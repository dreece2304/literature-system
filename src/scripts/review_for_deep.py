#!/usr/bin/env python3
"""
Intelligent review of quick extractions to flag papers for deep extraction.

Uses Ollama to review each paper's quick extraction summary and make intelligent
flagging decisions based on project context, paper type, and relevance scores.

This is smarter than simple "high relevance = flag" because Ollama considers:
- Whether the paper covers a gap in your research
- Whether similar papers have already been deep extracted
- Paper type (reviews vs. research articles)
- Specific methodological relevance

Usage:
    # Review and flag (default: high relevance papers without deep extraction)
    python -m scripts.review_for_deep

    # Dry run - see decisions without flagging
    python -m scripts.review_for_deep --dry-run

    # Include medium relevance papers
    python -m scripts.review_for_deep --include-medium

    # Limit papers to review
    python -m scripts.review_for_deep --limit 20

    # Review specific papers
    python -m scripts.review_for_deep --paper-ids 123 456 789

    # Show stats only
    python -m scripts.review_for_deep --stats
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from literature_core import get_session, Paper, get_logger, setup_logging
from literature_core.models import PaperContent, ProjectRelevance
from literature_core.constants import EnrichmentStatus
from services.paper_service import PaperService
from sqlalchemy import and_, or_

setup_logging()
logger = get_logger(__name__)


@dataclass
class ReviewDecision:
    """Decision for a single paper."""
    paper_id: int
    title: str
    decision: str  # "flag", "skip", "error"
    reasoning: str
    current_relevance: dict[str, str] = field(default_factory=dict)
    paper_type: Optional[str] = None
    topics: list[str] = field(default_factory=list)


@dataclass
class ReviewStats:
    """Statistics for the review batch."""
    total_candidates: int = 0
    high_relevance: int = 0
    medium_relevance: int = 0
    already_deep_extracted: int = 0
    missing_full_text: int = 0
    ready_for_review: int = 0


@dataclass
class ReviewResult:
    """Result of review batch."""
    reviewed: int = 0
    flagged: int = 0
    skipped: int = 0
    errors: int = 0
    decisions: list[ReviewDecision] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def get_stats() -> ReviewStats:
    """Get statistics on papers eligible for review."""
    stats = ReviewStats()

    with get_session() as session:
        # Papers with quick extraction
        quick_extracted = session.query(Paper).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.quick_extraction_date.isnot(None)
        )

        stats.total_candidates = quick_extracted.count()

        # Already deep extracted
        stats.already_deep_extracted = session.query(Paper).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.deep_extraction_date.isnot(None)
        ).count()

        # High relevance
        high_papers = session.query(ProjectRelevance.paper_id).filter(
            ProjectRelevance.relevance_level == "high"
        ).distinct().scalar_subquery()

        stats.high_relevance = session.query(Paper).filter(
            Paper.id.in_(high_papers)
        ).count()

        # Medium relevance
        medium_papers = session.query(ProjectRelevance.paper_id).filter(
            ProjectRelevance.relevance_level == "medium"
        ).distinct().scalar_subquery()

        stats.medium_relevance = session.query(Paper).filter(
            Paper.id.in_(medium_papers)
        ).count()

        # Has full text (via chunks)
        from literature_core.models import PaperChunk
        papers_with_text = session.query(PaperChunk.paper_id).distinct().scalar_subquery()

        # Ready for review: has quick extraction, no deep, has full text, high/medium relevance
        stats.ready_for_review = session.query(Paper).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.quick_extraction_date.isnot(None),
            PaperContent.deep_extraction_date.is_(None),
            Paper.id.in_(papers_with_text),
            or_(Paper.id.in_(high_papers), Paper.id.in_(medium_papers))
        ).count()

        # Missing full text (high/medium but no chunks)
        stats.missing_full_text = session.query(Paper).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.quick_extraction_date.isnot(None),
            PaperContent.deep_extraction_date.is_(None),
            ~Paper.id.in_(papers_with_text),
            or_(Paper.id.in_(high_papers), Paper.id.in_(medium_papers))
        ).count()

    return stats


def get_candidates(
    include_medium: bool = False,
    limit: int = 50,
    paper_ids: list[int] | None = None
) -> list[dict]:
    """Get papers ready for review.

    Returns papers that have:
    - Quick extraction done
    - No deep extraction yet
    - Full text available (has chunks)
    - High (or medium if include_medium) relevance
    """
    from literature_core.models import PaperChunk

    with get_session() as session:
        # Get papers with full text
        papers_with_text = session.query(PaperChunk.paper_id).distinct().scalar_subquery()

        # Get high relevance papers
        high_papers = session.query(ProjectRelevance.paper_id).filter(
            ProjectRelevance.relevance_level == "high"
        ).distinct().scalar_subquery()

        # Get medium relevance papers
        medium_papers = session.query(ProjectRelevance.paper_id).filter(
            ProjectRelevance.relevance_level == "medium"
        ).distinct().scalar_subquery()

        # Build query
        query = session.query(Paper).join(
            PaperContent, Paper.id == PaperContent.paper_id
        ).filter(
            PaperContent.quick_extraction_date.isnot(None),
            PaperContent.deep_extraction_date.is_(None),
            Paper.id.in_(papers_with_text)
        )

        # Filter by paper IDs if specified
        if paper_ids:
            query = query.filter(Paper.id.in_(paper_ids))
        else:
            # Filter by relevance
            if include_medium:
                query = query.filter(
                    or_(Paper.id.in_(high_papers), Paper.id.in_(medium_papers))
                )
            else:
                query = query.filter(Paper.id.in_(high_papers))

        # Limit and order
        papers = query.order_by(Paper.id.desc()).limit(limit).all()

        # Get relevance scores for each paper
        results = []
        for paper in papers:
            content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper.id
            ).first()

            relevances = session.query(ProjectRelevance).filter(
                ProjectRelevance.paper_id == paper.id
            ).all()

            results.append({
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "year": paper.year,
                "paper_type": content.paper_type if content else None,
                "topics": content.topics if content and isinstance(content.topics, list) else (json.loads(content.topics) if content and content.topics else []),
                "one_sentence_summary": content.one_sentence_summary if content else None,
                "relevances": {
                    r.project_name: {
                        "level": r.relevance_level,
                        "reason": r.relevance_summary or "",
                        "primary_use": getattr(r, 'primary_use', None) or ""
                    }
                    for r in relevances
                }
            })

        return results


def load_projects() -> list[dict]:
    """Load project definitions."""
    config = PaperService.load_projects_config()
    return [p for p in config.get("projects", []) if p.get("active", True)]


def build_review_prompt(paper: dict, projects: list[dict]) -> str:
    """Build the prompt for Ollama to review a paper."""

    project_context = "\n".join([
        f"- {p['name']}: {p['focus']}"
        for p in projects
    ])

    relevance_str = "\n".join([
        f"  - {proj}: {info['level']} ({info.get('reason', 'no reason given')})"
        for proj, info in paper['relevances'].items()
    ])

    prompt = f'''You are reviewing papers for deep extraction (detailed analysis).

ACTIVE RESEARCH PROJECTS:
{project_context}

PAPER TO REVIEW:
Title: {paper['title']}
Year: {paper['year']}
Type: {paper['paper_type'] or 'unknown'}
Topics: {', '.join(paper['topics']) if paper['topics'] else 'none extracted'}
Summary: {paper['one_sentence_summary'] or 'none'}

Current Relevance Scores:
{relevance_str}

DECISION CRITERIA:
Flag for deep extraction if:
- Paper provides novel methodology useful for active projects
- Paper contains specific data/results to cite or compare
- Paper fills a gap in our literature coverage
- Paper is a recent key reference in the field

Skip if:
- Paper is tangentially related (general background)
- Similar papers have already been deeply analyzed
- Paper is a review and we already have primary sources
- Low information density expected from full text

Respond with ONLY valid JSON:
{{
    "decision": "flag" or "skip",
    "reasoning": "Brief 1-2 sentence explanation"
}}'''

    return prompt


async def review_paper_with_ollama(paper: dict, projects: list[dict]) -> ReviewDecision:
    """Use Ollama to review a single paper."""
    import httpx

    prompt = build_review_prompt(paper, projects)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:7b-instruct-q5_K_M",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 200
                    }
                }
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("response", "").strip()

            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(text)

            return ReviewDecision(
                paper_id=paper["id"],
                title=paper["title"],
                decision=parsed.get("decision", "skip"),
                reasoning=parsed.get("reasoning", "No reasoning provided"),
                current_relevance={
                    k: v["level"] for k, v in paper["relevances"].items()
                },
                paper_type=paper.get("paper_type"),
                topics=paper.get("topics", [])
            )

    except json.JSONDecodeError as e:
        return ReviewDecision(
            paper_id=paper["id"],
            title=paper["title"],
            decision="error",
            reasoning=f"Failed to parse LLM response: {e}"
        )
    except Exception as e:
        return ReviewDecision(
            paper_id=paper["id"],
            title=paper["title"],
            decision="error",
            reasoning=f"Review failed: {e}"
        )


async def run_review(
    candidates: list[dict],
    projects: list[dict],
    dry_run: bool = False,
    delay: float = 0.5
) -> ReviewResult:
    """Run the review process with progress display."""
    import logging
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
    )

    console = Console()
    result = ReviewResult()
    start_time = time.time()

    # Suppress logging during progress
    logging.getLogger().setLevel(logging.WARNING)
    from loguru import logger as loguru_logger
    loguru_logger.disable("services")
    loguru_logger.disable("embeddings")

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
        task_id = progress.add_task("[cyan]Reviewing papers...", total=len(candidates))

        for paper in candidates:
            progress.update(task_id, description=f"[cyan]Reviewing [{paper['id']}]...")

            decision = await review_paper_with_ollama(paper, projects)
            result.decisions.append(decision)
            result.reviewed += 1

            if decision.decision == "flag":
                result.flagged += 1
                # Actually flag the paper unless dry run
                if not dry_run:
                    try:
                        PaperService.flag_for_deep_extraction(paper["id"])
                    except Exception as e:
                        logger.error(f"Failed to flag paper {paper['id']}: {e}")

                desc = f"[green]FLAG[/green] [{paper['id']}] {decision.reasoning[:40]}..."

            elif decision.decision == "skip":
                result.skipped += 1
                desc = f"[yellow]SKIP[/yellow] [{paper['id']}] {decision.reasoning[:40]}..."

            else:  # error
                result.errors += 1
                desc = f"[red]ERR[/red] [{paper['id']}] {decision.reasoning[:40]}..."

            progress.update(task_id, advance=1, description=desc)

            # Rate limiting
            if delay > 0 and result.reviewed < len(candidates):
                await asyncio.sleep(delay)

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    loguru_logger.enable("services")
    loguru_logger.enable("embeddings")

    result.elapsed_seconds = time.time() - start_time
    return result


def print_stats(stats: ReviewStats):
    """Print review statistics."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total with quick extraction", str(stats.total_candidates))
    table.add_row("Already deep extracted", str(stats.already_deep_extracted))
    table.add_row("High relevance papers", str(stats.high_relevance))
    table.add_row("Medium relevance papers", str(stats.medium_relevance))
    table.add_row("Ready for review (has full text)", str(stats.ready_for_review))
    table.add_row("Missing full text", str(stats.missing_full_text))

    console.print(Panel(table, title="Review Statistics", expand=False))


