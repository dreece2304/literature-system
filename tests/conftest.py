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
        self.errored = 0
        self.failreprs = []      # (nodeid, longreprtext) for failures + errors
        self.collect_errors = []  # (nodeid, longreprtext) from collection
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

    def pytest_collectreport(self, report):
        """Record collection failures so they are never silently dropped."""
        if report.failed:
            self.collect_errors.append(
                (getattr(report, "nodeid", "?"), report.longreprtext))

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
        elif report.when in ("setup", "teardown") and report.failed:
            # Fixture/teardown errors produce no "call" report — count them
            # explicitly or they vanish from the summary entirely.
            if report.when == "setup":
                self.current += 1
            self.errored += 1
            self.errors.append(report.nodeid)
            self.failreprs.append((report.nodeid, report.longreprtext))
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
            self.failreprs.append((report.nodeid, report.longreprtext))
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
        elapsed = (time.time() - self.start_time) if self.start_time else 0.0

        # Stop live display
        if self.live:
            self.live.stop()

        # Collection errors first — a run that never collected must scream
        if self.collect_errors:
            self.console.print()
            self.console.print("[bold red]Collection errors:[/bold red]")
            for nodeid, longrepr in self.collect_errors:
                self.console.print(f"[red]• {nodeid}[/red]")
                if longrepr:
                    self.console.print(longrepr, markup=False, highlight=False)

        # Tracebacks for failures and fixture/teardown errors
        if self.failreprs:
            self.console.print()
            for nodeid, longrepr in self.failreprs[:10]:
                self.console.print(f"[bold red]━━ {nodeid}[/bold red]")
                if longrepr:
                    self.console.print(longrepr, markup=False, highlight=False)
            if len(self.failreprs) > 10:
                self.console.print(
                    f"[dim]... +{len(self.failreprs) - 10} more tracebacks omitted[/dim]")

        # Summary
        parts = []
        if self.passed:
            parts.append(f"[green]{self.passed} passed[/green]")
        if self.failed:
            parts.append(f"[red]{self.failed} failed[/red]")
        if self.errored:
            parts.append(f"[red]{self.errored} errored[/red]")
        if self.skipped:
            parts.append(f"[yellow]{self.skipped} skipped[/yellow]")
        if self.collect_errors:
            parts.append(f"[red]{len(self.collect_errors)} collection errors[/red]")

        # Green only when pytest itself says the run was clean
        ok = exitstatus == 0
        status = "[bold green]✓[/bold green]" if ok else "[bold red]✗[/bold red]"
        if not parts:
            parts.append("no tests ran" if not ok else "0 tests")
        self.console.print(f"{status} {', '.join(parts)} in {elapsed:.1f}s")

        # Compact failure list for orientation
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
    get_sample_tex_content,
    get_multiple_papers_data,
)
from tests.fixtures.mocks import (
    MockEmbeddingGenerator,
    MockVectorStore,
    MockChunkVectorStore,
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
def sample_tex_content() -> str:
    """Sample LaTeX content with citations for testing."""
    return get_sample_tex_content()


@pytest.fixture
def multiple_papers_data() -> list[dict]:
    """Generate 5 paper data entries for batch testing."""
    return get_multiple_papers_data(5)


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
