#!/usr/bin/env python3
"""
Chunk all PDFs that need text extraction.

Extracts text from PDFs and splits into searchable chunks for
deep extraction and semantic search.

Usage:
    # Process all PDFs needing chunks
    python -m scripts.chunk_pdfs

    # Limit to 50 papers
    python -m scripts.chunk_pdfs --limit 50

    # Dry run (preview only)
    python -m scripts.chunk_pdfs --dry-run

    # Process specific papers
    python -m scripts.chunk_pdfs --paper-ids 123 456 789

    # Show stats only
    python -m scripts.chunk_pdfs --stats

    # Force re-extraction
    python -m scripts.chunk_pdfs --force
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

from literature_core import get_session, Paper, get_logger, setup_logging
from literature_core.models import PaperChunk, ExtractionMetadata
from literature_core.constants import ChunkingStatus
from services.extraction_service import ExtractionService, ChunkingResult
from sqlalchemy import func

setup_logging()
logger = get_logger(__name__)

# Global for graceful shutdown
_shutdown_requested = False


@dataclass
class ChunkingStats:
    total_papers: int = 0
    with_pdf: int = 0
    with_chunks: int = 0
    need_chunks: int = 0
    total_chunks: int = 0
    stuck_processing: int = 0
    stuck_complete_no_chunks: int = 0


@dataclass
class BatchResult:
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_chunks: int = 0
    elapsed_seconds: float = 0
    errors: list[tuple[int, str, str]] = field(default_factory=list)  # (id, title, error)


def reset_stuck_papers() -> int:
    """Reset papers stuck in bad states back to pending."""
    with get_session() as session:
        from sqlalchemy import and_, or_

        # Get paper IDs that actually have chunks
        has_chunks_subq = session.query(PaperChunk.paper_id).distinct().subquery()

        # Reset: processing status OR (complete status with no chunks)
        stuck_count = session.query(ExtractionMetadata).filter(
            or_(
                ExtractionMetadata.chunking_status == ChunkingStatus.PROCESSING,
                and_(
                    ExtractionMetadata.chunking_status == ChunkingStatus.COMPLETE,
                    ~ExtractionMetadata.paper_id.in_(session.query(has_chunks_subq.c.paper_id))
                )
            )
        ).update({
            ExtractionMetadata.chunking_status: ChunkingStatus.PENDING,
            ExtractionMetadata.chunking_error: None,
            ExtractionMetadata.chunk_count: 0,
        }, synchronize_session=False)

        session.commit()
        return stuck_count


def get_stats() -> ChunkingStats:
    """Get chunking statistics."""
    with get_session() as session:
        stats = ChunkingStats()
        stats.total_papers = session.query(Paper).count()
        stats.with_pdf = session.query(Paper).filter(
            Paper.file_path.isnot(None),
            Paper.file_path != ""
        ).count()

        # Papers with actual chunks in PaperChunk table
        stats.with_chunks = session.query(
            func.count(func.distinct(PaperChunk.paper_id))
        ).scalar() or 0

        # Total chunks
        stats.total_chunks = session.query(func.count(PaperChunk.id)).scalar() or 0

        stats.need_chunks = stats.with_pdf - stats.with_chunks

        # Check for stuck papers
        has_chunks_subq = session.query(PaperChunk.paper_id).distinct().subquery()

        stats.stuck_processing = session.query(ExtractionMetadata).filter(
            ExtractionMetadata.chunking_status == ChunkingStatus.PROCESSING
        ).count()

        stats.stuck_complete_no_chunks = session.query(ExtractionMetadata).filter(
            ExtractionMetadata.chunking_status == ChunkingStatus.COMPLETE,
            ~ExtractionMetadata.paper_id.in_(session.query(has_chunks_subq.c.paper_id))
        ).count()

        return stats


def get_papers_needing_chunks(
    limit: int = 100,
    paper_ids: Optional[list[int]] = None
) -> list[dict]:
    """Get papers with PDFs but no chunks (checks actual PaperChunk table)."""
    with get_session() as session:
        # Subquery for papers that have actual chunks
        has_chunks = session.query(PaperChunk.paper_id).distinct().subquery()

        query = session.query(Paper).filter(
            Paper.file_path.isnot(None),
            Paper.file_path != "",
            ~Paper.id.in_(session.query(has_chunks.c.paper_id))
        )

        if paper_ids:
            query = query.filter(Paper.id.in_(paper_ids))

        query = query.order_by(Paper.id).limit(limit)
        papers = query.all()

        return [
            {
                "id": p.id,
                "title": p.title or f"Paper {p.id}",
                "file_path": p.file_path,
            }
            for p in papers
        ]


def show_stats(console: Console):
    """Show chunking statistics."""
    stats = get_stats()

    console.print()
    console.print(Panel("[bold]PDF Chunking Status[/bold]", style="blue"))

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total papers", str(stats.total_papers))
    table.add_row("Papers with PDF", str(stats.with_pdf))
    table.add_row("Papers with chunks", f"[green]{stats.with_chunks}[/green]")
    if stats.need_chunks > 0:
        table.add_row("Need chunking", f"[yellow]{stats.need_chunks}[/yellow]")
    elif stats.need_chunks < 0:
        table.add_row("Need chunking", "[green]0[/green]")
        table.add_row("[dim]Orphan chunks[/dim]", f"[dim]{abs(stats.need_chunks)} papers have chunks but no PDF[/dim]")
    else:
        table.add_row("Need chunking", "[green]0[/green]")
    table.add_row("Total chunks", f"{stats.total_chunks:,}")

    console.print(table)

    # Show stuck papers if any
    if stats.stuck_processing > 0 or stats.stuck_complete_no_chunks > 0:
        console.print()
        console.print(Panel("[bold yellow]Status Issues[/bold yellow]"))
        if stats.stuck_processing > 0:
            console.print(f"  [yellow]Stuck in PROCESSING: {stats.stuck_processing}[/yellow]")
        if stats.stuck_complete_no_chunks > 0:
            console.print(f"  [yellow]Marked COMPLETE but no chunks: {stats.stuck_complete_no_chunks}[/yellow]")
        console.print("  [dim]Run without --stats to auto-reset these[/dim]")

    console.print()


def run_chunking(
    papers: list[dict],
    force: bool,
    console: Console
) -> BatchResult:
    """Run PDF chunking with Rich progress display."""
    global _shutdown_requested

    result = BatchResult()
    start_time = time.time()

    if not papers:
        return result

    # Suppress logging during progress
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    logging.getLogger("pdfplumber").setLevel(logging.ERROR)
    logging.getLogger("services").setLevel(logging.ERROR)

    from loguru import logger as loguru_logger
    loguru_logger.disable("services")
    loguru_logger.disable("services.extraction_service")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=False,
    ) as progress:
        # Overall progress
        task = progress.add_task(
            "[cyan]Chunking PDFs",
            total=len(papers),
            status=""
        )

        for paper in papers:
            if _shutdown_requested:
                console.print("\n[yellow]Shutdown requested, stopping...[/yellow]")
                break

            paper_id = paper["id"]
            title_short = paper["title"][:35] + "..." if len(paper["title"]) > 35 else paper["title"]

            progress.update(
                task,
                description=f"[cyan][{paper_id}] {title_short}"
            )

            try:
                # Process the paper directly (skip queue_extraction which may have stale status)
                chunk_result = ExtractionService.process_extraction_single(
                    paper_id,
                    force=force
                )

                result.processed += 1

                if chunk_result.status == "complete":
                    result.success += 1
                    result.total_chunks += chunk_result.chunk_count or 0
                    method = chunk_result.extraction_method or "text"
                    progress.update(
                        task,
                        advance=1,
                        status=f"[green]✓[/green] {chunk_result.chunk_count}ch ({method})"
                    )
                elif chunk_result.status == "skipped":
                    result.skipped += 1
                    progress.update(task, advance=1, status="[yellow]○[/yellow] skipped")
                else:
                    result.failed += 1
                    error_short = (chunk_result.error or "Unknown")[:30]
                    result.errors.append((paper_id, paper["title"], chunk_result.error or "Unknown"))
                    progress.update(task, advance=1, status=f"[red]✗[/red] {error_short}")

            except Exception as e:
                result.failed += 1
                result.errors.append((paper_id, paper["title"], str(e)))
                progress.update(task, advance=1, status=f"[red]✗[/red] {str(e)[:30]}")

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("pdfplumber").setLevel(logging.WARNING)
    loguru_logger.enable("services")

    result.elapsed_seconds = time.time() - start_time
    return result


def print_summary(result: BatchResult, console: Console):
    """Print final summary."""
    console.print()
    console.print(Panel("[bold]Summary[/bold]", style="blue"))

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Processed", str(result.processed))
    table.add_row("Successful", f"[green]{result.success}[/green]")
    table.add_row("Failed", f"[red]{result.failed}[/red]" if result.failed else "[green]0[/green]")
    table.add_row("Skipped", str(result.skipped))
    table.add_row("Chunks created", f"{result.total_chunks:,}")
    table.add_row("Elapsed time", f"{result.elapsed_seconds:.1f}s")

    if result.processed > 0 and result.elapsed_seconds > 0:
        rate = result.processed / result.elapsed_seconds
        table.add_row("Rate", f"{rate:.2f} papers/s")

    console.print(table)

    # Errors
    if result.errors:
        console.print()
        console.print(Panel("[bold red]Failed Papers[/bold red]"))
        for paper_id, title, error in result.errors[:10]:
            title_short = title[:40] + "..." if len(title) > 40 else title
            console.print(f"  [{paper_id}] {title_short}")
            console.print(f"      [red]{error}[/red]")
        if len(result.errors) > 10:
            console.print(f"  ... and {len(result.errors) - 10} more")


def main():
    """Main entry point."""
    global _shutdown_requested

    parser = argparse.ArgumentParser(
        description="Extract and chunk text from PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Maximum papers to process (default: 100)"
    )
    parser.add_argument(
        "--paper-ids", type=int, nargs="+",
        help="Specific paper IDs to process"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only, don't process"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show statistics only"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-extraction even if chunks exist"
    )
    parser.add_argument(
        "--no-reset", action="store_true",
        help="Don't reset stuck papers"
    )

    args = parser.parse_args()
    console = Console()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        global _shutdown_requested
        _shutdown_requested = True
        console.print("\n[yellow]Interrupt received, finishing current paper...[/yellow]")

    signal.signal(signal.SIGINT, signal_handler)

    # Stats only mode
    if args.stats:
        show_stats(console)
        return

    # Header
    console.print(Panel(
        "[bold]PDF Text Extraction & Chunking[/bold]",
        style="blue"
    ))

    # Reset stuck papers first (unless disabled)
    if not args.no_reset:
        stuck_reset = reset_stuck_papers()
        if stuck_reset > 0:
            console.print(f"[yellow]Reset {stuck_reset} stuck papers to pending[/yellow]")

    # Show current stats
    show_stats(console)

    # Get papers to process
    papers = get_papers_needing_chunks(
        limit=args.limit,
        paper_ids=args.paper_ids
    )

    if not papers and not args.force:
        console.print("[green]No papers need chunking![/green]")
        return

    console.print(f"Papers to process: [bold]{len(papers)}[/bold]")

    # Dry run
    if args.dry_run:
        console.print("\n[yellow]DRY RUN - Papers that would be processed:[/yellow]")
        for p in papers[:20]:
            console.print(f"  [dim][{p['id']}][/dim] {p['title'][:60]}...")
        if len(papers) > 20:
            console.print(f"  [dim]... and {len(papers) - 20} more[/dim]")
        return

    console.print()

    # Run chunking
    result = run_chunking(papers, force=args.force, console=console)

    # Print summary
    print_summary(result, console)

    # Show updated stats
    show_stats(console)


if __name__ == "__main__":
    main()