def print_results(result: ReviewResult, dry_run: bool = False):
    """Print review results."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    # Summary
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")

    summary.add_row("Papers reviewed", str(result.reviewed))
    summary.add_row("Flagged for deep extraction", f"[green]{result.flagged}[/green]")
    summary.add_row("Skipped", f"[yellow]{result.skipped}[/yellow]")
    summary.add_row("Errors", f"[red]{result.errors}[/red]" if result.errors else "0")
    summary.add_row("Duration", f"{result.elapsed_seconds:.1f}s")

    title = "Review Results (DRY RUN)" if dry_run else "Review Results"
    console.print(Panel(summary, title=title, expand=False))

    # Flagged papers
    if result.flagged > 0:
        console.print("\n[bold green]Papers flagged for deep extraction:[/bold green]")
        for d in result.decisions:
            if d.decision == "flag":
                console.print(f"  [{d.paper_id}] {d.title[:60]}...")
                console.print(f"       [dim]{d.reasoning}[/dim]")

    # Skipped papers (show a few)
    skipped = [d for d in result.decisions if d.decision == "skip"]
    if skipped:
        console.print("\n[bold yellow]Papers skipped (showing first 5):[/bold yellow]")
        for d in skipped[:5]:
            console.print(f"  [{d.paper_id}] {d.title[:60]}...")
            console.print(f"       [dim]{d.reasoning}[/dim]")
        if len(skipped) > 5:
            console.print(f"  ... and {len(skipped) - 5} more")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Intelligent review of papers for deep extraction"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Review but don't actually flag papers"
    )
    parser.add_argument(
        "--include-medium",
        action="store_true",
        help="Include medium relevance papers (default: high only)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum papers to review (default: 50)"
    )
    parser.add_argument(
        "--paper-ids",
        type=int,
        nargs="+",
        help="Specific paper IDs to review"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds between reviews for rate limiting (default: 0.5)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Stats mode
    if args.stats:
        stats = get_stats()
        if args.json:
            print(json.dumps({
                "total_candidates": stats.total_candidates,
                "already_deep_extracted": stats.already_deep_extracted,
                "high_relevance": stats.high_relevance,
                "medium_relevance": stats.medium_relevance,
                "ready_for_review": stats.ready_for_review,
                "missing_full_text": stats.missing_full_text
            }, indent=2))
        else:
            print_stats(stats)
        return

    # Load projects
    projects = load_projects()
    if not projects:
        print("No active projects found in data/projects.json")
        return

    # Get candidates
    candidates = get_candidates(
        include_medium=args.include_medium,
        limit=args.limit,
        paper_ids=args.paper_ids
    )

    if not candidates:
        print("No papers ready for review")
        print("(Papers need: quick extraction, no deep extraction, full text, high/medium relevance)")
        return

    from rich.console import Console
    console = Console()

    console.print(f"\n[bold]Reviewing {len(candidates)} papers...[/bold]")
    if args.dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]")
    console.print(f"Projects: {', '.join(p['name'] for p in projects)}\n")

    # Run review
    result = asyncio.run(run_review(
        candidates=candidates,
        projects=projects,
        dry_run=args.dry_run,
        delay=args.delay
    ))

    # Output results
    if args.json:
        print(json.dumps({
            "reviewed": result.reviewed,
            "flagged": result.flagged,
            "skipped": result.skipped,
            "errors": result.errors,
            "elapsed_seconds": result.elapsed_seconds,
            "decisions": [
                {
                    "paper_id": d.paper_id,
                    "title": d.title,
                    "decision": d.decision,
                    "reasoning": d.reasoning,
                    "paper_type": d.paper_type,
                    "topics": d.topics
                }
                for d in result.decisions
            ]
        }, indent=2))
    else:
        print_results(result, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
