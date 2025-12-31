"""Database fixtures for testing.

Provides in-memory SQLite database and session fixtures that isolate tests
from the production database.
"""
import pytest
from contextlib import contextmanager
from typing import Generator
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_test_engine():
    """Create an in-memory SQLite engine with foreign key enforcement.

    Uses StaticPool to ensure all connections share the same in-memory DB.
    Enables foreign key constraints (disabled by default in SQLite).
    """
    from literature_core.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def create_test_session_factory(engine):
    """Create a session factory bound to the test engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def create_test_session_context(session_factory) -> Generator[Session, None, None]:
    """Create a session context manager for testing."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class DatabaseOverride:
    """Context manager that patches get_session across all modules."""

    def __init__(self, engine):
        self.engine = engine
        self.session_factory = create_test_session_factory(engine)
        self._patches = []

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Test session context manager."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def __enter__(self):
        """Start patching get_session in all relevant modules."""
        modules_to_patch = [
            'literature_core.database.get_session',
            'literature_core.get_session',
            'services.paper_service.get_session',
            'services.collection_service.get_session',
            'services.note_service.get_session',
            'services.search_service.get_session',
            'services.pdf_service.get_session',
            'services.citation_service.get_session',
            'services.import_export_service.get_session',
        ]

        for module_path in modules_to_patch:
            try:
                p = patch(module_path, self.get_session)
                p.start()
                self._patches.append(p)
            except (ModuleNotFoundError, AttributeError):
                # Module may not exist or not have get_session
                pass

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop all patches."""
        for p in self._patches:
            p.stop()
        self._patches.clear()
        return False
