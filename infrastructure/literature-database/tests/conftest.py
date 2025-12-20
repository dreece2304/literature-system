"""
Pytest configuration and shared fixtures for literature-database tests.
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    Base, Paper, Author, Tag, Collection, Note, Citation,
    Manuscript, CitationLocation, PaperContent, ProjectRelevance
)


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def test_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def test_session(test_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def test_db_path(tmp_path) -> Path:
    """Create a temporary database file path."""
    return tmp_path / "test_literature.db"


@pytest.fixture(scope="function")
def file_based_engine(test_db_path):
    """Create a file-based SQLite engine for tests that need persistence."""
    engine = create_engine(f"sqlite:///{test_db_path}", echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_author() -> dict:
    """Sample author data."""
    return {
        "name": "John Smith",
        "orcid": "0000-0001-2345-6789",
        "email": "john.smith@example.com",
        "affiliation": "University of Example"
    }


@pytest.fixture
def sample_paper() -> dict:
    """Sample paper data for testing."""
    return {
        "title": "Machine Learning for Materials Science: A Comprehensive Review",
        "abstract": "This paper reviews recent advances in applying machine learning techniques to materials science problems, including property prediction, structure optimization, and synthesis planning.",
        "year": 2023,
        "doi": "10.1234/example.2023.001",
        "arxiv_id": "2301.12345",
        "journal": "Nature Materials",
        "volume": "22",
        "issue": "3",
        "pages": "123-145",
        "publisher": "Nature Publishing Group",
        "read_status": "unread",
        "rating": None,
        "file_path": None,
        "file_hash": None,
        "full_text": "Full text content of the paper...",
        "word_count": 8500
    }


@pytest.fixture
def sample_paper_minimal() -> dict:
    """Minimal paper data (only required fields)."""
    return {
        "title": "Test Paper Title"
    }


@pytest.fixture
def sample_tag() -> dict:
    """Sample tag data."""
    return {
        "name": "machine-learning",
        "category": "method",
        "color": "#3498db"
    }


@pytest.fixture
def sample_collection() -> dict:
    """Sample collection data."""
    return {
        "name": "ML Papers",
        "description": "Collection of machine learning papers"
    }


@pytest.fixture
def sample_note() -> dict:
    """Sample note data."""
    return {
        "content": "This is a key finding about the correlation between feature X and property Y.",
        "note_type": "highlight",
        "page_number": 5,
        "position": None
    }


@pytest.fixture
def sample_manuscript() -> dict:
    """Sample manuscript data."""
    return {
        "name": "PhD Thesis Chapter 3",
        "project_path": "/home/user/thesis",
        "tex_directory": "chapters/ch3",
        "bib_file": "references.bib",
        "description": "Chapter on ALD process optimization"
    }


# ============================================================================
# Model Instance Fixtures
# ============================================================================

@pytest.fixture
def created_author(test_session, sample_author) -> Author:
    """Create and return an Author instance."""
    author = Author(**sample_author)
    test_session.add(author)
    test_session.commit()
    test_session.refresh(author)
    return author


@pytest.fixture
def created_paper(test_session, sample_paper) -> Paper:
    """Create and return a Paper instance."""
    paper = Paper(**sample_paper)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def created_tag(test_session, sample_tag) -> Tag:
    """Create and return a Tag instance."""
    tag = Tag(**sample_tag)
    test_session.add(tag)
    test_session.commit()
    test_session.refresh(tag)
    return tag


@pytest.fixture
def created_collection(test_session, sample_collection) -> Collection:
    """Create and return a Collection instance."""
    collection = Collection(**sample_collection)
    test_session.add(collection)
    test_session.commit()
    test_session.refresh(collection)
    return collection


@pytest.fixture
def created_manuscript(test_session, sample_manuscript) -> Manuscript:
    """Create and return a Manuscript instance."""
    manuscript = Manuscript(**sample_manuscript)
    test_session.add(manuscript)
    test_session.commit()
    test_session.refresh(manuscript)
    return manuscript


@pytest.fixture
def paper_with_author(test_session, sample_paper, sample_author) -> Paper:
    """Create a paper with an associated author."""
    author = Author(**sample_author)
    paper = Paper(**sample_paper)
    paper.authors.append(author)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def paper_with_tags(test_session, sample_paper) -> Paper:
    """Create a paper with multiple tags."""
    paper = Paper(**sample_paper)
    tags = [
        Tag(name="machine-learning", category="method"),
        Tag(name="materials-science", category="field"),
        Tag(name="review", category="type")
    ]
    paper.tags.extend(tags)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def paper_with_citation_key(test_session, sample_paper) -> Paper:
    """Create a paper with a citation key."""
    paper = Paper(**sample_paper)
    paper.citation_key = "Smith2023Machine"
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


# ============================================================================
# File System Fixtures
# ============================================================================

@pytest.fixture
def temp_pdf_dir(tmp_path) -> Path:
    """Create a temporary directory for PDF files."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    return pdf_dir


@pytest.fixture
def temp_search_index(tmp_path) -> Path:
    """Create a temporary directory for search index."""
    index_dir = tmp_path / "search_index"
    index_dir.mkdir()
    return index_dir


