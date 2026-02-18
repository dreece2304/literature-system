#!/usr/bin/env python
"""Database migration script.

Adds missing columns to existing database to match current model definitions.
Safe to run multiple times - checks before adding.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text, inspect
from literature_core import get_engine, get_logger

logger = get_logger(__name__)


def get_existing_columns(engine, table_name: str) -> set[str]:
    """Get set of existing column names for a table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return {col["name"] for col in columns}


def run_migration(dry_run: bool = False):
    """Run database migrations."""
    engine = get_engine()

    # Define migrations: (table, column, sql)
    migrations = [
        # Validation columns (added for ValidationService)
        (
            "papers",
            "validation_status",
            "ALTER TABLE papers ADD COLUMN validation_status VARCHAR(20) DEFAULT 'unvalidated'"
        ),
        (
            "papers",
            "validation_source",
            "ALTER TABLE papers ADD COLUMN validation_source VARCHAR(50)"
        ),
        (
            "papers",
            "validation_date",
            "ALTER TABLE papers ADD COLUMN validation_date DATETIME"
        ),
        (
            "papers",
            "validation_confidence",
            "ALTER TABLE papers ADD COLUMN validation_confidence FLOAT"
        ),
    ]

    print(f"Database: {engine.url}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    applied = 0
    skipped = 0

    for table, column, sql in migrations:
        existing = get_existing_columns(engine, table)

        if column in existing:
            print(f"  SKIP: {table}.{column} (already exists)")
            skipped += 1
        else:
            print(f"  ADD:  {table}.{column}")
            if not dry_run:
                with engine.begin() as conn:
                    conn.execute(text(sql))
            applied += 1

    print(f"\nSummary: {applied} applied, {skipped} skipped")

    if dry_run and applied > 0:
        print("\nRun without --dry-run to apply changes")

    return applied


def create_indexes(dry_run: bool = False):
    """Create missing indexes."""
    engine = get_engine()

    indexes = [
        (
            "papers",
            "ix_papers_validation_status",
            "CREATE INDEX IF NOT EXISTS ix_papers_validation_status ON papers(validation_status)"
        ),
    ]

    print("\nIndexes:")
    for table, index_name, sql in indexes:
        print(f"  CREATE: {index_name}")
        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text(sql))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    print("=" * 50)
    print("Database Migration")
    print("=" * 50 + "\n")

    run_migration(dry_run=args.dry_run)
    create_indexes(dry_run=args.dry_run)

    print("\nDone!")
