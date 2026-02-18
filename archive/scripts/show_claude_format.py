#!/usr/bin/env python
"""Show Claude-formatted extraction for papers.

Run with:
    python scripts/show_claude_format.py 6       # Show Paper 6
    python scripts/show_claude_format.py 7 2000  # Paper 7, max 2000 chars preview
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from services import ChunkedExtractionService


def show_claude_format(paper_id: int, max_preview: int = 3000):
    """Show Claude-formatted output for a paper."""
    # Check if extracted
    status = ChunkedExtractionService.get_extraction_status(paper_id)
    if not status:
        print(f"Paper {paper_id} not extracted yet. Extracting...")
        result = ChunkedExtractionService.extract_and_store(paper_id)
        if not result.success:
            print(f"Error: {result.error}")
            return

    # Get Claude format
    claude_output = ChunkedExtractionService.prepare_for_claude(paper_id)

    print(f"Paper {paper_id}")
    print("=" * 80)

    # Show preview
    if len(claude_output) > max_preview:
        print(claude_output[:max_preview])
        print()
        print(f"... [{len(claude_output) - max_preview:,} more characters]")
    else:
        print(claude_output)

    print()
    print("=" * 80)
    print(f"Total output: {len(claude_output):,} characters ({len(claude_output.split()):,} words)")


if __name__ == "__main__":
    paper_id = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    max_preview = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    show_claude_format(paper_id, max_preview)
