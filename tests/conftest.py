"""Root pytest configuration and shared fixtures for Literature MCP Server tests.

This file provides:
- Test database fixtures (in-memory SQLite)
- Session management fixtures
- Database override for production database isolation
- Sample data fixtures
- Mock fixtures for expensive operations
"""
import pytest
import sys
from pathlib import Path
from typing import Generator

from sqlalchemy.orm import Session

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import from local fixtures
from tests.fixtures.database import (
    create_test_engine,
    create_test_session_factory,
    DatabaseOverride,
)
from tests.fixtures.sample_data import (
    get_sample_paper_data,
    get_sample_paper_with_arxiv,
    get_sample_authors,
    get_sample_tags,
    get_sample_collection,
    get_sample_child_collection,
    get_sample_note,
    get_sample_notes,
    get_sample_bibtex,
    get_sample_tex_content,
    get_multiple_papers_data,
)
from tests.fixtures.mocks import (
    MockEmbeddingGenerator,
    MockVectorStore,
    MockChunkVectorStore,
    create_mock_external_service,
    create_mock_httpx_client,
)


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def test_engine():
    """Create an in-memory SQLite engine with foreign key enforcement.

    Uses StaticPool to ensure all connections share the same in-memory DB.
    Enables foreign key constraints (disabled by default in SQLite).

    Yields:
        Engine: SQLAlchemy engine connected to in-memory database
    """
    from literature_core.models import Base

    engine = create_test_engine()
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_session(test_engine) -> Generator[Session, None, None]:
    """Create a database session for testing.

    Rolls back all changes after each test for isolation.

    Args:
        test_engine: The test database engine

    Yields:
        Session: SQLAlchemy session for testing
    """
    session_factory = create_test_session_factory(test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def db(test_engine):
    """Override get_session to use test database.

    This is the CRITICAL fixture that ensures tests use the test database
    instead of the production database. Use this fixture in any test that
    needs database access through services.

    Args:
        test_engine: The test database engine

    Yields:
        DatabaseOverride: Context manager handling all patches
    """
    with DatabaseOverride(test_engine) as override:
        yield override


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_paper_data() -> dict:
    """Sample paper data matching real academic paper structure."""
    return get_sample_paper_data()


@pytest.fixture
def sample_paper_with_arxiv() -> dict:
    """Sample arXiv preprint paper data."""
    return get_sample_paper_with_arxiv()


@pytest.fixture
def sample_authors() -> list[dict]:
    """List of sample author data."""
    return get_sample_authors()


@pytest.fixture
def sample_tags() -> list[dict]:
    """List of sample tag data."""
    return get_sample_tags()


@pytest.fixture
def sample_collection() -> dict:
    """Sample collection data."""
    return get_sample_collection()


@pytest.fixture
def sample_child_collection() -> dict:
    """Sample child collection for hierarchy testing."""
    return get_sample_child_collection()


@pytest.fixture
def sample_note() -> dict:
    """Sample note data."""
    return get_sample_note()


@pytest.fixture
def sample_notes() -> list[dict]:
    """Multiple sample notes for testing."""
    return get_sample_notes()


@pytest.fixture
def sample_bibtex() -> str:
    """Sample BibTeX content for testing import/export."""
    return get_sample_bibtex()


@pytest.fixture
def sample_tex_content() -> str:
    """Sample LaTeX content with citations for testing."""
    return get_sample_tex_content()


@pytest.fixture
def multiple_papers_data() -> list[dict]:
    """Generate 5 paper data entries for batch testing."""
    return get_multiple_papers_data(5)


# ============================================================================
# MODEL INSTANCE FIXTURES
# ============================================================================

@pytest.fixture
def created_paper(test_session, sample_paper_data):
    """Create and return a Paper instance in the test database.

    Args:
        test_session: Database session
        sample_paper_data: Paper data dict

    Returns:
        Paper: Created paper instance
    """
    from literature_core.models import Paper

    paper = Paper(**sample_paper_data)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def created_paper_with_authors(test_session, sample_paper_data, sample_authors):
    """Create a paper with associated authors.

    Args:
        test_session: Database session
        sample_paper_data: Paper data dict
        sample_authors: Author data list

    Returns:
        Paper: Created paper with authors
    """
    from literature_core.models import Paper, Author

    paper = Paper(**sample_paper_data)
    for author_data in sample_authors:
        author = Author(**author_data)
        paper.authors.append(author)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def created_paper_with_tags(test_session, sample_paper_data, sample_tags):
    """Create a paper with associated tags.

    Args:
        test_session: Database session
        sample_paper_data: Paper data dict
        sample_tags: Tag data list

    Returns:
        Paper: Created paper with tags
    """
    from literature_core.models import Paper, Tag

    paper = Paper(**sample_paper_data)
    for tag_data in sample_tags:
        tag = Tag(**tag_data)
        paper.tags.append(tag)
    test_session.add(paper)
    test_session.commit()
    test_session.refresh(paper)
    return paper


@pytest.fixture
def created_collection(test_session, sample_collection):
    """Create and return a Collection instance.

    Args:
        test_session: Database session
        sample_collection: Collection data dict

    Returns:
        Collection: Created collection instance
    """
    from literature_core.models import Collection

    collection = Collection(**sample_collection)
    test_session.add(collection)
    test_session.commit()
    test_session.refresh(collection)
    return collection


@pytest.fixture
def created_note(test_session, created_paper, sample_note):
    """Create and return a Note attached to a paper.

    Args:
        test_session: Database session
        created_paper: Paper to attach note to
        sample_note: Note data dict

    Returns:
        Note: Created note instance
    """
    from literature_core.models import Note

    note = Note(paper_id=created_paper.id, **sample_note)
    test_session.add(note)
    test_session.commit()
    test_session.refresh(note)
    return note


@pytest.fixture
def multiple_papers(test_session, multiple_papers_data):
    """Create multiple papers for batch operation testing.

    Args:
        test_session: Database session
        multiple_papers_data: List of paper data dicts

    Returns:
        list[Paper]: List of created paper instances
    """
    from literature_core.models import Paper

    papers = []
    for data in multiple_papers_data:
        paper = Paper(**data)
        test_session.add(paper)
        papers.append(paper)
    test_session.commit()
    for paper in papers:
        test_session.refresh(paper)
    return papers


# ============================================================================
# EMBEDDING & VECTOR STORE MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_embedding_generator():
    """Mock the sentence-transformers model to avoid loading during tests.

    Returns a mock that produces deterministic 384-dimensional embeddings.

    Yields:
        MockEmbeddingGenerator: Mock embedding generator
    """
    from unittest.mock import patch

    # Import the module first to ensure it's loaded before patching
    import embeddings.generator as emb_gen

    mock_gen = MockEmbeddingGenerator()

    with patch.object(emb_gen, 'get_embedding_generator', return_value=mock_gen):
        with patch.object(emb_gen, 'EmbeddingGenerator', return_value=mock_gen):
            yield mock_gen


@pytest.fixture
def mock_vector_store():
    """Mock ChromaDB vector store for testing without actual persistence.

    Yields:
        MockVectorStore: Mock vector store
    """
    from unittest.mock import patch

    # Import the module first to ensure it's loaded before patching
    import embeddings.vectorstore as vec_store

    mock_store = MockVectorStore()

    with patch.object(vec_store, 'get_vector_store', return_value=mock_store):
        with patch.object(vec_store, 'VectorStore', return_value=mock_store):
            yield mock_store


@pytest.fixture
def mock_chunk_store():
    """Mock chunk vector store for testing.

    Yields:
        MockChunkVectorStore: Mock chunk vector store
    """
    from unittest.mock import patch

    # Import the module first to ensure it's loaded before patching
    import embeddings.vectorstore as vec_store

    mock_store = MockChunkVectorStore()

    with patch.object(vec_store, 'get_chunk_store', return_value=mock_store):
        with patch.object(vec_store, 'ChunkVectorStore', return_value=mock_store):
            yield mock_store


# ============================================================================
# EXTERNAL API MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_external_apis():
    """Mock all external API calls (CrossRef, Semantic Scholar, etc.).

    Returns a dictionary of AsyncMock objects for each API that can be
    configured per-test:
        - crossref: _search_crossref_multi
        - openalex: _search_openalex
        - semantic_scholar: _search_semantic_scholar_query
        - arxiv: _search_arxiv
        - unpaywall: _search_unpaywall

    Yields:
        dict: Mock API methods that can be configured per test
    """
    from unittest.mock import patch, AsyncMock, MagicMock
    from tests.fixtures.mocks import create_mock_external_api_dict

    mock_apis = create_mock_external_api_dict()

    # Create a mock service that uses our configurable mocks
    def create_patched_service():
        mock_service = MagicMock()
        mock_service._search_crossref_multi = mock_apis["crossref"]
        mock_service._search_openalex = mock_apis["openalex"]
        mock_service._search_semantic_scholar_query = mock_apis["semantic_scholar"]
        mock_service._search_arxiv = mock_apis["arxiv"]
        mock_service._search_unpaywall = mock_apis["unpaywall"]
        mock_service._title_similarity = MagicMock(return_value=0.9)
        return mock_service

    # Patch where ExternalSearchService is USED (in external.py), not where it's defined
    with patch('mcp_server.tools.external.ExternalSearchService', create_patched_service):
        yield mock_apis


@pytest.fixture
def mock_httpx():
    """Mock httpx for all HTTP requests.

    Yields:
        MagicMock: Mock httpx client
    """
    from unittest.mock import patch

    mock_client = create_mock_httpx_client()

    with patch('httpx.AsyncClient', return_value=mock_client):
        yield mock_client


# ============================================================================
# FILE SYSTEM FIXTURES
# ============================================================================

@pytest.fixture
def temp_pdf_dir(tmp_path) -> Path:
    """Create temporary directory for PDF files.

    Args:
        tmp_path: Pytest tmp_path fixture

    Returns:
        Path: Path to temporary PDF directory
    """
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    return pdf_dir


@pytest.fixture
def temp_bibtex_file(tmp_path, sample_bibtex) -> Path:
    """Create a temporary BibTeX file for testing.

    Args:
        tmp_path: Pytest tmp_path fixture
        sample_bibtex: BibTeX content string

    Returns:
        Path: Path to temporary BibTeX file
    """
    bib_file = tmp_path / "references.bib"
    bib_file.write_text(sample_bibtex)
    return bib_file


@pytest.fixture
def temp_tex_file(tmp_path, sample_tex_content) -> Path:
    """Create a temporary TeX file with citations.

    Args:
        tmp_path: Pytest tmp_path fixture
        sample_tex_content: LaTeX content string

    Returns:
        Path: Path to temporary TeX file
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(sample_tex_content)
    return tex_file


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def clean_environment(monkeypatch):
    """Ensure clean environment without production config.

    Args:
        monkeypatch: Pytest monkeypatch fixture
    """
    env_vars = [
        "LITERATURE_DATABASE_PATH",
        "LITERATURE_PDF_PATH",
        "CROSSREF_MAILTO",
        "SEMANTIC_SCHOLAR_API_KEY",
        "UNPAYWALL_EMAIL",
        "ZOTERO_API_KEY",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    yield
