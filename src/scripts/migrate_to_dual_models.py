#!/usr/bin/env python3
"""
Migrate to dual-model embedding architecture (SPECTER2 + BGE).

Usage:
    python -m scripts.migrate_to_dual_models           # Full migration
    python -m scripts.migrate_to_dual_models --force   # Recreate collections with HNSW tuning
    python -m scripts.migrate_to_dual_models --dry-run # Preview only
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Suppress ALL verbose logging before any imports
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress loguru (used by embeddings modules) - must be after path setup
from loguru import logger as loguru_logger
loguru_logger.disable("embeddings")
loguru_logger.disable("literature_core")

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich import box
from rich.text import Text

from config.ai_settings import settings
from literature_core import get_session, Paper, PaperChunk


@dataclass
class MigrationStats:
    """Migration statistics."""
    papers_total: int = 0
    papers_embedded: int = 0
    papers_failed: int = 0
    chunks_total: int = 0
    chunks_embedded: int = 0
    elapsed_seconds: float = 0
    errors: list[dict] = field(default_factory=list)


def get_papers_with_abstracts() -> list[Paper]:
    """Get all papers that have abstracts."""
    with get_session() as session:
        papers = session.query(Paper).filter(
            Paper.abstract.isnot(None),
            Paper.abstract != ""
        ).all()
        for p in papers:
            session.expunge(p)
        return papers


def get_papers_with_chunks() -> list[Paper]:
    """Get papers that have text chunks."""
    with get_session() as session:
        papers = session.query(Paper).join(PaperChunk).distinct().all()
        for p in papers:
            session.expunge(p)
        return papers


def migrate_paper_embeddings(papers: list[Paper], console: Console, force: bool = False) -> MigrationStats:
    """Migrate paper-level embeddings."""
    stats = MigrationStats(papers_total=len(papers))
    start_time = time.time()

    import embeddings.vectorstore as vs

    # Handle force mode
    if force:
        try:
            temp_store = vs.get_vector_store()
            temp_store.client.delete_collection("papers")
        except Exception:
            pass
        vs._vectorstore_instance = None

    paper_store = vs.get_vector_store()

    from embeddings.generator import get_embedding_generator
    generator = get_embedding_generator()

    with Progress(
        SpinnerColumn(style="blue"),
        TextColumn("[blue]{task.description}"),
        BarColumn(bar_width=40, complete_style="blue", finished_style="green"),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Papers", total=len(papers))

        for paper in papers:
            try:
                text = f"{paper.title}\n\n{paper.abstract or ''}"
                embedding = generator.generate(text)

                paper_store.add(
                    id=str(paper.id),
                    embedding=embedding,
                    metadata={"paper_id": paper.id, "title": paper.title, "year": paper.year},
                    document=text[:1000],
                )
                stats.papers_embedded += 1

            except Exception as e:
                stats.papers_failed += 1
                stats.errors.append({"paper_id": paper.id, "error": str(e)})

            progress.update(task, advance=1)

    stats.elapsed_seconds = time.time() - start_time
    return stats


def migrate_chunk_embeddings(papers: list[Paper], console: Console, force: bool = False) -> MigrationStats:
    """Migrate chunk-level embeddings."""
    stats = MigrationStats(papers_total=len(papers))
    start_time = time.time()

    chunk_size = settings.embedding.chunk_size
    chunk_overlap = settings.embedding.chunk_overlap

    import embeddings.vectorstore as vs
    from services.paper_service import PaperService

    # Handle force mode
    if force:
        try:
            temp_store = vs.get_chunk_store()
            temp_store.client.delete_collection("chunks")
        except Exception:
            pass
        vs._chunk_store_instance = None

    chunk_store = vs.get_chunk_store()

    from embeddings.generator import get_embedding_generator
    generator = get_embedding_generator()

    with Progress(
        SpinnerColumn(style="magenta"),
        TextColumn("[magenta]{task.description}"),
        BarColumn(bar_width=40, complete_style="magenta", finished_style="green"),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Chunks", total=len(papers))

        for paper in papers:
            try:
                full_text = PaperService.get_full_text(paper.id)
                if not full_text:
                    stats.papers_embedded += 1
                    progress.update(task, advance=1)
                    continue

                try:
                    chunk_store.delete_paper_chunks(paper.id)
                except Exception:
                    pass

                chunk_embeddings = generator.embed_paper_chunks(
                    paper_id=paper.id,
                    full_text=full_text,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                if chunk_embeddings:
                    chunk_store.add_chunks(
                        chunk_ids=[c.chunk_id for c in chunk_embeddings],
                        embeddings=[c.embedding for c in chunk_embeddings],
                        texts=[c.text for c in chunk_embeddings],
                        metadatas=[c.to_metadata() for c in chunk_embeddings],
                    )
                    stats.chunks_embedded += len(chunk_embeddings)
                    stats.chunks_total += len(chunk_embeddings)

                stats.papers_embedded += 1

            except Exception as e:
                stats.papers_failed += 1
                stats.errors.append({"paper_id": paper.id, "error": str(e)})

            progress.update(task, advance=1)

    stats.elapsed_seconds = time.time() - start_time
    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate embeddings with HNSW tuning")
    parser.add_argument("--papers-only", action="store_true", help="Only paper-level")
    parser.add_argument("--chunks-only", action="store_true", help="Only chunk-level")
    parser.add_argument("--force", action="store_true", help="Recreate collections")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--limit", type=int, help="Limit papers to process")

    args = parser.parse_args()
    console = Console()

    # Compact header
    console.print()
    console.print("[bold blue]━━━ Embedding Migration ━━━[/bold blue]", justify="center")
    console.print(f"[dim]HNSW: ef={settings.chromadb.hnsw_ef_construction}, M={settings.chromadb.hnsw_m}[/dim]", justify="center")
    console.print()

    # Get papers
    papers_with_abstracts = get_papers_with_abstracts()
    papers_with_chunks = get_papers_with_chunks()

    if args.limit:
        papers_with_abstracts = papers_with_abstracts[:args.limit]
        papers_with_chunks = papers_with_chunks[:args.limit]

    # Compact plan display
    do_papers = not args.chunks_only
    do_chunks = not args.papers_only

    plan_items = []
    if do_papers:
        plan_items.append(f"[blue]Papers:[/blue] {len(papers_with_abstracts)}")
    if do_chunks:
        plan_items.append(f"[magenta]Chunks:[/magenta] {len(papers_with_chunks)} papers")
    if args.force:
        plan_items.append("[yellow]Force: recreate collections[/yellow]")

    console.print("  ".join(plan_items))
    console.print()

    if args.dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        return

    total_start = time.time()

    # Paper embeddings
    if do_papers:
        paper_stats = migrate_paper_embeddings(papers_with_abstracts, console, force=args.force)
        status = "[green]✓[/green]" if paper_stats.papers_failed == 0 else "[yellow]⚠[/yellow]"
        console.print(f"{status} Papers: {paper_stats.papers_embedded} embedded in {paper_stats.elapsed_seconds:.1f}s")

    # Chunk embeddings
    if do_chunks:
        chunk_stats = migrate_chunk_embeddings(papers_with_chunks, console, force=args.force)
        status = "[green]✓[/green]" if chunk_stats.papers_failed == 0 else "[yellow]⚠[/yellow]"
        console.print(f"{status} Chunks: {chunk_stats.chunks_embedded:,} from {chunk_stats.papers_embedded} papers in {chunk_stats.elapsed_seconds:.1f}s")

    # Done
    total_elapsed = time.time() - total_start
    console.print()
    console.print(f"[bold green]Done[/bold green] in {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
