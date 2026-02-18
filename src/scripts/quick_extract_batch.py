#!/usr/bin/env python3
"""
Run quick extractions with Ollama for papers needing extraction.

Quick extraction extracts: paper_type, topics, one_sentence_summary,
and project_relevance scores from abstracts.

Usage:
    # Process all papers needing quick extraction
    python -m scripts.quick_extract_batch

    # Limit to 50 papers
    python -m scripts.quick_extract_batch --limit 50

    # Dry run (preview only)
    python -m scripts.quick_extract_batch --dry-run

    # Process specific papers
    python -m scripts.quick_extract_batch --paper-ids 123 456 789

    # Show stats only
    python -m scripts.quick_extract_batch --stats

    # Force re-extraction
    python -m scripts.quick_extract_batch --force

    # Custom delay between extractions (rate limiting)
    python -m scripts.quick_extract_batch --delay 2.0
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import dataclass, field
from typing import Optional

from literature_core import get_session, Paper, get_logger, setup_logging
from literature_core.models import PaperContent, ProjectRelevance
from services.extraction_service import ExtractionService
from sqlalchemy import func

setup_logging()
logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    paper_id: int
    title: str
    status: str  # success, failed, skipped
    topics: list[str] = field(default_factory=list)
    paper_type: Optional[str] = None
    relevances: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class BatchStats:
    total_papers: int = 0
    with_abstract: int = 0
    with_quick_extraction: int = 0
    need_quick_extraction: int = 0
    with_deep_extraction: int = 0
    high_relevance: int = 0
    medium_relevance: int = 0


@dataclass
class BatchResult:
    processed: int = 0
    success: int = 0
    failed: int = 0
    high_relevance: int = 0
    medium_relevance: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)
    results: list[ExtractionResult] = field(default_factory=list)


def get_stats() -> BatchStats:
    """Get extraction statistics."""
    with get_session() as session:
        stats = BatchStats()
        stats.total_papers = session.query(Paper).count()

        stats.with_abstract = session.query(Paper).filter(
            Paper.abstract.isnot(None),
            Paper.abstract != ""
        ).count()

        # Quick extraction done
        stats.with_quick_extraction = session.query(PaperContent).filter(
            PaperContent.quick_extraction_date.isnot(None)
        ).count()

        # Deep extraction done
        stats.with_deep_extraction = session.query(PaperContent).filter(
            PaperContent.deep_extraction_date.isnot(None)
        ).count()

        # Need quick extraction (have abstract, no extraction yet)
        extracted_ids = session.query(PaperContent.paper_id).filter(
            PaperContent.quick_extraction_date.isnot(None)
        ).subquery()

        stats.need_quick_extraction = session.query(Paper).filter(
            Paper.abstract.isnot(None),
            Paper.abstract != "",
            ~Paper.id.in_(session.query(extracted_ids.c.paper_id))
        ).count()

        # High relevance papers
        stats.high_relevance = session.query(
            func.count(func.distinct(ProjectRelevance.paper_id))
        ).filter(
            ProjectRelevance.relevance_level == "high"
        ).scalar() or 0

        # Medium relevance papers
        stats.medium_relevance = session.query(
            func.count(func.distinct(ProjectRelevance.paper_id))
        ).filter(
            ProjectRelevance.relevance_level == "medium"
        ).scalar() or 0

        return stats


def get_papers_needing_extraction(
    limit: int = 100,
    paper_ids: Optional[list[int]] = None
) -> list[dict]:
    """Get papers with abstracts but no quick extraction."""
    with get_session() as session:
        # Papers with quick extraction
        extracted_ids = session.query(PaperContent.paper_id).filter(
            PaperContent.quick_extraction_date.isnot(None)
        ).subquery()

        query = session.query(Paper).filter(
            Paper.abstract.isnot(None),
            Paper.abstract != "",
            ~Paper.id.in_(session.query(extracted_ids.c.paper_id))
        )

        if paper_ids:
            query = query.filter(Paper.id.in_(paper_ids))

        query = query.order_by(Paper.id).limit(limit)
        papers = query.all()

        return [
            {
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "abstract_len": len(p.abstract) if p.abstract else 0,
            }
            for p in papers
        ]


async def extract_paper_quick(paper_id: int, force: bool = False) -> ExtractionResult:
    """Run quick extraction on a single paper."""
    # Get paper info
    with get_session() as session:
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return ExtractionResult(
                paper_id=paper_id,
                title="Unknown",
                status="failed",
                error="Paper not found"
            )
        title = paper.title

    try:
        # Run quick extraction with Ollama
        result = await ExtractionService.extract_paper_quick(
            paper_id=paper_id,
            backend="ollama",
            force=force
        )

        if result.success:
            # Get relevance scores
            relevances = {}
            with get_session() as session:
                rels = session.query(ProjectRelevance).filter(
                    ProjectRelevance.paper_id == paper_id
                ).all()
                relevances = {r.project_name: r.relevance_level or "none" for r in rels}

            return ExtractionResult(
                paper_id=paper_id,
                title=title,
                status="success",
                topics=result.topics or [],
                paper_type=result.paper_type,
                relevances=relevances,
            )
        else:
            return ExtractionResult(
                paper_id=paper_id,
                title=title,
                status="failed",
                error=result.error or "Unknown error"
            )

    except Exception as e:
        logger.error(f"Failed to extract paper {paper_id}: {e}")
        return ExtractionResult(
            paper_id=paper_id,
            title=title,
            status="failed",
            error=str(e)
        )


async def run_with_rich_display(
    papers: list[dict],
    delay: float = 1.0,
    force: bool = False,
) -> BatchResult:
    """Run extraction with rich progress display."""
    import logging
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn

    console = Console()
    result = BatchResult()

    # Suppress logging during progress display
    logging.getLogger().setLevel(logging.WARNING)

    # Also suppress loguru (used by services)
    from loguru import logger as loguru_logger
    loguru_logger.disable("services")
    loguru_logger.disable("embeddings")

    last_result: ExtractionResult | None = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("[cyan]Extracting papers...", total=len(papers))

        for paper in papers:
            progress.update(task_id, description=f"[cyan]Extracting [{paper['id']}]...")

            extraction_result = await extract_paper_quick(paper["id"], force=force)
            result.results.append(extraction_result)
            result.processed += 1

            if extraction_result.status == "success":
                result.success += 1
                last_result = extraction_result

                # Count relevance
                for level in extraction_result.relevances.values():
                    if level == "high":
                        result.high_relevance += 1
                        break
                for level in extraction_result.relevances.values():
                    if level == "medium":
                        result.medium_relevance += 1
                        break

                # Build description with result info
                rel_parts = []
                for proj, level in extraction_result.relevances.items():
                    if level == "high":
                        rel_parts.append(f"{proj}=H")
                    elif level == "medium":
                        rel_parts.append(f"{proj}=M")
                rel_str = ",".join(rel_parts) if rel_parts else "-"

                desc = f"[green]✓[/green] [{paper['id']}] {extraction_result.paper_type or '?'} | rel:{rel_str}"
            else:
                result.failed += 1
                result.errors.append((paper["id"], extraction_result.error or "Unknown"))
                desc = f"[red]✗[/red] [{paper['id']}] {extraction_result.error or 'failed'}..."[:60]

            progress.update(task_id, advance=1, description=desc)

            # Rate limiting
            if delay > 0 and result.processed < len(papers):
                await asyncio.sleep(delay)

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    loguru_logger.enable("services")
    loguru_logger.enable("embeddings")

    return result


async def run_simple(
    papers: list[dict],
    delay: float = 1.0,
    force: bool = False,
) -> BatchResult:
    """Run extraction with simple text output."""
    result = BatchResult()

    print("\nProcessing quick extractions...")
    print("-" * 60)

    for i, paper in enumerate(papers):
        print(f"[{i+1}/{len(papers)}] Processing paper {paper['id']}...")

        extraction_result = await extract_paper_quick(paper["id"], force=force)
        result.results.append(extraction_result)
        result.processed += 1

        if extraction_result.status == "success":
            result.success += 1
            rel_str = ", ".join(
                f"{k}={v}" for k, v in extraction_result.relevances.items()
                if v in ("high", "medium")
            ) or "none"
            print(f"  -> {extraction_result.paper_type or 'unknown'} | Relevance: {rel_str}")

            for level in extraction_result.relevances.values():
                if level == "high":
                    result.high_relevance += 1
                    break
            for level in extraction_result.relevances.values():
                if level == "medium":
                    result.medium_relevance += 1
                    break
        else:
            result.failed += 1
            result.errors.append((paper["id"], extraction_result.error or "Unknown"))
            print(f"  -> FAILED: {extraction_result.error}")

        # Rate limiting
        if delay > 0 and result.processed < len(papers):
            await asyncio.sleep(delay)

    return result


def check_ollama() -> bool:
    """Check if Ollama is available."""
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run quick extractions with Ollama"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum papers to process (default: 100)"
    )
    parser.add_argument(
        "--paper-ids",
        type=int,
        nargs="+",
        help="Specific paper IDs to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't process"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction even if already extracted"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between extractions in seconds (default: 1.0)"
    )

    args = parser.parse_args()

    # Check for rich
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        console = Console()
        use_rich = True
    except ImportError:
        use_rich = False
        print("(Install 'rich' for better display: pip install rich)")

    # Show stats
    stats = get_stats()

    if use_rich:
        table = Table(title="Quick Extraction Status", show_header=False, box=None)
        table.add_column("Metric", style="dim", width=22)
        table.add_column("Value", style="bold")
        table.add_row("Total papers", str(stats.total_papers))
        table.add_row("With abstract", str(stats.with_abstract))
        table.add_row("Quick extraction done", f"[green]{stats.with_quick_extraction}[/green]")
        table.add_row("Need quick extraction", f"[yellow]{stats.need_quick_extraction}[/yellow]" if stats.need_quick_extraction else "0")
        table.add_row("Deep extraction done", str(stats.with_deep_extraction))
        table.add_row("High relevance papers", f"[cyan]{stats.high_relevance}[/cyan]")
        table.add_row("Medium relevance papers", f"[blue]{stats.medium_relevance}[/blue]")
        console.print()
        console.print(Panel(table, border_style="blue"))
    else:
        print("\n" + "=" * 60)
        print("QUICK EXTRACTION STATUS")
        print("=" * 60)
        print(f"Total papers:           {stats.total_papers}")
        print(f"With abstract:          {stats.with_abstract}")
        print(f"Quick extraction done:  {stats.with_quick_extraction}")
        print(f"Need quick extraction:  {stats.need_quick_extraction}")
        print(f"Deep extraction done:   {stats.with_deep_extraction}")
        print(f"High relevance papers:  {stats.high_relevance}")
        print(f"Medium relevance papers: {stats.medium_relevance}")

    if args.stats:
        return

    # Get papers to process
    papers = get_papers_needing_extraction(
        limit=args.limit,
        paper_ids=args.paper_ids
    )

    if not papers and not args.force:
        if use_rich:
            console.print("\n[green]No papers need quick extraction![/green]")
        else:
            print("\nNo papers need quick extraction!")
        return

    if use_rich:
        console.print(f"\n[bold]Papers to process:[/bold] {len(papers)}")
        console.print(f"[dim]Rate limit delay: {args.delay}s[/dim]")
    else:
        print(f"\nPapers to process: {len(papers)}")
        print(f"Rate limit delay: {args.delay}s")

    if args.dry_run:
        if use_rich:
            console.print("\n[yellow]DRY RUN - Papers that would be processed:[/yellow]")
            for p in papers[:20]:
                console.print(f"  [dim][{p['id']}][/dim] {p['title'][:60]}...")
            if len(papers) > 20:
                console.print(f"  [dim]... and {len(papers) - 20} more[/dim]")
        else:
            print("\nDRY RUN - Papers that would be processed:")
            for p in papers[:20]:
                print(f"  [{p['id']}] {p['title'][:60]}...")
            if len(papers) > 20:
                print(f"  ... and {len(papers) - 20} more")
        return

    # Check Ollama availability
    if use_rich:
        console.print("\n[bold]Checking Ollama availability...[/bold]")
    else:
        print("\nChecking Ollama availability...")

    if not check_ollama():
        if use_rich:
            console.print("[red]ERROR: Could not connect to Ollama[/red]")
            console.print("[dim]Make sure Ollama is running: ollama serve[/dim]")
        else:
            print("ERROR: Could not connect to Ollama")
            print("Make sure Ollama is running: ollama serve")
        return

    if use_rich:
        console.print("[green]Ollama is available[/green]\n")
    else:
        print("Ollama is available\n")

    # Run extraction
    if use_rich:
        result = asyncio.run(run_with_rich_display(
            papers=papers,
            delay=args.delay,
            force=args.force,
        ))
    else:
        result = asyncio.run(run_simple(
            papers=papers,
            delay=args.delay,
            force=args.force,
        ))

    # Summary
    if use_rich:
        summary_table = Table(title="Summary", show_header=False, box=None)
        summary_table.add_column("Metric", style="dim", width=18)
        summary_table.add_column("Value", style="bold")
        summary_table.add_row("Processed", str(result.processed))
        summary_table.add_row("Successful", f"[green]{result.success}[/green]")
        summary_table.add_row("Failed", f"[red]{result.failed}[/red]" if result.failed else "0")
        summary_table.add_row("High relevance", f"[cyan]{result.high_relevance}[/cyan]")
        summary_table.add_row("Medium relevance", f"[blue]{result.medium_relevance}[/blue]")

        console.print()
        console.print(Panel(summary_table, title="[bold green]Complete[/bold green]", border_style="green"))

        if result.errors:
            console.print("\n[red]Failed papers:[/red]")
            for paper_id, error in result.errors[:10]:
                console.print(f"  [{paper_id}] {error[:60]}...")
            if len(result.errors) > 10:
                console.print(f"  [dim]... and {len(result.errors) - 10} more[/dim]")

        # Updated stats
        stats = get_stats()
        console.print(f"\n[dim]Quick extraction done: {stats.with_quick_extraction} | "
                      f"Still need extraction: {stats.need_quick_extraction} | "
                      f"High relevance: {stats.high_relevance}[/dim]")
    else:
        print("\n" + "=" * 60)
        print("COMPLETE")
        print("=" * 60)
        print(f"Processed:       {result.processed}")
        print(f"Successful:      {result.success}")
        print(f"Failed:          {result.failed}")
        print(f"High relevance:  {result.high_relevance}")
        print(f"Medium relevance: {result.medium_relevance}")

        if result.errors:
            print("\nFailed papers:")
            for paper_id, error in result.errors[:10]:
                print(f"  [{paper_id}] {error}")

        stats = get_stats()
        print(f"\nQuick extraction done: {stats.with_quick_extraction} | "
              f"Still need extraction: {stats.need_quick_extraction}")


if __name__ == "__main__":
    main()
