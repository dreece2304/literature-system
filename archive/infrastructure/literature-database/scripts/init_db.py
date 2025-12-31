#!/usr/bin/env python
"""Initialize the literature database."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.database import init_db
from src.models import *

if __name__ == "__main__":
    print("Initializing literature database...")
    init_db()
    print("Database initialization complete!")
