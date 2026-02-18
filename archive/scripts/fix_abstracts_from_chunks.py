#!/usr/bin/env python
"""Fix paper abstracts using content from PDF chunks.

Many papers have incorrect/duplicate abstracts in the database.
This script extracts the correct abstract from the chunked PDF content.

Run with:
    python scripts/fix_abstracts_from_chunks.py          # Dry run
    python scripts/fix_abstracts_from_chunks.py --apply  # Apply changes
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import argparse
from sqlalchemy import text
from literature_core import get_session
from literature_core.models import Paper, PaperChunk


def extract_abstract_from_chunk(content: str) -> str | None:
    """Extract abstract from chunk content using various patterns."""

    # Clean up content first - fix common PDF extraction issues
    # Add space before capital letters that follow lowercase (word boundaries)
    content_cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)

    # Pattern 1: ABSTRACT: followed by text until next section
    patterns = [
        # ACS style: ABSTRACT: ... KEYWORDS:
        r'ABSTRACT[:\s]*(.+?)(?:KEYWORDS|■\s*INTRODUCTION|1\.\s*INTRODUCTION)',
        # Nature style: Abstract followed by paragraph
        r'(?:^|\n)Abstract\s*\n(.+?)(?:\n\n|\nIntroduction|\n1\.\s)',
        # RSC/Wiley style
        r'(?:^|\n)(?:Abstract|ABSTRACT)\s*[:\-]?\s*(.+?)(?:\n\n|\nKeywords|\n\d+\.\s)',
        # Generic: look for abstract keyword with more flexible ending
        r'[Aa]bstract[:\.\s]+(.+?)(?:\n\n|\n[A-Z][a-z]+:|\n\d+\.\s|KEYWORDS)',
        # Even more generic - just get text after ABSTRACT
        r'ABSTRACT[:\s]+(.{200,2000}?)(?:\n\n|\n[A-Z])',
    ]

    for pattern in patterns:
        match = re.search(pattern, content_cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            abstract = match.group(1).strip()
            # Clean up: remove excessive whitespace
            abstract = re.sub(r'\s+', ' ', abstract)
            # Remove common artifacts
            abstract = re.sub(r'\[Page \d+\]', '', abstract)
            abstract = re.sub(r'Cite\s*This.*?Read\s*Online', '', abstract, flags=re.IGNORECASE)
            abstract = abstract.strip()
            # Abstracts are typically 50-500 words
            word_count = len(abstract.split())
            if 30 < word_count < 700:
                return abstract

    return None


def get_papers_with_chunks():
    """Get all paper IDs that have PDF chunks."""
    with get_session() as session:
        result = session.execute(
            text("SELECT DISTINCT paper_id FROM paper_chunks ORDER BY paper_id")
        )
        return [row[0] for row in result]


def get_first_chunk(paper_id: int) -> str | None:
    """Get the first chunk content for a paper."""
    with get_session() as session:
        chunk = session.query(PaperChunk).filter(
            PaperChunk.paper_id == paper_id,
            PaperChunk.chunk_order == 0
        ).first()
        return chunk.content if chunk else None


def get_paper_abstract(paper_id: int) -> str | None:
    """Get current abstract from papers table."""
    with get_session() as session:
        paper = session.query(Paper).get(paper_id)
        return paper.abstract if paper else None


def update_paper_abstract(paper_id: int, abstract: str):
    """Update paper abstract in database."""
    with get_session() as session:
        paper = session.query(Paper).get(paper_id)
        if paper:
            paper.abstract = abstract
            session.commit()


def main():
    parser = argparse.ArgumentParser(description="Fix abstracts from PDF chunks")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    parser.add_argument("--limit", type=int, default=0, help="Limit papers to process")
    parser.add_argument("--paper-id", type=int, help="Process specific paper")
    args = parser.parse_args()

    if args.paper_id:
        paper_ids = [args.paper_id]
    else:
        paper_ids = get_papers_with_chunks()

    if args.limit > 0:
        paper_ids = paper_ids[:args.limit]

    print(f"Processing {len(paper_ids)} papers with PDF chunks")
    print()

    stats = {"found": 0, "updated": 0, "skipped": 0, "no_abstract": 0}

    for paper_id in paper_ids:
        chunk = get_first_chunk(paper_id)
        if not chunk:
            stats["skipped"] += 1
            continue

        # Extract abstract from chunk
        new_abstract = extract_abstract_from_chunk(chunk)

        if not new_abstract:
            stats["no_abstract"] += 1
            continue

        stats["found"] += 1
        current_abstract = get_paper_abstract(paper_id)

        # Check if abstracts differ significantly
        if current_abstract and len(current_abstract) > 50:
            # Compare first 100 chars to detect mismatches
            current_start = current_abstract[:100].lower()
            new_start = new_abstract[:100].lower()
            if current_start == new_start:
                # Same abstract, skip
                continue

        print(f"Paper {paper_id}:")
        print(f"  OLD: {(current_abstract or 'None')[:100]}...")
        print(f"  NEW: {new_abstract[:100]}...")
        print()

        if args.apply:
            update_paper_abstract(paper_id, new_abstract)
            stats["updated"] += 1
            print(f"  -> Updated!")
        print()

    print("=" * 60)
    print(f"Papers processed: {len(paper_ids)}")
    print(f"Abstracts found in chunks: {stats['found']}")
    print(f"Abstracts updated: {stats['updated']}")
    print(f"No abstract found in chunk: {stats['no_abstract']}")
    print(f"Skipped (no chunk): {stats['skipped']}")

    if not args.apply and stats['found'] > 0:
        print()
        print("Run with --apply to update the database")


if __name__ == "__main__":
    main()
