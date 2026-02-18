#!/usr/bin/env python3
"""Continuous LLM extraction script for processing all papers (local only).

This script runs extraction continuously until all papers are processed.
It handles errors gracefully and can be resumed if interrupted.
Uses only local LLM backends (Ollama or vLLM).

Usage:
    # From project root with litai conda env
    mamba run -n litai python scripts/continuous_extraction.py

    # With options
    mamba run -n litai python scripts/continuous_extraction.py --batch-size 5 --delay 3

    # Force re-extraction of existing papers
    mamba run -n litai python scripts/continuous_extraction.py --force

    # Use vLLM with YaRN for longer context (start vLLM server first)
    mamba run -n litai python scripts/continuous_extraction.py --backend vllm
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from services.extraction_service import ExtractionService  # noqa: E402


# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    global shutdown_requested
    print("\n\nShutdown requested. Finishing current paper...")
    shutdown_requested = True


async def extract_with_retry(
    paper_id: int,
    backend: str = "auto",
    max_retries: int = 3,
    verbose: bool = False
) -> tuple[bool, str]:
    """Extract a paper with retry logic.

    Returns:
        Tuple of (success, message)
    """
    for attempt in range(max_retries):
        try:
            result = await ExtractionService.extract_paper(
                paper_id=paper_id,
                backend=backend,
                force=False,
                verbose=verbose
            )

            if result.success:
                if "Already extracted" in (result.error or ""):
                    return True, "skipped"
                return True, "extracted"
            else:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return False, result.error or "Unknown error"

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return False, str(e)

    return False, "Max retries exceeded"


async def continuous_extraction(
    batch_size: int = 10,
    delay: float = 2.0,
    backend: str = "auto",
    force: bool = False,
    max_errors: int = 10,
    verbose: bool = False
):
    """Run continuous extraction until all papers are processed.

    Args:
        batch_size: Papers to process before status update
        delay: Seconds between extractions
        backend: LLM backend (ollama, claude, auto)
        force: Re-extract even if extraction exists
        max_errors: Stop after this many consecutive errors
        verbose: Show detailed output
    """
    global shutdown_requested

    print("=" * 70)
    print("CONTINUOUS EXTRACTION")
    print("=" * 70)

    # Check LLM status (local only)
    llm_status = ExtractionService.get_llm_status()
    print(f"\nLLM Status (local only):")
    print(f"  Ollama: {'Available' if llm_status['ollama']['available'] else 'Not available'}")
    print(f"  vLLM: {'Available' if llm_status['vllm']['available'] else 'Not available'}")
    print(f"  Using: {backend}")

    if not llm_status['recommended'] and backend == "auto":
        print("\nNo LLM backend available. Please start Ollama or vLLM server.")
        return

    # Get initial status
    status = ExtractionService.get_extraction_status()
    print(f"\nInitial Status:")
    print(f"  Total papers: {status.total_papers}")
    print(f"  Already extracted: {status.papers_with_extraction}")
    print(f"  Needing extraction: {status.papers_needing_extraction}")
    print(f"  Coverage: {status.extraction_coverage_percent:.1f}%")

    if status.papers_needing_extraction == 0 and not force:
        print("\nAll papers already extracted!")
        return

    print(f"\nSettings:")
    print(f"  Batch size: {batch_size}")
    print(f"  Delay between papers: {delay}s")
    print(f"  Force re-extraction: {force}")
    print(f"\nPress Ctrl+C to stop gracefully")
    print("-" * 70)

    # Track statistics
    stats = {
        "extracted": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "start_time": time.time(),
        "consecutive_errors": 0,
    }

    batch_count = 0

    while not shutdown_requested:
        # Get next batch of papers to extract
        papers = ExtractionService.get_papers_needing_extraction(limit=batch_size)

        if not papers:
            print("\nNo more papers to extract!")
            break

        batch_count += 1
        batch_start = time.time()

        for paper in papers:
            if shutdown_requested:
                break

            paper_id = paper['id']
            title = paper['title'][:50] + "..." if len(paper['title']) > 50 else paper['title']

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Paper {paper_id}: {title}")

            success, message = await extract_with_retry(
                paper_id=paper_id,
                backend=backend,
                verbose=verbose
            )

            if success:
                if message == "extracted":
                    stats["extracted"] += 1
                    stats["consecutive_errors"] = 0
                    print(f"  ✓ Extracted successfully")
                else:
                    stats["skipped"] += 1
                    print(f"  ⊘ Already extracted")
            else:
                stats["failed"] += 1
                stats["consecutive_errors"] += 1
                stats["errors"].append(f"Paper {paper_id}: {message}")
                print(f"  ✗ Failed: {message}")

                if stats["consecutive_errors"] >= max_errors:
                    print(f"\n\nStopping: {max_errors} consecutive errors")
                    shutdown_requested = True
                    break

            # Rate limiting
            if delay > 0 and not shutdown_requested:
                await asyncio.sleep(delay)

        # Batch summary
        batch_time = time.time() - batch_start
        total_time = time.time() - stats["start_time"]
        processed = stats["extracted"] + stats["skipped"] + stats["failed"]

        # Get updated status
        status = ExtractionService.get_extraction_status()
        remaining = status.papers_needing_extraction

        print(f"\n--- Batch {batch_count} Complete ---")
        print(f"Session: {stats['extracted']} extracted, {stats['skipped']} skipped, {stats['failed']} failed")
        print(f"Remaining: {remaining} papers ({status.extraction_coverage_percent:.1f}% coverage)")
        print(f"Time: {batch_time:.1f}s this batch, {total_time/60:.1f}min total")

        if processed > 0:
            avg_time = total_time / processed
            eta_minutes = (remaining * avg_time) / 60
            print(f"ETA: ~{eta_minutes:.0f} minutes for remaining papers")

    # Final summary
    total_time = time.time() - stats["start_time"]
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"\nResults:")
    print(f"  Extracted: {stats['extracted']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Total time: {total_time/60:.1f} minutes")

    if stats['errors']:
        print(f"\nErrors ({len(stats['errors'])} total):")
        for err in stats['errors'][:5]:
            print(f"  - {err}")
        if len(stats['errors']) > 5:
            print(f"  ... and {len(stats['errors']) - 5} more")

    # Final status
    status = ExtractionService.get_extraction_status()
    print(f"\nFinal Status:")
    print(f"  Coverage: {status.extraction_coverage_percent:.1f}%")
    print(f"  Remaining: {status.papers_needing_extraction} papers")


def main():
    parser = argparse.ArgumentParser(
        description="Continuously extract papers using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=10,
        help="Papers to process before status update (default: 10)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=2.0,
        help="Seconds between extractions (default: 2.0)"
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "vllm", "auto"],
        default="auto",
        help="LLM backend to use - local only (default: auto)"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-extract papers that already have extractions"
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=10,
        help="Stop after this many consecutive errors (default: 10)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including prompts"
    )

    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run extraction
    asyncio.run(continuous_extraction(
        batch_size=args.batch_size,
        delay=args.delay,
        backend=args.backend,
        force=args.force,
        max_errors=args.max_errors,
        verbose=args.verbose
    ))


if __name__ == "__main__":
    main()
