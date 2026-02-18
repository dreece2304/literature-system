"""Add paper_references table for extracted bibliography.

This migration adds:
- paper_references table for storing extracted references
- reference_count column to extraction_metadata

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.migrations.add_paper_references
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import text
from literature_core import get_engine, get_logger

logger = get_logger(__name__)


def check_table_exists(conn, table: str) -> bool:
    """Check if a table exists."""
    result = conn.execute(text(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
    ))
    return result.fetchone() is not None


def check_column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result}
    return column in columns


def create_paper_references_table(conn) -> bool:
    """Create the paper_references table."""
    if check_table_exists(conn, "paper_references"):
        logger.info("Table paper_references already exists")
        return False

    conn.execute(text("""
        CREATE TABLE paper_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            reference_order INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            parsed_title TEXT,
            parsed_authors TEXT,
            parsed_year INTEGER,
            parsed_journal VARCHAR(500),
            parsed_doi VARCHAR(100),
            parsed_arxiv_id VARCHAR(50),
            match_status VARCHAR(20) DEFAULT 'unmatched',
            matched_paper_id INTEGER,
            parse_confidence FLOAT,
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (matched_paper_id) REFERENCES papers(id) ON DELETE SET NULL
        )
    """))
    logger.info("Created table paper_references")
    return True


def create_indexes(conn) -> list[str]:
    """Create indexes for paper_references."""
    created = []
    indexes = [
        ("ix_paper_refs_paper_order", "paper_references", "paper_id, reference_order"),
        ("ix_paper_refs_paper_id", "paper_references", "paper_id"),
        ("ix_paper_refs_doi", "paper_references", "parsed_doi"),
        ("ix_paper_refs_match_status", "paper_references", "match_status"),
        ("ix_paper_refs_matched_paper_id", "paper_references", "matched_paper_id"),
    ]

    for idx_name, table, columns in indexes:
        result = conn.execute(text(
            f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'"
        ))
        if not result.fetchone():
            conn.execute(text(f"CREATE INDEX {idx_name} ON {table}({columns})"))
            created.append(idx_name)
            logger.info(f"Created index {idx_name}")

    return created


def add_reference_count_column(conn) -> bool:
    """Add reference_count column to extraction_metadata."""
    if check_column_exists(conn, "extraction_metadata", "reference_count"):
        logger.info("Column extraction_metadata.reference_count already exists")
        return False

    conn.execute(text(
        "ALTER TABLE extraction_metadata ADD COLUMN reference_count INTEGER"
    ))
    logger.info("Added column extraction_metadata.reference_count")
    return True


def upgrade(dry_run: bool = False):
    """Run the migration."""
    logger.info("Starting migration: add_paper_references")

    engine = get_engine()

    with engine.connect() as conn:
        # Create table
        table_created = create_paper_references_table(conn)

        # Create indexes
        indexes = create_indexes(conn)

        # Add column
        column_added = add_reference_count_column(conn)

        if dry_run:
            logger.info("DRY RUN - Rolling back changes")
            conn.rollback()
        else:
            conn.commit()
            logger.info("Migration committed successfully")

    # Summary
    logger.info("=" * 50)
    logger.info("Migration Summary:")
    logger.info(f"  Table created: {table_created}")
    logger.info(f"  Indexes created: {indexes}")
    logger.info(f"  Column added: {column_added}")
    logger.info("=" * 50)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add paper_references table migration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    upgrade(dry_run=args.dry_run)
