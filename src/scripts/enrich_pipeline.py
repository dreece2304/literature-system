"""Enrichment batch runner - backfill chunks, deep-extract, verify.

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

logger = get_logger(__name__)


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
    p.add_argument("--stage", choices=["backfill", "extract", "verify", "all"], default="all")
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


async def _run_extract_verify(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "reextracted": 0, "review": 0, "errors": 0}
    total = len(ids)
    for i, pid in enumerate(ids, 1):
        if dry_run:
            print(f"  [dry-run] would extract+verify paper {pid}")
            continue
        print(f"  [{i}/{total}] extracting+verifying paper {pid}...", flush=True)
        try:
            result = await VerificationService.extract_and_verify(pid)
            stats["processed"] += 1
            if result.get("error"):
                stats["errors"] += 1
            elif result.get("routing") == "accept":
                stats["accepted"] += 1
                if result.get("attempts", 1) > 1:
                    stats["reextracted"] += 1
            else:
                stats["review"] += 1
        except Exception as e:
            logger.error("Extract+verify failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
        print(f"  paper {pid}: {stats}")
    return stats


def _run_verify_only(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "review": 0, "errors": 0}
    total = len(ids)
    for i, pid in enumerate(ids, 1):
        if dry_run:
            print(f"  [dry-run] would verify paper {pid}")
            continue
        print(f"  [{i}/{total}] verifying paper {pid}...", flush=True)
        try:
            result = VerificationService.verify_paper(pid)
            stats["processed"] += 1
            if result.get("error"):
                stats["errors"] += 1
            elif result.get("routing") == "accept":
                stats["accepted"] += 1
            else:
                stats["review"] += 1
        except Exception as e:
            logger.error("Verify failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
    return stats


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    with get_session() as session:
        stages = ["backfill", "extract", "verify"] if args.stage == "all" else [args.stage]
        for stage in stages:
            if args.paper_ids:
                ids = args.paper_ids
            elif stage == "backfill":
                ids = plan_backfill(session)
            elif stage == "extract":
                ids = plan_extract(session, args.limit)
            else:
                ids = plan_verify(session, args.limit)
            print(f"== Stage {stage}: {len(ids)} papers ==")
            if stage == "backfill":
                stats = _run_backfill(ids, args.dry_run)
            elif stage == "extract":
                stats = asyncio.run(_run_extract_verify(ids, args.dry_run))
            else:
                stats = _run_verify_only(ids, args.dry_run)
            print(f"== Stage {stage} done: {stats} ==")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
