#!/usr/bin/env python3
"""
Reindex papers with chunk-level embeddings for semantic search.

Extracts text chunks from papers and generates embeddings for vector search.

Usage:
    # Full reindex (all papers with chunks)
    python -m scripts.reindex_embeddings

    # Only papers missing embeddings (incremental)
    python -m scripts.reindex_embeddings --missing-only

    # Single paper
    python -m scripts.reindex_embeddings --paper-id 123

    # Dry run (preview only)
    python -m scripts.reindex_embeddings --dry-run

    # Show stats only
    python -m scripts.reindex_embeddings --stats

    # Custom chunk size
    python -m scripts.reindex_embeddings --chunk-size 600 --chunk-overlap 100
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TaskProgressColumn, TimeRemainingColumn, MofNCompleteColumn
)
from rich.table import Table
from rich import box

from literature_core import get_session, Paper, PaperChunk, setup_logging, get_logger
from services.paper_service import PaperService

setup_logging()
logger = get_logger(__name__)

# Global for graceful shutdown
_shutdown_requested = False


@dataclass
class ReindexStats:
    """Statistics for the reindex operation."""
    papers_total: int = 0
    papers_processed: int = 0
    papers_skipped: int = 0
    papers_failed: int = 0
    chunks_created: int = 0
    chunks_deleted: int = 0
    elapsed_seconds: float = 0
    errors: list[dict] = field(default_factory=list)


def get_papers_with_chunks(paper_id: int | None = None) -> list[Paper]:
    """Get papers that have chunks available (extracted full text)."""
    with get_session() as session:
        query = session.query(Paper).join(PaperChunk).distinct()

        if paper_id:
            query = query.filter(Paper.id == paper_id)

        papers = query.all()
        for p in papers:
            session.expunge(p)

        return papers


def get_papers_needing_embeddings() -> list[Paper]:
    """Get papers with chunks but missing from vector store."""
    from embeddings.vectorstore import get_chunk_store

    # Get all papers with chunks
    papers = get_papers_with_chunks()

    # Get papers already in vector store by querying collection metadata
    chunk_store = get_chunk_store()
    try:
        results = chunk_store.collection.get(include=["metadatas"])
        indexed_papers = set()
        for metadata in results["metadatas"] or []:
            if metadata and "paper_id" in metadata:
                indexed_papers.add(metadata["paper_id"])
    except Exception:
        indexed_papers = set()

    # Return papers not yet indexed
    return [p for p in papers if p.id not in indexed_papers]


def reindex_paper(
    paper: Paper,
    generator,
    chunk_store,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> tuple[int, int]:
    """
    Reindex a single paper.

    Returns:
        Tuple of (chunks_created, chunks_deleted)
    """
    full_text = PaperService.get_full_text(paper.id)
    if not full_text:
        return 0, 0

    # Delete existing chunks for this paper (if any)
    deleted = 0
    try:
        chunk_store.delete_paper_chunks(paper.id)
        deleted = 1  # Just mark that we deleted something
    except Exception:
        pass

    # Generate chunk embeddings
    chunk_embeddings = generator.embed_paper_chunks(
        paper_id=paper.id,
        full_text=full_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not chunk_embeddings:
        return 0, deleted

    # Add to vector store
    chunk_store.add_chunks(
        chunk_ids=[c.chunk_id for c in chunk_embeddings],
        embeddings=[c.embedding for c in chunk_embeddings],
        texts=[c.text for c in chunk_embeddings],
        metadatas=[c.to_metadata() for c in chunk_embeddings],
    )

    return len(chunk_embeddings), deleted


def show_stats(console: Console):
    """Show current chunk store statistics."""
    from embeddings.vectorstore import get_chunk_store, get_vector_store

    console.print()
    console.print(Panel("[bold]Vector Store Statistics[/bold]", style="blue"))

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
    table.add_column("Store")
    table.add_column("Collection")
    table.add_column("Count", justify="right")
    table.add_column("Status")

    # Paper-level embeddings
    try:
        paper_store = get_vector_store()
        paper_stats = paper_store.get_stats()
        table.add_row(
            "Paper-level",
            paper_stats['collection_name'],
            str(paper_stats['count']),
            "[green]OK[/green]"
        )
    except Exception as e:
        table.add_row("Paper-level", "-", "-", f"[red]Error: {e}[/red]")

    # Chunk-level embeddings
    try:
        chunk_store = get_chunk_store()
        chunk_stats = chunk_store.get_stats()
        table.add_row(
            "Chunk-level",
            chunk_stats['collection_name'],
            f"{chunk_stats['total_chunks']} chunks / {chunk_stats['papers_indexed']} papers",
            "[green]OK[/green]"
        )
    except Exception as e:
        table.add_row("Chunk-level", "-", "-", f"[red]Error: {e}[/red]")

    console.print(table)

    # Coverage
    papers = get_papers_with_chunks()
    try:
        chunk_store = get_chunk_store()
        stats = chunk_store.get_stats()
        indexed = stats['papers_indexed']
        total = len(papers)

        coverage_table = Table(show_header=False, box=box.SIMPLE)
        coverage_table.add_column("Metric", style="cyan")
        coverage_table.add_column("Value", justify="right")

        coverage_table.add_row("Papers in DB with chunks", str(total))
        coverage_table.add_row("Papers with embeddings", str(indexed))

        if total > indexed:
            coverage_table.add_row(
                "[yellow]Papers needing indexing[/yellow]",
                f"[yellow]{total - indexed}[/yellow]"
            )
        else:
            coverage_table.add_row("Coverage", "[green]100%[/green]")

        console.print()
        console.print(Panel("Coverage", style="blue"))
        console.print(coverage_table)
    except Exception:
        pass

    console.print()


def run_reindex(
    papers: list[Paper],
    chunk_size: int,
    chunk_overlap: int,
    console: Console
) -> ReindexStats:
    """Run the reindex with Rich progress display."""
    global _shutdown_requested

    stats = ReindexStats(papers_total=len(papers))
    start_time = time.time()

    # Suppress logging during progress
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("embeddings").setLevel(logging.ERROR)
    logging.getLogger("embeddings.generator").setLevel(logging.ERROR)
    logging.getLogger("embeddings.vectorstore").setLevel(logging.ERROR)

    from loguru import logger as loguru_logger
    loguru_logger.disable("embeddings")
    loguru_logger.disable("embeddings.generator")
    loguru_logger.disable("embeddings.vectorstore")

    # Import embedding tools
    from embeddings.generator import get_embedding_generator
    from embeddings.vectorstore import get_chunk_store

    generator = get_embedding_generator()
    chunk_store = get_chunk_store()

    # Show model info
    model_table = Table(show_header=False, box=box.SIMPLE)
    model_table.add_column("", style="dim")
    model_table.add_column("")
    model_table.add_row("Model", generator.model_name)
    model_table.add_row("Device", str(generator.device))
    model_table.add_row("Dimension", str(generator.dimension))
    model_table.add_row("Chunk size", f"{chunk_size} chars")
    model_table.add_row("Overlap", f"{chunk_overlap} chars")
    console.print(model_table)
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            "[cyan]Indexing papers",
            total=len(papers),
            status=""
        )

        for paper in papers:
            if _shutdown_requested:
                console.print("\n[yellow]Shutdown requested, stopping...[/yellow]")
                break

            # Update description with current paper
            title_short = paper.title[:35] + "..." if len(paper.title) > 35 else paper.title
            progress.update(
                task,
                description=f"[cyan][{paper.id}] {title_short}"
            )

            try:
                created, deleted = reindex_paper(
                    paper=paper,
                    generator=generator,
                    chunk_store=chunk_store,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                stats.papers_processed += 1
                stats.chunks_created += created
                stats.chunks_deleted += deleted

                # Update status field
                progress.update(
                    task,
                    advance=1,
                    status=f"chunks: {stats.chunks_created:,}"
                )

            except Exception as e:
                stats.papers_failed += 1
                stats.errors.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "error": str(e)
                })
                progress.update(task, advance=1)

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("embeddings").setLevel(logging.INFO)
    loguru_logger.enable("embeddings")

    stats.elapsed_seconds = time.time() - start_time
    return stats


def print_summary(stats: ReindexStats, console: Console):
    """Print final summary."""
    console.print()
    console.print(Panel("[bold]Summary[/bold]", style="blue"))

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Papers processed", str(stats.papers_processed))
    table.add_row("Papers failed", str(stats.papers_failed) if stats.papers_failed else "[green]0[/green]")
    table.add_row("Chunks created", f"{stats.chunks_created:,}")
    if stats.chunks_deleted > 0:
        table.add_row("Chunks replaced", f"{stats.chunks_deleted:,}")
    table.add_row("Elapsed time", f"{stats.elapsed_seconds:.1f}s")

    if stats.papers_processed > 0:
        rate = stats.papers_processed / stats.elapsed_seconds
        table.add_row("Rate", f"{rate:.1f} papers/s")

    console.print(table)

    # Errors
    if stats.errors:
        console.print()
        console.print(Panel("[bold red]Errors[/bold red]"))
        for err in stats.errors[:10]:
            console.print(f"  [{err['paper_id']}] {err['error']}")
        if len(stats.errors) > 10:
            console.print(f"  ... and {len(stats.errors) - 10} more")


def main():
    """Main entry point."""
    global _shutdown_requested

    parser = argparse.ArgumentParser(
        description="Reindex papers with chunk-level embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--paper-id", type=int,
        help="Reindex single paper by ID"
    )
    parser.add_argument(
        "--missing-only", action="store_true",
        help="Only index papers missing from vector store (incremental)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only, don't make changes"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show statistics only"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=500,
        help="Target characters per chunk (default: 500)"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=50,
        help="Overlap between chunks (default: 50)"
    )
    parser.add_argument(
        "--limit", type=int,
        help="Maximum papers to process"
    )

    args = parser.parse_args()
    console = Console()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        global _shutdown_requested
        _shutdown_requested = True
        console.print("\n[yellow]Interrupt received, finishing current paper...[/yellow]")

    signal.signal(signal.SIGINT, signal_handler)

    if args.stats:
        show_stats(console)
        return

    # Header
    console.print(Panel(
        "[bold]Chunk Embedding Reindex[/bold]\n"
        f"Chunk size: {args.chunk_size} | Overlap: {args.chunk_overlap}",
        style="blue"
    ))

    # Get papers to process
    if args.paper_id:
        papers = get_papers_with_chunks(args.paper_id)
        if not papers:
            console.print(f"[red]Paper {args.paper_id} not found or has no chunks[/red]")
            return
    elif args.missing_only:
        console.print("[dim]Finding papers missing embeddings...[/dim]")
        papers = get_papers_needing_embeddings()
        if not papers:
            console.print("[green]All papers already have embeddings![/green]")
            show_stats(console)
            return
        console.print(f"[cyan]Found {len(papers)} papers needing embeddings[/cyan]")
    else:
        papers = get_papers_with_chunks()

    if args.limit:
        papers = papers[:args.limit]

    if not papers:
        console.print("[yellow]No papers to process[/yellow]")
        return

    console.print(f"\nPapers to process: [bold]{len(papers)}[/bold]")

    if args.dry_run:
        console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")

        # Show sample
        from embeddings.generator import get_embedding_generator
        generator = get_embedding_generator()

        paper = papers[0]
        full_text = PaperService.get_full_text(paper.id)
        chunks = generator.chunk_paper(
            paper_id=paper.id,
            full_text=full_text,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )

        console.print(f"Sample: Paper {paper.id} -> {len(chunks)} chunks")
        if chunks:
            console.print(f"  [dim]First: {chunks[0].text[:80]}...[/dim]")

        # Estimate
        total_chars = sum(len(PaperService.get_full_text(p.id) or "") for p in papers[:10])
        avg_chars = total_chars / min(10, len(papers))
        estimated = int(avg_chars / (args.chunk_size - args.chunk_overlap) * len(papers))
        console.print(f"\nEstimated total chunks: ~{estimated:,}")
        return

    console.print()

    # Run reindex
    stats = run_reindex(
        papers=papers,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        console=console
    )

    # Print summary
    print_summary(stats, console)

    # Show final stats
    show_stats(console)


if __name__ == "__main__":
    main()
