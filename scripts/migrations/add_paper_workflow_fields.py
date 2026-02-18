"""Add paper workflow fields for enrichment and provenance tracking.

This migration adds the following columns:

Paper table:
- metadata_source: Source of metadata (crossref, openalex, etc.)
- metadata_confidence: Confidence score (0.0-1.0)
- enrichment_status: Current enrichment status
- import_method: How the paper was imported
- import_date: When the paper was imported

ExtractionMetadata table:
- chunking_status: PDF chunking status
- chunking_error: Error message if chunking failed
- chunking_queued_at: When chunking was queued

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.migrations.add_paper_workflow_fields
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import text
from literature_core import get_engine, get_session, get_logger

logger = get_logger(__name__)


def check_column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result}
    return column in columns


def add_paper_columns(conn) -> list[str]:
    """Add new columns to papers table."""
    added = []
    columns_to_add = [
        ("metadata_source", "VARCHAR(50)"),
        ("metadata_confidence", "FLOAT"),
        ("enrichment_status", "VARCHAR(50) DEFAULT 'pending'"),
        ("import_method", "VARCHAR(50)"),
        ("import_date", "DATETIME"),
    ]

    for col_name, col_type in columns_to_add:
        if not check_column_exists(conn, "papers", col_name):
            conn.execute(text(f"ALTER TABLE papers ADD COLUMN {col_name} {col_type}"))
            added.append(col_name)
            logger.info(f"Added column papers.{col_name}")
        else:
            logger.debug(f"Column papers.{col_name} already exists")

    return added


def add_extraction_metadata_columns(conn) -> list[str]:
    """Add new columns to extraction_metadata table."""
    added = []
    columns_to_add = [
        ("chunking_status", "VARCHAR(20) DEFAULT 'none'"),
        ("chunking_error", "TEXT"),
        ("chunking_queued_at", "DATETIME"),
    ]

    for col_name, col_type in columns_to_add:
        if not check_column_exists(conn, "extraction_metadata", col_name):
            conn.execute(text(f"ALTER TABLE extraction_metadata ADD COLUMN {col_name} {col_type}"))
            added.append(col_name)
            logger.info(f"Added column extraction_metadata.{col_name}")
        else:
            logger.debug(f"Column extraction_metadata.{col_name} already exists")

    return added


def create_indexes(conn) -> list[str]:
    """Create indexes on new columns."""
    created = []
    indexes = [
        ("ix_papers_metadata_source", "papers", "metadata_source"),
        ("ix_papers_enrichment_status", "papers", "enrichment_status"),
    ]

    for idx_name, table, column in indexes:
        # Check if index exists
        result = conn.execute(text(
            f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'"
        ))
        if not result.fetchone():
            conn.execute(text(f"CREATE INDEX {idx_name} ON {table}({column})"))
            created.append(idx_name)
            logger.info(f"Created index {idx_name}")
        else:
            logger.debug(f"Index {idx_name} already exists")

    return created


def backfill_enrichment_status(conn, force: bool = False) -> int:
    """Backfill enrichment_status based on existing data.

    Args:
        conn: Database connection
        force: If True, update all papers regardless of current status
    """
    updated = 0

    # Determine condition - either NULL or force all
    condition = "1=1" if force else "enrichment_status IS NULL OR enrichment_status = 'pending'"

    # Papers with chunks are complete
    result = conn.execute(text(f"""
        UPDATE papers
        SET enrichment_status = 'complete'
        WHERE ({condition})
        AND id IN (SELECT DISTINCT paper_id FROM paper_chunks)
    """))
    updated += result.rowcount
    logger.info(f"Set {result.rowcount} papers with chunks to 'complete'")

    # Papers with file_path but no chunks need chunks
    result = conn.execute(text(f"""
        UPDATE papers
        SET enrichment_status = 'needs_chunks'
        WHERE ({condition})
        AND file_path IS NOT NULL
        AND id NOT IN (SELECT DISTINCT paper_id FROM paper_chunks)
    """))
    updated += result.rowcount
    logger.info(f"Set {result.rowcount} papers with PDF but no chunks to 'needs_chunks'")

    # Papers with abstract but no PDF need PDF
    result = conn.execute(text(f"""
        UPDATE papers
        SET enrichment_status = 'needs_pdf'
        WHERE ({condition})
        AND abstract IS NOT NULL
        AND file_path IS NULL
    """))
    updated += result.rowcount
    logger.info(f"Set {result.rowcount} papers with abstract but no PDF to 'needs_pdf'")

    # Papers without abstract need abstract
    result = conn.execute(text(f"""
        UPDATE papers
        SET enrichment_status = 'needs_abstract'
        WHERE ({condition})
        AND abstract IS NULL
    """))
    updated += result.rowcount
    logger.info(f"Set {result.rowcount} papers without abstract to 'needs_abstract'")

    return updated


def backfill_chunking_status(conn) -> int:
    """Backfill chunking_status based on existing extraction metadata."""
    # Papers with chunks should have 'complete' status
    result = conn.execute(text("""
        UPDATE extraction_metadata
        SET chunking_status = 'complete'
        WHERE chunking_status IS NULL
        AND chunk_count IS NOT NULL
        AND chunk_count > 0
    """))
    updated = result.rowcount
    logger.info(f"Set {result.rowcount} extraction_metadata records to chunking_status='complete'")

    # Remaining set to 'none'
    result = conn.execute(text("""
        UPDATE extraction_metadata
        SET chunking_status = 'none'
        WHERE chunking_status IS NULL
    """))
    updated += result.rowcount
    if result.rowcount > 0:
        logger.info(f"Set {result.rowcount} remaining extraction_metadata to chunking_status='none'")

    return updated


def upgrade(dry_run: bool = False):
    """Run the migration."""
    logger.info("Starting migration: add_paper_workflow_fields")

    engine = get_engine()

    with engine.connect() as conn:
        # Add columns
        paper_cols = add_paper_columns(conn)
        extraction_cols = add_extraction_metadata_columns(conn)

        # Create indexes
        indexes = create_indexes(conn)

        # Backfill data (force=True to update papers that defaulted to 'pending')
        enrichment_updated = backfill_enrichment_status(conn, force=True)
        chunking_updated = backfill_chunking_status(conn)

        if dry_run:
            logger.info("DRY RUN - Rolling back changes")
            conn.rollback()
        else:
            conn.commit()
            logger.info("Migration committed successfully")

    # Summary
    logger.info("=" * 50)
    logger.info("Migration Summary:")
    logger.info(f"  Papers columns added: {paper_cols}")
    logger.info(f"  ExtractionMetadata columns added: {extraction_cols}")
    logger.info(f"  Indexes created: {indexes}")
    logger.info(f"  Papers enrichment_status backfilled: {enrichment_updated}")
    logger.info(f"  ExtractionMetadata chunking_status backfilled: {chunking_updated}")
    logger.info("=" * 50)


def downgrade():
    """Rollback the migration (not recommended for SQLite)."""
    logger.warning("Downgrade not supported for SQLite - columns cannot be dropped easily")
    logger.warning("To rollback, restore from backup or recreate the database")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add paper workflow fields migration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    upgrade(dry_run=args.dry_run)
