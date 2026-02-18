#!/usr/bin/env python3
"""Deep extraction batch processing with auto-flagging.

Scans quick extractions for high-relevance papers and runs deep extraction
with Ollama. Shows detailed progress with in-place updates.

Usage:
    # Default: auto-flag and extract papers with high relevance or rating >= 4
    python -m scripts.deep_extract_batch

    # Dry run to see what would be extracted
    python -m scripts.deep_extract_batch --dry-run

    # Process only already-flagged papers (skip scan/flag phases)
    python -m scripts.deep_extract_batch --process-flagged

    # Specific papers by ID
    python -m scripts.deep_extract_batch --paper-ids 123 456 789

    # Lower threshold: medium relevance OR rating >= 3
    python -m scripts.deep_extract_batch --relevance-threshold medium --min-rating 3

    # Limit to 20 papers with 2s delay between
    python -m scripts.deep_extract_batch --limit 20 --delay 2.0
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
import traceback
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime
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
from rich.live import Live
from rich.layout import Layout
from rich import box

from literature_core import (
    get_session, get_logger, setup_logging,
    Paper, PaperContent, PaperChunk, ProjectRelevance, EnrichmentStatus,
)
from services.extraction_service import ExtractionService, PaperExtraction, ProgressCallback
from services.paper_service import PaperService

setup_logging()
logger = get_logger(__name__)

# Global for graceful shutdown
_shutdown_requested = False


@dataclass
class CandidatePaper:
    """Paper identified for deep extraction."""
    paper_id: int
    title: str
    rating: Optional[int]
    project_relevances: dict[str, str]  # project_name -> relevance_level
    chunk_count: int
    has_pdf: bool
    has_deep_extraction: bool
    flag_reason: str  # "high_relevance" | "high_rating" | "both"


@dataclass
class ScanResult:
    """Result of scanning for candidates."""
    candidates: list[CandidatePaper] = field(default_factory=list)
    by_relevance: int = 0
    by_rating: int = 0
    already_extracted: int = 0
    total_scanned: int = 0
    with_chunks: int = 0
    with_pdf_no_chunks: int = 0
    no_pdf: int = 0


@dataclass
class FlagResult:
    """Result of flagging papers."""
    flagged: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


@dataclass
class BatchExtractionResult:
    """Extended extraction result for CLI."""
    papers_processed: int = 0
    papers_extracted: int = 0
    papers_failed: int = 0
    papers_skipped: int = 0
    total_chunks: int = 0
    elapsed_seconds: float = 0
    errors: list[dict] = field(default_factory=list)
    extracted_papers: list[dict] = field(default_factory=list)


def get_project_relevances_from_table(session, paper_id: int) -> dict[str, str]:
    """Get project relevances from ProjectRelevance table.

    Returns dict like: {"thesis": "high", "paper2": "medium"}
    """
    records = session.query(ProjectRelevance).filter(
        ProjectRelevance.paper_id == paper_id
    ).all()

    return {r.project_name: r.relevance_level or "none" for r in records}


def scan_for_candidates(
    min_rating: int = 4,
    relevance_threshold: str = "high",
    limit: int = 50,
    console: Optional[Console] = None
) -> ScanResult:
    """Scan papers with quick extraction for deep extraction candidates.

    Criteria (OR logic):
    1. High relevance to ANY project (from ProjectRelevance table)
    2. rating >= min_rating

    Returns papers sorted by priority (high relevance first, then by rating).
    """
    result = ScanResult()
    thresholds = ["high"] if relevance_threshold == "high" else ["high", "medium"]

    with get_session() as session:
        # Get papers with quick extraction but no deep extraction
        papers = session.query(Paper, PaperContent).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.extraction_depth == "abstract_only",  # Has quick
        ).all()

        result.total_scanned = len(papers)

        candidates = []
        for paper, content in papers:
            # Check if already has deep extraction
            has_deep = content.deep_extraction_date is not None or content.key_findings is not None

            if has_deep:
                result.already_extracted += 1
                continue

            # Get project relevances from ProjectRelevance table
            relevances = get_project_relevances_from_table(session, paper.id)

            # Check criteria
            has_relevant = any(r in thresholds for r in relevances.values())
            high_rating = paper.rating is not None and paper.rating >= min_rating

            if not has_relevant and not high_rating:
                continue

            # Determine flag reason
            if has_relevant and high_rating:
                flag_reason = "both"
                result.by_relevance += 1
                result.by_rating += 1
            elif has_relevant:
                flag_reason = "high_relevance"
                result.by_relevance += 1
            else:
                flag_reason = "high_rating"
                result.by_rating += 1

            # Get chunk count and PDF status
            chunk_count = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper.id
            ).count()
            has_pdf = paper.file_path is not None and paper.file_path != ""

            # Track PDF/chunk stats
            if chunk_count > 0:
                result.with_chunks += 1
            elif has_pdf:
                result.with_pdf_no_chunks += 1
            else:
                result.no_pdf += 1

            candidates.append(CandidatePaper(
                paper_id=paper.id,
                title=paper.title,
                rating=paper.rating,
                project_relevances=relevances,
                chunk_count=chunk_count,
                has_pdf=has_pdf,
                has_deep_extraction=has_deep,
                flag_reason=flag_reason
            ))

        # Sort: papers with chunks first, then high relevance, then by rating
        candidates.sort(key=lambda c: (
            0 if c.chunk_count > 0 else 1,  # Chunks first
            0 if c.flag_reason in ["high_relevance", "both"] else 1,
            -(c.rating or 0)
        ))

        result.candidates = candidates[:limit]

    return result


def get_flagged_papers(limit: int = 50) -> list[CandidatePaper]:
    """Get papers already flagged as NEEDS_DEEP_EXTRACTION."""
    candidates = []

    with get_session() as session:
        papers = session.query(Paper, PaperContent).outerjoin(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            Paper.enrichment_status == EnrichmentStatus.NEEDS_DEEP_EXTRACTION
        ).limit(limit).all()

        for paper, content in papers:
            relevances = get_project_relevances_from_table(session, paper.id)

            chunk_count = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper.id
            ).count()
            has_pdf = paper.file_path is not None and paper.file_path != ""

            candidates.append(CandidatePaper(
                paper_id=paper.id,
                title=paper.title,
                rating=paper.rating,
                project_relevances=relevances,
                chunk_count=chunk_count,
                has_pdf=has_pdf,
                has_deep_extraction=False,
                flag_reason="already_flagged"
            ))

    return candidates


def flag_candidates(
    candidates: list[CandidatePaper],
    dry_run: bool = False
) -> FlagResult:
    """Flag papers for deep extraction.

    In dry-run mode, just return what would be flagged.
    """
    result = FlagResult()
    paper_ids = [c.paper_id for c in candidates]

    if not paper_ids:
        return result

    if dry_run:
        result.flagged = paper_ids
        return result

    try:
        flag_result = PaperService.batch_flag_for_deep_extraction(paper_ids)
        result.flagged = flag_result.get("flagged_ids", [])
        result.errors = flag_result.get("errors", [])
    except Exception as e:
        result.errors.append({"error": str(e), "traceback": traceback.format_exc()})

    return result


async def extract_papers(
    candidates: list[CandidatePaper],
    backend: str = "auto",
    delay: float = 1.0,
    force: bool = False,
    verbose: bool = False,
    console: Optional[Console] = None
) -> BatchExtractionResult:
    """Run deep extractions with progress display showing pass-level progress."""
    import logging

    global _shutdown_requested
    result = BatchExtractionResult()
    console = console or Console()

    if not candidates:
        return result

    start_time = time.time()

    # Suppress logging during progress display
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("services").setLevel(logging.ERROR)
    logging.getLogger("embeddings").setLevel(logging.ERROR)
    logging.getLogger("literature_core").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    # Also suppress loguru (used by embeddings/services modules)
    from loguru import logger as loguru_logger
    loguru_logger.disable("services")
    loguru_logger.disable("embeddings")
    loguru_logger.disable("embeddings.generator")
    loguru_logger.disable("embeddings.vectorstore")

    # State for pass progress display
    current_pass_info = {"pass": 0, "current": 0, "total": 0, "message": ""}

    def make_progress_callback(paper_id: int, chunk_count: int):
        """Create a progress callback for a specific paper."""
        def callback(pass_num: int, current: int, total: int, message: str):
            current_pass_info["pass"] = pass_num
            current_pass_info["current"] = current
            current_pass_info["total"] = total
            current_pass_info["message"] = message
        return callback

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
        expand=False,
    ) as progress:
        # Overall paper progress
        papers_task = progress.add_task("[cyan]Papers", total=len(candidates))
        # Per-paper pass progress (hidden initially)
        pass_task = progress.add_task("[dim]Pass 1: chunks", total=100, visible=True)

        for i, candidate in enumerate(candidates):
            if _shutdown_requested:
                console.print("\n[yellow]Shutdown requested, stopping...[/yellow]")
                break

            # Build description with paper info
            rel_parts = []
            for proj, level in candidate.project_relevances.items():
                if level == "high":
                    rel_parts.append(f"{proj}=H")
                elif level == "medium":
                    rel_parts.append(f"{proj}=M")
            rel_str = ",".join(rel_parts) if rel_parts else "-"

            # Reset pass progress for new paper
            progress.reset(pass_task)
            progress.update(
                pass_task,
                total=candidate.chunk_count + 1,  # chunks + consolidation
                completed=0,
                description=f"[dim]Pass 1: 0/{candidate.chunk_count} chunks"
            )

            progress.update(
                papers_task,
                description=f"[cyan][{candidate.paper_id}] {candidate.title[:40]}..."
            )

            # Create callback that updates the pass progress bar
            def progress_callback(pass_num: int, current: int, total: int, message: str):
                if pass_num == 1:
                    # Pass 1: chunk extraction
                    progress.update(
                        pass_task,
                        completed=current,
                        description=f"[dim]Pass 1: {current}/{total} chunks"
                    )
                else:
                    # Pass 2: consolidation
                    progress.update(
                        pass_task,
                        completed=candidate.chunk_count + 1,
                        description=f"[dim]Pass 2: consolidating..."
                    )

            try:
                # Run extraction with progress callback
                extraction = await ExtractionService.extract_paper_deep(
                    paper_id=candidate.paper_id,
                    backend=backend,
                    force=force,
                    verbose=verbose,
                    progress_callback=progress_callback
                )

                result.papers_processed += 1
                result.total_chunks += candidate.chunk_count

                if extraction.success:
                    if extraction.error and "Already" in extraction.error:
                        result.papers_skipped += 1
                        desc = f"[yellow]○[/yellow] [{candidate.paper_id}] skipped (already done)"
                    else:
                        result.papers_extracted += 1
                        result.extracted_papers.append({
                            "paper_id": candidate.paper_id,
                            "title": candidate.title
                        })
                        desc = f"[green]✓[/green] [{candidate.paper_id}] {candidate.chunk_count}ch | rel:{rel_str}"
                else:
                    result.papers_failed += 1
                    result.errors.append({
                        "paper_id": candidate.paper_id,
                        "title": candidate.title,
                        "error": extraction.error
                    })
                    desc = f"[red]✗[/red] [{candidate.paper_id}] {extraction.error or 'failed'}..."[:60]

                progress.update(papers_task, advance=1, description=desc)

                # Rate limiting
                if delay > 0 and i < len(candidates) - 1:
                    await asyncio.sleep(delay)

            except Exception as e:
                result.papers_failed += 1
                result.errors.append({
                    "paper_id": candidate.paper_id,
                    "title": candidate.title,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })

                desc = f"[red]✗[/red] [{candidate.paper_id}] {str(e)[:40]}..."
                progress.update(papers_task, advance=1, description=desc)

        # Hide pass progress when done
        progress.update(pass_task, visible=False)

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("services").setLevel(logging.INFO)
    logging.getLogger("embeddings").setLevel(logging.INFO)
    logging.getLogger("literature_core").setLevel(logging.INFO)
    loguru_logger.enable("services")
    loguru_logger.enable("embeddings")

    result.elapsed_seconds = time.time() - start_time
    return result


def print_summary(
    scan_result: Optional[ScanResult],
    flag_result: Optional[FlagResult],
    extract_result: Optional[BatchExtractionResult],
    json_output: bool = False,
    console: Optional[Console] = None
):
    """Print final summary."""
    console = console or Console()

    if json_output:
        output = {
            "scan": asdict(scan_result) if scan_result else None,
            "flag": asdict(flag_result) if flag_result else None,
            "extraction": asdict(extract_result) if extract_result else None,
        }
        console.print(json.dumps(output, indent=2, default=str))
        return

    console.print()
    console.print(Panel("Summary", style="bold blue"))

    # Summary table
    summary = Table(show_header=False, box=box.SIMPLE)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right")

    if scan_result:
        summary.add_row("Papers scanned", str(scan_result.total_scanned))
        summary.add_row("Candidates found", str(len(scan_result.candidates)))
        summary.add_row("  - By relevance", str(scan_result.by_relevance))
        summary.add_row("  - By rating", str(scan_result.by_rating))
        summary.add_row("Already extracted", str(scan_result.already_extracted))

    if flag_result:
        summary.add_row("Papers flagged", str(len(flag_result.flagged)))

    if extract_result:
        summary.add_row("", "")  # Spacer
        summary.add_row("Papers processed", str(extract_result.papers_processed))
        summary.add_row("  - Extracted", str(extract_result.papers_extracted))
        summary.add_row("  - Failed", str(extract_result.papers_failed))
        summary.add_row("  - Skipped", str(extract_result.papers_skipped))
        summary.add_row("Total chunks", str(extract_result.total_chunks))
        summary.add_row("Elapsed time", f"{extract_result.elapsed_seconds:.1f}s")

    console.print(summary)

    # Errors
    if extract_result and extract_result.errors:
        console.print()
        console.print(Panel("Errors", style="bold red"))
        for err in extract_result.errors[:10]:  # Show first 10
            console.print(f"  Paper {err['paper_id']}: {err.get('error', 'Unknown')}")
        if len(extract_result.errors) > 10:
            console.print(f"  ... and {len(extract_result.errors) - 10} more")


def check_ollama_available() -> bool:
    """Check if Ollama is available for extraction."""
    try:
        from config.ai_settings import OllamaSettings
        import httpx

        settings = OllamaSettings()
        response = httpx.get(f"{settings.host}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def main():
    """Main entry point."""
    global _shutdown_requested

    parser = argparse.ArgumentParser(
        description="Batch deep extraction with auto-flagging based on relevance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Selection Mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--process-flagged", action="store_true",
        help="Only process papers already flagged as NEEDS_DEEP_EXTRACTION"
    )
    mode_group.add_argument(
        "--paper-ids", nargs="+", type=int,
        help="Specific paper IDs to process (bypasses selection logic)"
    )

    # Criteria
    parser.add_argument(
        "--min-rating", type=int, default=4,
        help="Minimum star rating to auto-flag (default: 4)"
    )
    parser.add_argument(
        "--relevance-threshold", type=str, default="high",
        choices=["high", "medium"],
        help="Minimum relevance level to auto-flag (default: high)"
    )

    # Processing
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Maximum papers to process (default: 50)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between extractions for rate limiting (default: 1.0)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-extract papers that already have deep extractions"
    )
    parser.add_argument(
        "--backend", choices=["ollama", "auto"], default="auto",
        help="LLM backend for extraction (default: auto)"
    )

    # Output modes
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and flag papers, but don't run extractions"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results in JSON format"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed extraction output"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Minimal output (errors only)"
    )

    args = parser.parse_args()

    console = Console(quiet=args.quiet)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        global _shutdown_requested
        _shutdown_requested = True
        console.print("\n[yellow]Interrupt received, finishing current paper...[/yellow]")

    signal.signal(signal.SIGINT, signal_handler)

    # Header
    if not args.json and not args.quiet:
        console.print(Panel(
            "[bold]Deep Extraction Batch Processing[/bold]\n"
            f"Relevance threshold: {args.relevance_threshold} | "
            f"Min rating: {args.min_rating} | "
            f"Limit: {args.limit}",
            style="blue"
        ))

    # Check Ollama availability (unless dry-run)
    if not args.dry_run:
        if not args.quiet:
            console.print("\n[dim]Checking Ollama availability...[/dim]")
        if not check_ollama_available():
            console.print("[red]Error: Ollama is not available. Please start Ollama first.[/red]")
            console.print("[dim]Run: ollama serve[/dim]")
            sys.exit(1)
        if not args.quiet:
            console.print("[green]Ollama is available[/green]")

    scan_result: Optional[ScanResult] = None
    flag_result: Optional[FlagResult] = None
    extract_result: Optional[BatchExtractionResult] = None

    # Phase 1: Get candidates
    if args.paper_ids:
        # Manual paper IDs
        if not args.quiet:
            console.print(f"\n[bold]Phase 1/3:[/bold] Using {len(args.paper_ids)} specified paper IDs")
        candidates = []
        with get_session() as session:
            for pid in args.paper_ids:
                paper = session.query(Paper).filter(Paper.id == pid).first()
                if paper:
                    relevances = get_project_relevances_from_table(session, pid)
                    chunk_count = session.query(PaperChunk).filter(PaperChunk.paper_id == pid).count()
                    has_pdf = paper.file_path is not None and paper.file_path != ""
                    candidates.append(CandidatePaper(
                        paper_id=pid,
                        title=paper.title,
                        rating=paper.rating,
                        project_relevances=relevances,
                        chunk_count=chunk_count,
                        has_pdf=has_pdf,
                        has_deep_extraction=False,
                        flag_reason="manual"
                    ))
                else:
                    console.print(f"[yellow]Paper {pid} not found[/yellow]")

    elif args.process_flagged:
        # Process already-flagged papers
        if not args.quiet:
            console.print("\n[bold]Phase 1/3:[/bold] Getting flagged papers...")
        candidates = get_flagged_papers(limit=args.limit)
        if not args.quiet:
            console.print(f"  Found {len(candidates)} flagged papers")

    else:
        # Auto-flag mode: scan and flag
        if not args.quiet:
            console.print("\n[bold]Phase 1/3:[/bold] Scanning for candidates...")

        scan_result = scan_for_candidates(
            min_rating=args.min_rating,
            relevance_threshold=args.relevance_threshold,
            limit=args.limit,
            console=console
        )

        if not args.quiet:
            console.print(f"  Scanned: {scan_result.total_scanned} papers with quick extraction")
            console.print(f"  Found: {scan_result.by_relevance} by {args.relevance_threshold} relevance")
            console.print(f"  Found: {scan_result.by_rating} by rating >= {args.min_rating}")
            console.print(f"  Already extracted: {scan_result.already_extracted}")
            console.print(f"  [green]Total candidates: {len(scan_result.candidates)}[/green]")
            # PDF/chunk status
            console.print(f"    - Ready (have chunks): {scan_result.with_chunks}")
            console.print(f"    - Have PDF, need chunks: {scan_result.with_pdf_no_chunks}")
            console.print(f"    - No PDF: {scan_result.no_pdf}")

            if scan_result.with_pdf_no_chunks > 0 and scan_result.with_chunks == 0:
                console.print(f"\n  [yellow]Note: {scan_result.with_pdf_no_chunks} papers have PDFs but need chunk processing.[/yellow]")
                console.print(f"  [dim]Run: process_pdf_queue to extract text chunks first.[/dim]")

        candidates = scan_result.candidates

        # Phase 2: Flag papers
        if candidates:
            if not args.quiet:
                console.print(f"\n[bold]Phase 2/3:[/bold] Flagging {len(candidates)} papers...")

            # Suppress logging during flagging
            logging.getLogger("services").setLevel(logging.ERROR)
            logging.getLogger("services.paper_service").setLevel(logging.ERROR)
            flag_result = flag_candidates(candidates, dry_run=args.dry_run)
            logging.getLogger("services").setLevel(logging.INFO)
            logging.getLogger("services.paper_service").setLevel(logging.INFO)

            if not args.quiet:
                if args.dry_run:
                    console.print(f"  [dim]Would flag {len(flag_result.flagged)} papers (dry-run)[/dim]")
                else:
                    console.print(f"  [green]Flagged {len(flag_result.flagged)} papers[/green]")

    # Phase 3: Run extractions
    if not candidates:
        if not args.quiet:
            console.print("\n[yellow]No papers to process[/yellow]")
    elif args.dry_run:
        if not args.quiet:
            console.print("\n[bold]Phase 3/3:[/bold] [dim]Skipped (dry-run mode)[/dim]")
            console.print("\n[bold]Papers that would be extracted:[/bold]")
            for c in candidates[:20]:
                rel_str = ", ".join(f"{k}={v}" for k, v in c.project_relevances.items()) or "none"
                chunk_status = f"{c.chunk_count} chunks" if c.chunk_count > 0 else ("has PDF" if c.has_pdf else "no PDF")
                console.print(f"  [{c.paper_id}] {c.title[:55]}... ({chunk_status}, {rel_str})")
            if len(candidates) > 20:
                console.print(f"  ... and {len(candidates) - 20} more")
    else:
        if not args.quiet:
            console.print(f"\n[bold]Phase 3/3:[/bold] Running deep extractions...")
            console.print()

        extract_result = asyncio.run(extract_papers(
            candidates=candidates,
            backend=args.backend,
            delay=args.delay,
            force=args.force,
            verbose=args.verbose,
            console=console
        ))

    # Summary
    print_summary(
        scan_result=scan_result,
        flag_result=flag_result,
        extract_result=extract_result,
        json_output=args.json,
        console=console
    )


if __name__ == "__main__":
    main()
