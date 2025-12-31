"""Database connection and session management."""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from .config import settings
from .models import Base


logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings.ensure_directories()
        _engine = create_engine(
            settings.database_url,
            echo=False,
            connect_args={"check_same_thread": False}  # SQLite specific
        )
    return _engine


def init_db() -> None:
    """Initialize database with tables and FTS5 index."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # Initialize FTS5 full-text search tables
    try:
        from .fts import create_fts_tables
        create_fts_tables(engine)
        logger.info("FTS5 tables initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize FTS5 tables: {e}")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session as a context manager.

    Usage:
        with get_session() as session:
            papers = session.query(Paper).all()
    """
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_factory() -> sessionmaker:
    """Get a session factory for creating sessions manually."""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
