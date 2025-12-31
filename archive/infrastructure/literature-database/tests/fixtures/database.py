"""Database test utilities."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import Base  # noqa: E402


def create_test_database(db_path: Path = None):
    """
    Create a test database with all tables.

    Args:
        db_path: Path to SQLite file. If None, creates in-memory database.

    Returns:
        tuple: (engine, SessionLocal)
    """
    if db_path:
        url = f"sqlite:///{db_path}"
    else:
        url = "sqlite:///:memory:"

    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return engine, SessionLocal


def reset_database(engine):
    """Drop and recreate all tables."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_table_counts(session: Session) -> dict:
    """Get row counts for all tables."""
    from src.models import Paper, Author, Tag, Collection, Note, Citation

    return {
        "papers": session.query(Paper).count(),
        "authors": session.query(Author).count(),
        "tags": session.query(Tag).count(),
        "collections": session.query(Collection).count(),
        "notes": session.query(Note).count(),
        "citations": session.query(Citation).count()
    }
