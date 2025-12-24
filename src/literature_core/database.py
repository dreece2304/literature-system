"""Database connection and session management."""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from .config import settings
from .models import Base


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
    """Initialize database with tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


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
