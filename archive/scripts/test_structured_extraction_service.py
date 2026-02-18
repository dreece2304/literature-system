#!/usr/bin/env python
"""Test the ChunkedExtractionService.

Run with:
    python scripts/test_structured_extraction_service.py
    python scripts/test_structured_extraction_service.py --paper-id 6
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from tqdm import tqdm
from services import ChunkedExtractionService


# Test papers of varying lengths
TEST_PAPER_IDS = [6, 5, 2, 7, 11, 40]


def test_extraction(paper_id: int, force: bool = False, quiet: bool = False):
    """Test extraction and storage for a paper."""
    def out(msg):
        if quiet:
            tqdm.write(msg)
        else:
            print(msg)

    if not quiet:
        out(f"\n{'='*70}")
        out(f"Paper {paper_id}")
        out("=" * 70)

    # Check if already extracted
    status = ChunkedExtractionService.get_extraction_status(paper_id)
    if status:
        if not quiet:
            out(f"Already extracted: {status['method']}")
            out(f"  Chunks: {status['chunk_count']}")
            out(f"  Tables: {status['table_count']}")
            out(f"  Figures: {status['figure_count']}")
            out(f"  Words: {status['word_count']:,}")
        if not force:
            return status

    # Extract
    if not quiet:
        out("Extracting...")
    result = ChunkedExtractionService.extract_and_store(paper_id, force=force)

    if not quiet:
        out(f"Success: {result.success}")
        out(f"Chunks: {result.chunk_count}")
        out(f"Tables: {result.table_count}")
        out(f"Figures: {result.figure_count}")
        out(f"Words: {result.word_count:,}")
        out(f"Pages: {result.page_count}")

    if result.error:
        out(f"Error: {result.error}")

    return result


def test_prepare_for_claude(paper_id: int, max_preview: int = 3000):
    """Test Claude formatting."""
    print(f"\n{'='*70}")
    print(f"CLAUDE FORMAT - Paper {paper_id}")
    print("=" * 70)

    # Get status first
    status = ChunkedExtractionService.get_extraction_status(paper_id)
    if not status:
        print("Not extracted yet - extracting first...")
        ChunkedExtractionService.extract_and_store(paper_id)
        status = ChunkedExtractionService.get_extraction_status(paper_id)

    word_count = status['word_count']
    chunk_count = status['chunk_count']
    print(f"Word count: {word_count:,}")
    print(f"Chunks: {chunk_count}")
    print()

    # Show full content
    content = ChunkedExtractionService.prepare_for_claude(paper_id)

    print(f"Output size: {len(content):,} chars (~{len(content)//4:,} tokens)")
    print("-" * 70)
    print(content[:max_preview])
    if len(content) > max_preview:
        print(f"\n... [{len(content) - max_preview:,} more chars]")
    print("-" * 70)


def test_chunk_by_chunk(paper_id: int, max_preview: int = 500):
    """Test retrieving chunks one by one."""
    print(f"\n{'='*70}")
    print(f"CHUNK-BY-CHUNK - Paper {paper_id}")
    print("=" * 70)

    status = ChunkedExtractionService.get_extraction_status(paper_id)
    if not status:
        print("Not extracted yet!")
        return

    print(f"Total chunks: {status['chunk_count']}")
    print()

    for i in range(status['chunk_count']):
        chunk = ChunkedExtractionService.get_chunk(paper_id, i)
        print(f"Chunk {i+1}/{chunk['total_chunks']}: {chunk['word_count']:,} words")
        print("-" * 50)
        preview = chunk['content'][:max_preview]
        print(preview)
        if len(chunk['content']) > max_preview:
            print(f"... [{len(chunk['content']) - max_preview:,} more chars]")
        print()


def main():
    parser = argparse.ArgumentParser(description="Test ChunkedExtractionService")
    parser.add_argument("--paper-id", "-p", type=int, help="Test specific paper")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-extraction")
    parser.add_argument("--claude", "-c", action="store_true", help="Show Claude format")
    parser.add_argument("--chunks", action="store_true", help="Show chunk-by-chunk")
    parser.add_argument("--all", "-a", action="store_true", help="Test all papers")
    args = parser.parse_args()

    if args.paper_id:
        test_extraction(args.paper_id, force=args.force)
        if args.claude:
            test_prepare_for_claude(args.paper_id)
        if args.chunks:
            test_chunk_by_chunk(args.paper_id)
    elif args.all:
        print("Testing extraction on multiple papers...")
        for pid in tqdm(TEST_PAPER_IDS, desc="Extracting", unit="paper"):
            try:
                test_extraction(pid, force=args.force, quiet=True)
            except Exception as e:
                tqdm.write(f"Paper {pid} Error: {e}")

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        # Show all extraction statuses
        for pid in TEST_PAPER_IDS:
            status = ChunkedExtractionService.get_extraction_status(pid)
            if status:
                print(f"Paper {pid}: {status['chunk_count']} chunks, "
                      f"{status['table_count']} tables, {status['word_count']:,} words")
            else:
                print(f"Paper {pid}: Not extracted")
    else:
        # Default: show what needs extraction
        print("Papers needing extraction:")
        needs = ChunkedExtractionService.get_papers_needing_extraction(limit=10)
        if needs:
            for pid in needs:
                print(f"  - Paper {pid}")
            print(f"\nRun with --all to extract all, or --paper-id N for specific paper")
        else:
            print("  None - all papers with PDFs have been extracted")


if __name__ == "__main__":
    main()
