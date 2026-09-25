"""Enrichment batch runner - backfill chunks, embed, deep-extract, verify.

Stage order matches the batch-by-model strategy (one Ollama model resident
per stage). Resumable: each planning query only selects papers not yet done,
so re-running after a crash continues where it left off.

Usage:
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage all --limit 20
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage verify --dry-run
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage extract --paper-ids 12,99
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from literature_core import get_logger, get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from scripts._progress import StageProgress, quiet_logging

logger = get_logger(__name__)


def preflight(stage: str) -> str | None:
    """Return an error string if `stage` cannot run, else None.

    The extract and verify stages are useless without Ollama. Without this
    check a dead daemon is only discovered per-call, deep inside scoring,
    where it is easily mistaken for a bad extraction.
    """
    if stage not in ("extract", "verify"):
        return None
    from services.verification_service import JudgeClient, MiniCheckClient

    mc = MiniCheckClient()
    if not mc.is_available():
        return (f"Ollama verifier unavailable at {mc.host} (model {mc.model}).\n"
                f"    Start it with:  ollama serve\n"
                f"    Then confirm:   ollama list | grep {mc.model.split(':')[0]}")
    if stage == "verify":
        judge = JudgeClient()
        try:
            import httpx
            with httpx.Client(timeout=5) as client:
                tags = client.get(f"{judge.host}/api/tags").text
            if judge.model.split(":")[0] not in tags:
                return (f"Judge model {judge.model} is not pulled.\n"
                        f"    Fix with:  ollama pull {judge.model}")
        except Exception as e:
            return f"Could not query Ollama at {judge.host}: {type(e).__name__}: {e}"
    return None


def plan_backfill(session) -> list[int]:
    """Papers with a PDF on record but no chunks."""
    sub = session.query(PaperChunk.paper_id)
    rows = (session.query(Paper.id)
            .filter(Paper.file_path.isnot(None), Paper.file_path != "")
            .filter(~Paper.id.in_(sub))
            .order_by(Paper.id).all())
    return [r.id for r in rows]


def plan_extract(session, limit: int | None) -> list[int]:
    """Chunked papers lacking a comprehensive extraction."""
    sub = session.query(PaperChunk.paper_id)
    q = (session.query(Paper.id)
         .outerjoin(PaperContent, PaperContent.paper_id == Paper.id)
         .filter(Paper.id.in_(sub))
         .filter((PaperContent.extraction_depth.is_(None))
                 | (PaperContent.extraction_depth != "comprehensive"))
         .order_by(Paper.id))
    if limit:
        q = q.limit(limit)
    return [r.id for r in q.all()]


def plan_embed(session, limit: int | None) -> list[int]:
    """Papers whose chunks or abstract are not yet in the vector store.

    Chunking makes text available; embedding is what makes it *searchable*,
    so this runs before the long LLM stages - semantic search over a paper
    starts working as soon as it is chunked, not after extraction finishes.
    """
    from services.embedding_service import EmbeddingService

    status = EmbeddingService.get_embedding_status(include_ids=True)
    ids = sorted(set(status.paper_ids_needing_chunk_embedding)
                 | set(status.paper_ids_needing_paper_embedding))
    return ids[:limit] if limit else ids


def plan_verify(session, limit: int | None) -> list[int]:
    """Comprehensive extractions never verified."""
    q = (session.query(Paper.id)
         .join(PaperContent, PaperContent.paper_id == Paper.id)
         .filter(PaperContent.extraction_depth == "comprehensive")
         .filter(PaperContent.verification_score.is_(None))
         .order_by(Paper.id))
    if limit:
        q = q.limit(limit)
    return [r.id for r in q.all()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrichment batch runner")
    p.add_argument("--stage",
                   choices=["backfill", "embed", "extract", "verify", "all"], default="all")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--paper-ids", type=lambda s: [int(x) for x in s.split(",")], default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def _run_backfill(ids: list[int], dry_run: bool) -> dict:
    from services.extraction_service import ExtractionService
    stats = {"processed": 0, "errors": 0}
    total = len(ids)
    for i, pid in enumerate(ids, 1):
        if dry_run:
            print(f"  [dry-run] would re-process PDF for paper {pid}")
            continue
        print(f"  [{i}/{total}] backfilling paper {pid}...", flush=True)
        try:
            result = ExtractionService.extract_pdf_and_store(pid)
            if getattr(result, "success", False):
                stats["processed"] += 1
            else:
                logger.error("Backfill failed", extra={"paper_id": pid,
                             "error": getattr(result, "error", "unknown")})
                stats["errors"] += 1
        except Exception as e:
            logger.error("Backfill failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
    return stats


async def _run_embed(ids: list[int], dry_run: bool) -> dict:
    from services.embedding_service import EmbeddingService

    stats = {"processed": 0, "errors": 0}
    if dry_run:
        for pid in ids:
            print(f"  [dry-run] would embed paper {pid}")
        return stats

    first_errors: list[str] = []
    with quiet_logging(), StageProgress("embed", len(ids)) as bar:
        for pid in ids:
            bar.item(f"paper {pid}")
            try:
                result = await EmbeddingService.embed_paper(pid)
                if result.success:
                    stats["processed"] += 1
                else:
                    stats["errors"] += 1
                    if len(first_errors) < 3:
                        first_errors.append(f"paper {pid}: {'; '.join(result.errors)[:160]}")
            except Exception as e:
                logger.error("Embed failed", extra={"paper_id": pid, "error": str(e)})
                stats["errors"] += 1
                if len(first_errors) < 3:
                    first_errors.append(f"paper {pid}: {type(e).__name__}: {e}")
            bar.done(ok=stats["processed"], err=stats["errors"])

    for line in first_errors:
        print(f"  ! {line}")
    return stats


async def _run_extract_verify(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "reextracted": 0, "review": 0, "errors": 0}
    if dry_run:
        for pid in ids:
            print(f"  [dry-run] would extract+verify paper {pid}")
        return stats

    first_errors: list[str] = []
    with quiet_logging(), StageProgress("extract+verify", len(ids)) as bar:
        for pid in ids:
            # extract -> verify -> (optional) re-extract on a low score
            bar.item(f"paper {pid}: extracting", substeps=2)
            try:
                result = await VerificationService.extract_and_verify(pid)
                bar.step(f"paper {pid}: verifying")
                stats["processed"] += 1
                if result.get("error"):
                    stats["errors"] += 1
                    if len(first_errors) < 3:
                        first_errors.append(f"paper {pid}: {result['error']}")
                elif result.get("routing") == "accept":
                    stats["accepted"] += 1
                    if result.get("attempts", 1) > 1:
                        stats["reextracted"] += 1
                else:
                    stats["review"] += 1
            except Exception as e:
                logger.error("Extract+verify failed", extra={"paper_id": pid, "error": str(e)})
                stats["errors"] += 1
                if len(first_errors) < 3:
                    first_errors.append(f"paper {pid}: {type(e).__name__}: {e}")
            bar.done(ok=stats["accepted"], review=stats["review"], err=stats["errors"])

    for line in first_errors:
        print(f"  ! {line}")
    return stats


def _run_verify_only(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "review": 0, "errors": 0}
    if dry_run:
        for pid in ids:
            print(f"  [dry-run] would verify paper {pid}")
        return stats

    first_errors: list[str] = []
    with quiet_logging(), StageProgress("verify", len(ids)) as bar:
        for pid in ids:
            bar.item(f"paper {pid}")
            try:
                result = VerificationService.verify_paper(pid)
                stats["processed"] += 1
                if result.get("error"):
                    stats["errors"] += 1
                    if len(first_errors) < 3:
                        first_errors.append(f"paper {pid}: {result['error']}")
                elif result.get("routing") == "accept":
                    stats["accepted"] += 1
                else:
                    stats["review"] += 1
            except Exception as e:
                logger.error("Verify failed", extra={"paper_id": pid, "error": str(e)})
                stats["errors"] += 1
                if len(first_errors) < 3:
                    first_errors.append(f"paper {pid}: {type(e).__name__}: {e}")
            bar.done(ok=stats["accepted"], review=stats["review"], err=stats["errors"])

    # Errors were suppressed to keep the bar readable; surface the reason once.
    for line in first_errors:
        print(f"  ! {line}")
    return stats


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    with get_session() as session:
        # chunk -> make searchable -> extract -> score. Stages are batched
        # rather than run per-paper because only one Ollama model fits in 8 GB
        # of VRAM; see the module docstring.
        stages = (["backfill", "embed", "extract", "verify"]
                  if args.stage == "all" else [args.stage])
        for stage in stages:
            if args.paper_ids:
                ids = args.paper_ids
            else:
                # Planning is inside quiet_logging too: plan_embed initialises
                # ChromaDB, which logs its collection stats at INFO and would
                # otherwise print above the bar on every stage.
                with quiet_logging():
                    if stage == "backfill":
                        ids = plan_backfill(session)
                    elif stage == "embed":
                        ids = plan_embed(session, args.limit)
                    elif stage == "extract":
                        ids = plan_extract(session, args.limit)
                    else:
                        ids = plan_verify(session, args.limit)
            blocked = None if args.dry_run else preflight(stage)
            if blocked:
                print(f"== Stage {stage}: ABORTED ==\n    {blocked}")
                return 1
            print(f"== Stage {stage}: {len(ids)} papers ==")
            if stage == "backfill":
                stats = _run_backfill(ids, args.dry_run)
            elif stage == "embed":
                stats = asyncio.run(_run_embed(ids, args.dry_run))
            elif stage == "extract":
                stats = asyncio.run(_run_extract_verify(ids, args.dry_run))
            else:
                stats = _run_verify_only(ids, args.dry_run)
            print(f"== Stage {stage} done: {stats} ==")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
