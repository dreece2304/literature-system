"""Migrate Paper.full_text to PaperChunk records.

This migration finds papers with full_text but no chunks, splits the text
into chunks, and stores them as PaperChunk records.

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.migrations.migrate_fulltext_to_chunks

Options:
    --dry-run       Show what would be done without making changes
    --batch-size N  Process N papers at a time (default: 50)
    --limit N       Only process N papers total (for testing)
    --quiet         Suppress progress output
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import text, and_
from sqlalchemy.orm import Session
from literature_core import (
    get_engine,
    get_logger,
    get_session,
    Paper,
    PaperChunk,
    ExtractionMetadata,
    EnrichmentStatus,
    ChunkingStatus,
)

logger = get_logger(__name__)

# Chunk settings (matching ChunkedExtractionService defaults)
CHUNK_SIZE = 8000  # characters
CHUNK_OVERLAP = 500  # characters


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks.

    This mirrors ChunkedExtractionService._split_into_chunks() logic.
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # If not at the end, try to break at paragraph or sentence
        if end < text_len:
            # Look for paragraph break
            para_break = text.rfind('\n\n', start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2  # Include the newlines
            else:
                # Look for sentence break (. followed by space or newline)
                for punct in ['. ', '.\n', '? ', '?\n', '! ', '!\n']:
                    sent_break = text.rfind(punct, start + chunk_size // 2, end)
                    if sent_break > start:
                        end = sent_break + len(punct)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start, accounting for overlap
        start = end - overlap if end < text_len else text_len

    return chunks


def get_papers_needing_migration(session: Session, limit: int | None = None) -> list[Paper]:
    """Find papers with full_text but no chunks."""
    # Subquery to find papers that already have chunks
    papers_with_chunks = (
        session.query(PaperChunk.paper_id)
        .distinct()
        .subquery()
    )

    # Query papers with full_text that don't have chunks
    query = (
        session.query(Paper)
        .filter(
            and_(
                Paper.full_text.isnot(None),
                Paper.full_text != '',
                ~Paper.id.in_(session.query(papers_with_chunks))
            )
        )
        .order_by(Paper.id)
    )

    if limit:
        query = query.limit(limit)

    return query.all()


def migrate_paper(session: Session, paper: Paper, dry_run: bool = False) -> dict:
    """Migrate a single paper's full_text to chunks.

    Returns dict with migration results.
    """
    result = {
        "paper_id": paper.id,
        "title": paper.title[:50] + "..." if len(paper.title) > 50 else paper.title,
        "full_text_chars": len(paper.full_text) if paper.full_text else 0,
        "chunks_created": 0,
        "status": "skipped",
        "error": None,
    }

    if not paper.full_text:
        result["status"] = "skipped"
        result["error"] = "No full_text"
        return result

    try:
        # Split into chunks
        chunks = split_into_chunks(paper.full_text)
        result["chunks_created"] = len(chunks)

        if dry_run:
            result["status"] = "would_migrate"
            return result

        # Create PaperChunk records
        for i, chunk_text in enumerate(chunks):
            chunk = PaperChunk(
                paper_id=paper.id,
                chunk_order=i,
                content=chunk_text,
                word_count=len(chunk_text.split()),
                char_count=len(chunk_text),
            )
            session.add(chunk)

        # Update or create ExtractionMetadata
        metadata = session.query(ExtractionMetadata).filter_by(paper_id=paper.id).first()
        if metadata:
            metadata.chunk_count = len(chunks)
            metadata.chunking_status = ChunkingStatus.COMPLETE
        else:
            metadata = ExtractionMetadata(
                paper_id=paper.id,
                extraction_method="full_text_migration",
                extraction_date=datetime.utcnow(),
                chunk_count=len(chunks),
                word_count=len(paper.full_text.split()) if paper.full_text else 0,
                chunking_status=ChunkingStatus.COMPLETE,
            )
            session.add(metadata)

        # Update paper enrichment status
        paper.enrichment_status = EnrichmentStatus.COMPLETE

        result["status"] = "migrated"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Error migrating paper {paper.id}: {e}")

    return result


def migrate_fulltext_to_chunks(
    batch_size: int = 50,
    limit: int | None = None,
    dry_run: bool = True,
    quiet: bool = False
) -> dict:
    """Migrate all papers with full_text to chunks.

    Args:
        batch_size: Number of papers to process per batch
        limit: Maximum papers to process (None for all)
        dry_run: If True, show what would be done without making changes
        quiet: If True, suppress progress output

    Returns:
        Summary dict with migration statistics
    """
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    if not quiet:
        print("=" * 60)
        print("FULL_TEXT TO CHUNKS MIGRATION")
        print("=" * 60)
        print(f"  dry_run: {dry_run}")
        print(f"  batch_size: {batch_size}")
        print(f"  limit: {limit or 'all'}")
        print("=" * 60)

    summary = {
        "total_found": 0,
        "processed": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "total_chunks_created": 0,
        "dry_run": dry_run,
        "results": [],
    }

    with get_session() as session:
        # Find papers needing migration
        papers = get_papers_needing_migration(session, limit)
        summary["total_found"] = len(papers)

        if not papers:
            if not quiet:
                print("\nNo papers found needing migration")
            return summary

        if not quiet:
            print(f"\nFound {len(papers)} papers to migrate\n")

        # Create iterator with progress bar if available
        if has_tqdm and not quiet:
            paper_iter = tqdm(papers, desc="Migrating papers", unit="paper")
        else:
            paper_iter = papers

        # Process papers
        batch_count = 0
        for paper in paper_iter:
            result = migrate_paper(session, paper, dry_run)
            summary["results"].append(result)
            summary["processed"] += 1
            batch_count += 1

            if result["status"] == "migrated" or result["status"] == "would_migrate":
                summary["migrated"] += 1
                summary["total_chunks_created"] += result["chunks_created"]
            elif result["status"] == "skipped":
                summary["skipped"] += 1
            elif result["status"] == "error":
                summary["errors"] += 1
                if not quiet and not has_tqdm:
                    print(f"  ERROR: Paper {paper.id}: {result.get('error')}")

            # Commit in batches
            if batch_count >= batch_size and not dry_run:
                session.commit()
                batch_count = 0

        # Final commit
        if not dry_run and batch_count > 0:
            session.commit()

    # Final summary
    if not quiet:
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"  Papers found:         {summary['total_found']}")
        print(f"  Papers processed:     {summary['processed']}")
        print(f"  Papers migrated:      {summary['migrated']}")
        print(f"  Papers skipped:       {summary['skipped']}")
        print(f"  Errors:               {summary['errors']}")
        print(f"  Total chunks created: {summary['total_chunks_created']}")
        print(f"  Dry run:              {summary['dry_run']}")
        print("=" * 60)

    return summary


def show_preview(limit: int = 10):
    """Show a preview of papers that would be migrated."""
    with get_session() as session:
        papers = get_papers_needing_migration(session, limit)

        print(f"\nPapers needing migration (showing first {limit}):\n")
        print(f"{'ID':<8} {'Title':<50} {'Full Text Chars':<15} {'Est. Chunks':<12}")
        print("-" * 90)

        for paper in papers:
            chars = len(paper.full_text) if paper.full_text else 0
            est_chunks = max(1, chars // CHUNK_SIZE) if chars else 0
            title = paper.title[:47] + "..." if len(paper.title) > 50 else paper.title
            print(f"{paper.id:<8} {title:<50} {chars:<15} {est_chunks:<12}")

        # Count total
        total = len(get_papers_needing_migration(session))
        print(f"\nTotal papers needing migration: {total}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Paper.full_text to PaperChunk records")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--batch-size", type=int, default=50, help="Process N papers at a time (default: 50)")
    parser.add_argument("--limit", type=int, help="Only process N papers total")
    parser.add_argument("--preview", action="store_true", help="Show preview of papers to migrate")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    if args.preview:
        show_preview(args.limit or 10)
    else:
        migrate_fulltext_to_chunks(
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
