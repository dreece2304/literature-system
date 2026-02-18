#!/usr/bin/env python
"""Initialize the chunked extraction tables.

Run with:
    python scripts/init_structured_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from literature_core import get_engine
from literature_core.models import PaperChunk, PaperTable, PaperFigure, ExtractionMetadata


def create_tables():
    """Create the chunked extraction tables."""
    engine = get_engine()

    # Create only the new tables (won't affect existing)
    tables = [
        PaperChunk.__table__,
        PaperTable.__table__,
        PaperFigure.__table__,
        ExtractionMetadata.__table__,
    ]

    for table in tables:
        try:
            table.create(engine, checkfirst=True)
            print(f"Created table: {table.name}")
        except Exception as e:
            print(f"Table {table.name}: {e}")

    print("\nDone!")


if __name__ == "__main__":
    create_tables()