@pytest.fixture
def temp_config_dir(tmp_path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_manuscript_dir(tmp_path) -> Path:
    """Create a temporary manuscript directory with LaTeX files."""
    manuscript_dir = tmp_path / "manuscript"
    manuscript_dir.mkdir()

    # Create a tex file with citations
    tex_content = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
This is the introduction with a citation \cite{Smith2023}.

\section{Methods}
Methods section with multiple citations \cite{Jones2022, Brown2021}.

\section{Results}
Results with more citations \cite{Smith2023, Davis2020}.
\end{document}
"""
    tex_file = manuscript_dir / "main.tex"
    tex_file.write_text(tex_content)

    return manuscript_dir


@pytest.fixture
def sample_config(temp_config_dir) -> Path:
    """Create a sample configuration file."""
    import yaml

    config = {
        "database": {
            "type": "sqlite",
            "path": "data/metadata/literature.db"
        },
        "pdf": {
            "storage_path": "data/pdfs",
            "extract_text": True,
            "organize_by_year": True
        },
        "search": {
            "index_path": "data/cache/search_index"
        },
        "zotero": {
            "library_type": "user"
        }
    }

    config_path = temp_config_dir / "settings.yml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    return config_path


# ============================================================================
# Test Data Directory
# ============================================================================

@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return the path to the test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def test_pdfs_dir(test_data_dir) -> Path:
    """Return the path to test PDFs directory."""
    pdfs_dir = test_data_dir / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    return pdfs_dir


@pytest.fixture(scope="session")
def zotero_responses_dir(test_data_dir) -> Path:
    """Return the path to mocked Zotero responses."""
    responses_dir = test_data_dir / "zotero_responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    return responses_dir


# ============================================================================
# Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_zotero_item() -> dict:
    """Sample Zotero item response."""
    return {
        "key": "ABC12345",
        "version": 1,
        "data": {
            "key": "ABC12345",
            "itemType": "journalArticle",
            "title": "Atomic Layer Deposition of Aluminum Oxide",
            "abstractNote": "This paper describes ALD of Al2O3...",
            "date": "2023-01-15",
            "DOI": "10.1000/test.doi",
            "publicationTitle": "Journal of Vacuum Science",
            "volume": "41",
            "issue": "2",
            "pages": "100-110",
            "creators": [
                {"creatorType": "author", "firstName": "Jane", "lastName": "Doe"},
                {"creatorType": "author", "firstName": "John", "lastName": "Smith"}
            ],
            "tags": [
                {"tag": "ALD"},
                {"tag": "aluminum oxide"}
            ]
        }
    }


@pytest.fixture
def mock_zotero_items_response(mock_zotero_item) -> list:
    """Sample Zotero items list response."""
    return [mock_zotero_item]


@pytest.fixture
def mock_zotero_collections_response() -> list:
    """Sample Zotero collections response."""
    return [
        {
            "key": "COL12345",
            "data": {
                "key": "COL12345",
                "name": "ALD Papers",
                "parentCollection": False
            }
        },
        {
            "key": "COL67890",
            "data": {
                "key": "COL67890",
                "name": "MLD Papers",
                "parentCollection": "COL12345"
            }
        }
    ]


# ============================================================================
# Utility Functions
# ============================================================================

def create_test_pdf(path: Path, text: str = "Test PDF content") -> Path:
    """Create a minimal test PDF file."""
    # Create a simple PDF-like file for testing
    # In real tests, you'd use a library like reportlab or pypdf
    path.write_bytes(b"%PDF-1.4\n" + text.encode() + b"\n%%EOF")
    return path


@pytest.fixture
def create_pdf(temp_pdf_dir):
    """Factory fixture to create test PDFs."""
    def _create_pdf(filename: str = "test.pdf", text: str = "Test content") -> Path:
        pdf_path = temp_pdf_dir / filename
        return create_test_pdf(pdf_path, text)
    return _create_pdf


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def clean_environment(monkeypatch):
    """Ensure a clean environment for testing."""
    # Remove any environment variables that might affect tests
    env_vars = [
        "LITDB_CONFIG_PATH",
        "LITDB_DATABASE_URL",
        "LITDB_LOG_LEVEL",
        "ZOTERO_API_KEY",
        "ZOTERO_USER_ID"
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def set_test_config(monkeypatch, sample_config):
    """Set the config path to the test config."""
    monkeypatch.setenv("LITDB_CONFIG_PATH", str(sample_config))
    yield sample_config


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def client(test_engine, tmp_path):
    """Create a FastAPI test client with test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from src.api.main import app
    from src.database import get_session
    from src.services.search_service import SearchService

    # Create session factory for test database
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Override the database dependency
    def override_get_session():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Override search service to use temp directory
    search_index_path = tmp_path / "search_index"
    search_index_path.mkdir(exist_ok=True)

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_paper_data() -> dict:
    """Sample paper data for API tests."""
    return {
        "title": "Test Paper for API Integration",
        "abstract": "This is a test abstract for integration testing.",
        "year": 2024,
        "doi": "10.1000/test.doi.integration",
        "journal": "Test Journal",
        "volume": "1",
        "issue": "1",
        "pages": "1-10",
        "rating": 4,
        "read_status": "unread",
        "authors": ["Dr. Test Author", "Prof. Example Researcher"],
        "tags": ["machine learning", "materials science", "testing"],
        "collections": ["Test Collection"]
    }


@pytest.fixture
def sample_paper_update() -> dict:
    """Sample paper update data for API tests."""
    return {
        "rating": 5,
        "read_status": "read",
        "abstract": "Updated abstract for testing."
    }


@pytest.fixture
def mock_event_publisher():
    """Mock event publisher for testing."""
    from unittest.mock import MagicMock, patch

    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    mock_publisher.publish_paper_added.return_value = True
    mock_publisher.publish_paper_updated.return_value = True
    mock_publisher.publish_paper_deleted.return_value = True
    mock_publisher.publish_sync_completed.return_value = True
    mock_publisher.is_connected.return_value = True
    mock_publisher.enabled = True
    mock_publisher.get_connection_info.return_value = {
        "redis_url": "redis://localhost:6379",
        "service_name": "literature-database",
        "enabled": True,
        "connected": True,
        "redis_available": True
    }

    with patch('src.services.event_service.get_event_publisher', return_value=mock_publisher):
        yield mock_publisher
