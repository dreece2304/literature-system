#!/usr/bin/env python3
"""
Add database indexes for query performance.

Run with: python -m scripts.add_indexes
Or: python scripts/add_indexes.py

Safe to run multiple times - checks if indexes exist before creating.

Current database: 418 papers
Expected improvement: 10-100x faster lookups on indexed columns
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect

from literature_core import get_engine, setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


# Index definitions: (index_name, table_name, [columns], unique)
# Based on query pattern analysis from service files
INDEXES = [
    # =========================================================================
    # Papers table - Primary lookups (most frequently queried)
    # =========================================================================
    # Already have UNIQUE indexes on: doi, arxiv_id, pubmed_id, zotero_key

    # citation_key - used by CitationService for BibTeX matching
    ("ix_papers_citation_key", "papers", ["citation_key"], False),

    # =========================================================================
    # Papers table - Common filters (used in list/search queries)
    # =========================================================================

    # read_status - PaperService.list(read_status="unread")
    ("ix_papers_read_status", "papers", ["read_status"], False),

    # year - PaperService.list(year=2024)
    ("ix_papers_year", "papers", ["year"], False),

    # rating - Favorites filter (rating >= 4)
    ("ix_papers_rating", "papers", ["rating"], False),

    # date_added - Recent papers, sorting
    ("ix_papers_date_added", "papers", ["date_added"], False),

    # Composite: year + read_status (common filter combination)
    ("ix_papers_year_status", "papers", ["year", "read_status"], False),

    # =========================================================================
    # Authors table
    # =========================================================================

    # name - SearchService.search_by_author("Smith")
    ("ix_authors_name", "authors", ["name"], False),

    # =========================================================================
    # Junction tables (critical for JOIN performance)
    # =========================================================================

    # paper_authors - Both directions for efficient joins
    ("ix_paper_authors_paper_id", "paper_authors", ["paper_id"], False),
    ("ix_paper_authors_author_id", "paper_authors", ["author_id"], False),
    # Composite for covering index
    ("ix_paper_authors_both", "paper_authors", ["paper_id", "author_id"], False),

    # paper_tags - Both directions
    ("ix_paper_tags_paper_id", "paper_tags", ["paper_id"], False),
    ("ix_paper_tags_tag_id", "paper_tags", ["tag_id"], False),

    # paper_collections - Both directions
    ("ix_paper_collections_paper_id", "paper_collections", ["paper_id"], False),
    ("ix_paper_collections_collection_id", "paper_collections", ["collection_id"], False),

    # =========================================================================
    # Collections table
    # =========================================================================

    # name - CollectionService.get_by_name()
    ("ix_collections_name", "collections", ["name"], False),

    # parent_id - Hierarchy traversal
    ("ix_collections_parent_id", "collections", ["parent_id"], False),

    # =========================================================================
    # Notes table
    # =========================================================================

    # paper_id - NoteService.get_paper_notes(paper_id)
    ("ix_notes_paper_id", "notes", ["paper_id"], False),

    # note_type - Filter by type (highlight, comment, summary)
    ("ix_notes_note_type", "notes", ["note_type"], False),

    # Composite: paper_id + note_type
    ("ix_notes_paper_type", "notes", ["paper_id", "note_type"], False),
]


def get_existing_indexes(engine) -> set[str]:
    """Get names of all existing indexes."""
    inspector = inspect(engine)
    existing = set()
    for table in inspector.get_table_names():
        for idx in inspector.get_indexes(table):
            existing.add(idx["name"])
    return existing


def get_existing_tables(engine) -> set[str]:
    """Get names of all existing tables."""
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def create_indexes(dry_run: bool = False) -> tuple[int, int, int]:
    """
    Create all defined indexes.

    Args:
        dry_run: If True, only print what would be done without executing

    Returns:
        Tuple of (created, skipped, failed) counts
    """
    engine = get_engine()
    existing_indexes = get_existing_indexes(engine)
    existing_tables = get_existing_tables(engine)

    logger.info(f"Found {len(existing_indexes)} existing indexes")
    logger.info(f"Found {len(existing_tables)} tables: {', '.join(sorted(existing_tables))}")

    created = 0
    skipped = 0
    failed = 0

    with engine.connect() as conn:
        for idx_name, table, columns, unique in INDEXES:
            # Check if index already exists
            if idx_name in existing_indexes:
                logger.debug(f"SKIP: {idx_name} - already exists")
                skipped += 1
                continue

            # Check if table exists
            if table not in existing_tables:
                logger.warning(f"SKIP: {idx_name} - table '{table}' does not exist")
                skipped += 1
                continue

            # Build CREATE INDEX statement
            cols = ", ".join(columns)
            unique_str = "UNIQUE " if unique else ""
            sql = f"CREATE {unique_str}INDEX {idx_name} ON {table} ({cols})"

            if dry_run:
                logger.info(f"DRY RUN: {sql}")
                created += 1
                continue

            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"CREATED: {idx_name} ON {table}({cols})")
                created += 1
            except Exception as e:
                logger.error(f"FAILED: {idx_name} - {e}")
                failed += 1

    return created, skipped, failed


def verify_indexes() -> None:
    """Print all indexes after creation."""
    engine = get_engine()
    inspector = inspect(engine)

    print("\n" + "=" * 60)
    print("INDEX VERIFICATION")
    print("=" * 60)

    for table in sorted(inspector.get_table_names()):
        indexes = inspector.get_indexes(table)
        if indexes:
            print(f"\n{table}:")
            for idx in indexes:
                cols = ", ".join(idx["column_names"])
                unique = " (UNIQUE)" if idx["unique"] else ""
                print(f"  - {idx['name']}: ({cols}){unique}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Add database indexes for performance")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without executing")
    parser.add_argument("--verify", action="store_true", help="Only verify existing indexes")
    args = parser.parse_args()

    if args.verify:
        verify_indexes()
        return

    print("=" * 60)
    print("DATABASE INDEX MIGRATION")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    created, skipped, failed = create_indexes(dry_run=args.dry_run)

    print("\n" + "-" * 60)
    print(f"Results: {created} created, {skipped} skipped, {failed} failed")
    print("-" * 60)

    if not args.dry_run and created > 0:
        verify_indexes()


if __name__ == "__main__":
    main()
