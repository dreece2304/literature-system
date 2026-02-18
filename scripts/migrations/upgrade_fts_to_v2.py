"""Upgrade FTS5 from v1 (title+abstract+full_text) to v2 (title+abstract only).

This migration:
1. Drops the old FTS5 table and triggers
2. Creates the new v2 FTS5 table (without full_text column)
3. Creates new triggers for v2
4. Rebuilds the index with just title and abstract

Full-text content search is now handled by semantic search via ChromaDB chunks.

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.migrations.upgrade_fts_to_v2
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import text
from literature_core import get_engine, get_logger
from literature_core.fts import (
    FTS5_CREATE_TABLE,
    FTS5_TRIGGER_INSERT,
    FTS5_TRIGGER_DELETE,
    FTS5_TRIGGER_UPDATE,
)

logger = get_logger(__name__)


def check_fts_version(conn) -> str | None:
    """Check current FTS5 table schema version.

    Returns:
        'v1' if full_text column exists
        'v2' if only title+abstract
        None if table doesn't exist
    """
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'"
    ))
    if result.fetchone() is None:
        return None

    # Check table structure by trying to query
    # FTS5 tables don't have PRAGMA table_info, but we can check via error
    try:
        # Try to select full_text column - if it works, it's v1
        conn.execute(text("SELECT full_text FROM papers_fts LIMIT 0"))
        return "v1"
    except Exception:
        return "v2"


def drop_old_fts(conn) -> bool:
    """Drop old FTS5 table and triggers."""
    try:
        # Drop triggers first
        conn.execute(text("DROP TRIGGER IF EXISTS papers_fts_insert"))
        conn.execute(text("DROP TRIGGER IF EXISTS papers_fts_delete"))
        conn.execute(text("DROP TRIGGER IF EXISTS papers_fts_update"))

        # Drop the FTS table
        conn.execute(text("DROP TABLE IF EXISTS papers_fts"))

        logger.info("Dropped old FTS5 table and triggers")
        return True
    except Exception as e:
        logger.error(f"Failed to drop old FTS5: {e}")
        return False


def create_new_fts(conn) -> bool:
    """Create new v2 FTS5 table and triggers."""
    try:
        # Create FTS5 table (v2: title + abstract only)
        conn.execute(text(FTS5_CREATE_TABLE))

        # Create sync triggers
        conn.execute(text(FTS5_TRIGGER_INSERT))
        conn.execute(text(FTS5_TRIGGER_DELETE))
        conn.execute(text(FTS5_TRIGGER_UPDATE))

        logger.info("Created new FTS5 v2 table and triggers")
        return True
    except Exception as e:
        logger.error(f"Failed to create new FTS5: {e}")
        return False


def rebuild_index(conn, batch_size: int = 100) -> int:
    """Rebuild FTS5 index from papers table.

    Returns number of papers indexed.
    """
    # Get total count
    total = conn.execute(text("SELECT COUNT(*) FROM papers")).scalar() or 0

    if total == 0:
        logger.info("No papers to index")
        return 0

    # Populate in batches
    offset = 0
    while offset < total:
        conn.execute(text("""
            INSERT INTO papers_fts(rowid, title, abstract)
            SELECT id, title, abstract
            FROM papers
            ORDER BY id
            LIMIT :limit OFFSET :offset
        """), {"limit": batch_size, "offset": offset})

        offset += batch_size
        logger.info(f"  Indexed {min(offset, total)}/{total} papers")

    return total


def upgrade(dry_run: bool = False, batch_size: int = 100):
    """Run the FTS5 v1 to v2 upgrade.

    Args:
        dry_run: If True, show what would be done without making changes
        batch_size: Number of papers to index per batch
    """
    logger.info("=" * 60)
    logger.info("Starting FTS5 upgrade: v1 -> v2")
    logger.info(f"  dry_run: {dry_run}")
    logger.info("=" * 60)

    engine = get_engine()

    with engine.connect() as conn:
        # Check current version
        current_version = check_fts_version(conn)
        logger.info(f"Current FTS5 version: {current_version or 'not installed'}")

        if current_version == "v2":
            logger.info("Already on v2, nothing to do")
            return {"status": "already_v2", "papers_indexed": 0}

        if dry_run:
            logger.info("DRY RUN - Would perform the following:")
            logger.info("  1. Drop old FTS5 table and triggers")
            logger.info("  2. Create new FTS5 v2 table (title + abstract only)")
            logger.info("  3. Create new triggers for v2")
            logger.info("  4. Rebuild index with all papers")

            # Count papers that would be indexed
            total = conn.execute(text("SELECT COUNT(*) FROM papers")).scalar() or 0
            logger.info(f"  Papers that would be indexed: {total}")

            return {"status": "dry_run", "papers_would_index": total}

        # Drop old FTS
        if not drop_old_fts(conn):
            return {"status": "error", "error": "Failed to drop old FTS5"}

        # Create new FTS v2
        if not create_new_fts(conn):
            return {"status": "error", "error": "Failed to create new FTS5"}

        # Rebuild index
        papers_indexed = rebuild_index(conn, batch_size)

        # Commit changes
        conn.commit()

        logger.info("=" * 60)
        logger.info("FTS5 upgrade complete!")
        logger.info(f"  Papers indexed: {papers_indexed}")
        logger.info("=" * 60)

        return {"status": "success", "papers_indexed": papers_indexed}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upgrade FTS5 from v1 to v2")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--batch-size", type=int, default=100, help="Papers to index per batch (default: 100)")
    args = parser.parse_args()

    upgrade(dry_run=args.dry_run, batch_size=args.batch_size)
