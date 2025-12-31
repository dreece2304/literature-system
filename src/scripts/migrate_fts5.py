#!/usr/bin/env python3
"""Migrate existing literature database to use FTS5 full-text search.

This script:
1. Creates the FTS5 virtual table if it doesn't exist
2. Sets up sync triggers for INSERT/UPDATE/DELETE
3. Populates the FTS index from existing papers
4. Verifies index integrity

Usage:
    python -m scripts.migrate_fts5           # Normal migration
    python -m scripts.migrate_fts5 --rebuild # Force rebuild index
    python -m scripts.migrate_fts5 --check   # Check status only
    python -m scripts.migrate_fts5 --optimize # Optimize index after migration
"""
import argparse
import logging
import sys
from pathlib import Path

# Ensure src is in path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from literature_core.database import get_engine, init_db
from literature_core.fts import (
    create_fts_tables,
    is_fts_available,
    get_fts_status,
    rebuild_fts_index,
    optimize_fts_index,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_status(engine) -> dict:
    """Check and display FTS5 index status."""
    status = get_fts_status(engine)

    print("\n=== FTS5 Index Status ===")
    print(f"Available: {status.is_available}")
    print(f"Indexed papers: {status.indexed_count}")
    print(f"Total papers: {status.papers_count}")
    print(f"Needs rebuild: {status.needs_rebuild}")
    if status.last_error:
        print(f"Last error: {status.last_error}")

    if status.is_available and not status.needs_rebuild:
        print("\n✓ FTS5 index is healthy and up to date")
    elif status.is_available and status.needs_rebuild:
        print(f"\n⚠ FTS5 index needs rebuild ({status.papers_count - status.indexed_count} papers missing)")
    else:
        print("\n✗ FTS5 index not available")

    return {
        "available": status.is_available,
        "indexed": status.indexed_count,
        "total": status.papers_count,
        "healthy": status.is_available and not status.needs_rebuild,
    }


def migrate(engine, force_rebuild: bool = False) -> bool:
    """Run the FTS5 migration.

    Args:
        engine: SQLAlchemy engine
        force_rebuild: Force rebuild even if index exists

    Returns:
        True if migration succeeded
    """
    logger.info("Starting FTS5 migration...")

    # Step 1: Create FTS5 tables and triggers
    logger.info("Step 1: Creating FTS5 tables and triggers...")
    if not create_fts_tables(engine):
        logger.error("Failed to create FTS5 tables")
        return False
    logger.info("✓ FTS5 tables created")

    # Step 2: Check if rebuild is needed
    status = get_fts_status(engine)

    if status.needs_rebuild or force_rebuild:
        logger.info(f"Step 2: {'Force rebuilding' if force_rebuild else 'Rebuilding'} FTS index...")
        result = rebuild_fts_index(engine, batch_size=100)

        if not result["success"]:
            logger.error(f"Failed to rebuild index: {result['errors']}")
            return False

        logger.info(f"✓ Indexed {result['papers_indexed']} papers")
    else:
        logger.info("Step 2: Index already up to date, skipping rebuild")

    # Step 3: Verify
    logger.info("Step 3: Verifying index...")
    final_status = get_fts_status(engine)

    if final_status.is_available and not final_status.needs_rebuild:
        logger.info(f"✓ Migration complete. {final_status.indexed_count} papers indexed.")
        return True
    else:
        logger.error(f"Migration verification failed: {final_status}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Migrate literature database to use FTS5 full-text search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Check FTS5 status only, don't migrate"
    )
    parser.add_argument(
        "--rebuild", "-r",
        action="store_true",
        help="Force rebuild index even if it exists"
    )
    parser.add_argument(
        "--optimize", "-o",
        action="store_true",
        help="Optimize index after migration"
    )

    args = parser.parse_args()

    # Get database engine
    engine = get_engine()

    # Ensure base tables exist
    init_db()

    if args.check:
        # Just check status
        result = check_status(engine)
        sys.exit(0 if result["healthy"] else 1)

    # Run migration
    success = migrate(engine, force_rebuild=args.rebuild)

    if success and args.optimize:
        logger.info("Optimizing FTS5 index...")
        if optimize_fts_index(engine):
            logger.info("✓ Index optimized")
        else:
            logger.warning("Index optimization failed (non-critical)")

    # Show final status
    check_status(engine)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
