"""Root pytest configuration and shared fixtures for Literature MCP Server tests.

This file provides:
- Test database fixtures (in-memory SQLite)
- Session management fixtures
- Database override for production database isolation
- Sample data fixtures
- Mock fixtures for expensive operations
- Rich-based test output formatting
"""
import pytest
import sys
import time
import os
import logging
from pathlib import Path
from typing import Generator

from sqlalchemy.orm import Session

# Suppress loguru and other verbose logging during tests
try:
    from loguru import logger
    logger.remove()  # Remove default handler
    logger.add(lambda _: None, level="CRITICAL")  # Suppress all output
except ImportError:
    pass

# Suppress standard logging
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("chromadb").setLevel(logging.CRITICAL)
logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)

# Rich test output
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.table import Table
from rich.panel import Panel


class RichTerminalReporter:
    """Custom pytest terminal reporter using Rich Live display.

    Uses Rich's Live display for interactive terminals, falls back to
    periodic progress updates for non-tty environments (pipes, mamba run, etc).
    """

    def __init__(self, config):
        self.config = config
        # Check if we have a real terminal
        self.is_tty = sys.stderr.isatty() or sys.stdout.isatty()
        # Use stderr for Rich output
        self.console = Console(stderr=True, force_terminal=self.is_tty)
        self.start_time = None
        self.test_start_time = None
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = []
        self.total_tests = 0
        self.current = 0
        self.current_test = ""
        self.live = None
        self.last_progress_report = 0

    def _build_display(self, running=False):
        """Build the Rich renderable for current state."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        pct = self.current / self.total_tests if self.total_tests else 0

        # Progress bar
        bar_width = 40
        filled = int(bar_width * pct)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Status counts
        status_parts = []
        if self.passed:
            status_parts.append(f"[green]{self.passed}✓[/green]")
        if self.failed:
            status_parts.append(f"[red]{self.failed}✗[/red]")
        if self.skipped:
            status_parts.append(f"[yellow]{self.skipped}○[/yellow]")
        status_str = " ".join(status_parts) if status_parts else "[dim]starting...[/dim]"

        # Current test
        if self.current_test:
            parts = self.current_test.split("::")
            test_name = parts[-1][:40] if len(parts) > 1 else self.current_test[-40:]
        else:
            test_name = ""

        # Build display
        icon = "[cyan]▶[/cyan]" if running else "[dim]•[/dim]"
        test_duration = time.time() - self.test_start_time if self.test_start_time and running else 0
        dur_str = f" [yellow]({test_duration:.1f}s)[/yellow]" if test_duration > 2.0 else ""

        line = f"{icon} [dim]{bar}[/dim] {self.current}/{self.total_tests} • {elapsed:.0f}s • {status_str}"
        if test_name:
            line += f"\n   [dim]{test_name}[/dim]{dur_str}"

        return Text.from_markup(line)

    def _print_progress(self):
        """Print periodic progress update for non-tty mode."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        pct = int(100 * self.current / self.total_tests) if self.total_tests else 0
        self.console.print(f"[dim]Progress:[/dim] {self.current}/{self.total_tests} ({pct}%) • {elapsed:.0f}s • {self.passed}✓ {self.failed}✗ {self.skipped}○")

    def pytest_collection_finish(self, session):
        """Called after collection."""
        self.total_tests = len(session.items)
        self.start_time = time.time()

        # Print header
        self.console.print()
        self.console.print("[bold blue]━━━ Literature MCP Tests ━━━[/bold blue]", justify="center")
        self.console.print(f"[dim]{self.total_tests} tests[/dim]", justify="center")
        self.console.print()

        # Start live display only in tty mode
        if self.is_tty:
            self.live = Live(self._build_display(), console=self.console, refresh_per_second=4, transient=True)
            self.live.start()

    def pytest_runtest_logstart(self, nodeid, location):
        """Called when a test starts."""
        self.test_start_time = time.time()
        self.current_test = nodeid
        if self.live:
            self.live.update(self._build_display(running=True))

    def pytest_runtest_logreport(self, report):
        """Called for each test phase."""
        if report.when == "call":
            self._handle_test_result(report)
        elif report.when == "setup" and report.skipped:
            # Handle setup-phase skips
            self.current += 1
            self.skipped += 1
            if self.live:
                self.live.update(self._build_display())

    def _handle_test_result(self, report):
        """Handle test completion."""
        self.current += 1

        # Track outcomes
        if report.passed:
            self.passed += 1
        elif report.failed:
            self.failed += 1
            self.errors.append(report.nodeid)
        elif report.skipped:
            self.skipped += 1

        self.test_start_time = None

        if self.live:
            self.live.update(self._build_display())
        elif not self.is_tty:
            # Non-tty: print progress every 50 tests or 10%
            interval = max(50, self.total_tests // 10)
            if self.current - self.last_progress_report >= interval:
                self._print_progress()
                self.last_progress_report = self.current

    def pytest_sessionfinish(self, session, exitstatus):
        """Called at end of session."""
        elapsed = time.time() - self.start_time

        # Stop live display
        if self.live:
            self.live.stop()

        # Summary
        parts = []
        if self.passed:
            parts.append(f"[green]{self.passed} passed[/green]")
        if self.failed:
            parts.append(f"[red]{self.failed} failed[/red]")
        if self.skipped:
            parts.append(f"[yellow]{self.skipped} skipped[/yellow]")

        status = "[bold green]✓[/bold green]" if self.failed == 0 else "[bold red]✗[/bold red]"
        self.console.print(f"{status} {', '.join(parts)} in {elapsed:.1f}s")

        # Show failures
        if self.errors:
            self.console.print()
            self.console.print("[bold red]Failed:[/bold red]")
            for err in self.errors[:10]:
                self.console.print(f"  [dim]•[/dim] {err}")
            if len(self.errors) > 10:
                self.console.print(f"  [dim]... +{len(self.errors) - 10} more[/dim]")

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        """Suppress default terminal summary."""
        pass


# Plugin registration
_rich_reporter = None


def pytest_configure(config):
    """Register Rich reporter and suppress default output."""
    global _rich_reporter
    # Always register for verbose < 2, let Rich handle tty detection
    if config.option.verbose < 2:
        _rich_reporter = RichTerminalReporter(config)
        config.pluginmanager.register(_rich_reporter, "rich_reporter")


@pytest.hookimpl(trylast=True)
def pytest_report_teststatus(report, config):
    """Suppress default test status output."""
    if _rich_reporter:
        return "", "", ""

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
        # Search methods (return lists)
        mock_service._search_crossref_multi = mock_apis["crossref"]
        mock_service._search_openalex = mock_apis["openalex"]
        mock_service._search_semantic_scholar_query = mock_apis["semantic_scholar"]
        mock_service._search_arxiv = mock_apis["arxiv"]
        mock_service._search_unpaywall = mock_apis["unpaywall"]
        mock_service._title_similarity = MagicMock(return_value=0.9)

        # Direct DOI lookup methods (async, return single result or None)
        # These use the crossref mock's first result if available
        async def lookup_by_doi_mock(doi):
            results = mock_apis["crossref"].return_value
            return results[0] if results else None

        async def lookup_openalex_doi_mock(doi):
            results = mock_apis["openalex"].return_value
            return results[0] if results else None

        async def lookup_semantic_scholar_doi_mock(doi):
            results = mock_apis["semantic_scholar"].return_value
            return results[0] if results else None

        async def resolve_ss_id_mock(paper_id=None, doi=None, title=None):
            return "mock-ss-id" if doi or title else None

        mock_service.lookup_by_doi = lookup_by_doi_mock
        mock_service.lookup_crossref_doi = lookup_by_doi_mock  # Alias
        mock_service.lookup_openalex_doi = lookup_openalex_doi_mock
        mock_service.lookup_semantic_scholar_doi = lookup_semantic_scholar_doi_mock
        mock_service._resolve_semantic_scholar_id = resolve_ss_id_mock
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
