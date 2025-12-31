# Literature MCP Server - Test Suite

Comprehensive test suite for the Literature MCP Server plugin, providing ~80% code coverage.

## Directory Structure

```
tests/
├── conftest.py                    # Root fixtures and configuration
├── pytest.ini                     # Pytest configuration
├── fixtures/
│   ├── __init__.py
│   ├── database.py                # Test database factory
│   ├── sample_data.py             # Realistic paper data
│   └── mocks.py                   # External service mocks
├── unit/
│   ├── services/
│   │   ├── test_paper_service.py
│   │   ├── test_collection_service.py
│   │   ├── test_note_service.py
│   │   └── test_search_service.py
│   ├── models/
│   │   ├── test_paper_model.py
│   │   ├── test_relationships.py
│   │   └── test_constraints.py
│   └── embeddings/
│       ├── test_generator.py
│       └── test_vectorstore.py
├── integration/
│   ├── conftest.py
│   ├── tools/
│   │   ├── test_paper_tools.py
│   │   ├── test_search_tools.py
│   │   ├── test_collection_tools.py
│   │   ├── test_note_tools.py
│   │   ├── test_import_export_tools.py
│   │   └── test_external_tools.py
│   └── test_database_integrity.py
└── benchmarks/
    ├── test_search_performance.py
    ├── test_embedding_performance.py
    └── test_batch_operations.py
```

## Running Tests

### Prerequisites

```bash
# Activate the environment
conda activate litai

# Install test dependencies
pip install pytest pytest-cov pytest-asyncio
```

### Basic Commands

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=html

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v

# Skip slow tests
pytest tests/ -v -m "not slow"

# Run specific test file
pytest tests/unit/services/test_paper_service.py -v

# Run specific test class
pytest tests/unit/services/test_paper_service.py::TestPaperCreate -v

# Run specific test
pytest tests/unit/services/test_paper_service.py::TestPaperCreate::test_create_minimal -v
```

### Benchmarks

```bash
# Run benchmark tests
pytest tests/benchmarks/ -v

# Run benchmarks with timing output
pytest tests/benchmarks/ -v -s

# Run only slow benchmarks
pytest tests/benchmarks/ -v -m slow
```

## Test Fixtures

### Database Fixtures

The test suite uses an in-memory SQLite database with proper isolation:

```python
@pytest.fixture
def db():
    """Provides isolated test database session."""
    # Uses in-memory SQLite with foreign key enforcement
    # Automatically creates tables and cleans up
    pass
```

### Mock Fixtures

External services are mocked for reliable testing:

```python
@pytest.fixture
def mock_external_apis():
    """Mocks all external API calls (CrossRef, Semantic Scholar, etc.)."""
    pass

@pytest.fixture
def mock_embedding_generator():
    """Provides deterministic embedding generator."""
    pass

@pytest.fixture
def mock_vector_store():
    """Provides in-memory vector store."""
    pass
```

### Sample Data

Realistic test data for papers, authors, and tags:

```python
from tests.fixtures.sample_data import (
    get_sample_paper_data,
    get_sample_authors,
    get_sample_tags,
    get_sample_bibtex,
    get_multiple_papers_data,
)
```

## Writing Tests

### Unit Test Pattern

```python
import pytest

class TestPaperCreate:
    """Tests for PaperService.create()."""

    def test_create_minimal(self, db):
        """Test creating paper with minimal fields."""
        from services import PaperService

        result = PaperService.create(title="Test Paper")

        assert result["id"] is not None
        assert result["title"] == "Test Paper"

    def test_create_with_authors(self, db):
        """Test creating paper with authors."""
        from services import PaperService

        result = PaperService.create(
            title="Test Paper",
            authors=["Author One", "Author Two"]
        )

        assert len(result["authors"]) == 2
```

### Integration Test Pattern

```python
import pytest

class TestPaperTools:
    """Integration tests for paper MCP tools."""

    def test_add_paper_tool(self, db, mock_external_apis):
        """Test add_paper tool end-to-end."""
        from mcp_server.tools.papers import call_tool

        result = call_tool("add_paper", {
            "title": "Test Paper",
            "year": 2023
        })

        assert result["id"] is not None
```

### Mock Configuration

Configure mock responses per test:

```python
def test_with_custom_mock(self, mock_external_apis):
    """Test with custom mock response."""
    from tests.fixtures.mocks import MockExternalResult

    # Configure mock to return specific results
    mock_external_apis["crossref"].return_value = [
        MockExternalResult(
            title="Found Paper",
            doi="10.1234/test",
            year=2023
        )
    ]

    # Run test with configured mock
    result = search_external("test query")
    assert result[0]["title"] == "Found Paper"
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation:
- **Services**: Business logic for papers, collections, notes, search
- **Models**: Database model behavior and relationships
- **Embeddings**: Embedding generation and vector store operations

### Integration Tests (`tests/integration/`)

Test components working together:
- **MCP Tools**: Full tool invocation through MCP interface
- **Database Integrity**: Foreign keys, cascades, constraints

### Benchmarks (`tests/benchmarks/`)

Performance tests marked with `@pytest.mark.slow`:
- **Search Performance**: Keyword vs semantic search scaling
- **Embedding Performance**: Generation time, batch vs single
- **Batch Operations**: Create/update/delete performance

## Coverage

Generate coverage reports:

```bash
# HTML report
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# Terminal report
pytest tests/ --cov=src --cov-report=term-missing

# XML report (for CI)
pytest tests/ --cov=src --cov-report=xml
```

### Coverage Targets

| Module | Target |
|--------|--------|
| services/ | 85% |
| models/ | 90% |
| mcp_server/tools/ | 80% |
| embeddings/ | 75% |
| Overall | 80% |

## CI/CD Integration

Example GitHub Actions configuration:

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: conda-incubator/setup-miniconda@v2
        with:
          environment-file: environment.yml
      - run: pytest tests/ --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v3
```

## Troubleshooting

### Import Errors

Ensure `src` is in the Python path:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

### Database Isolation Issues

If tests interfere with each other:
```bash
# Run tests in separate processes
pytest tests/ --forked
```

### Slow Tests

Skip benchmarks for quick iteration:
```bash
pytest tests/ -m "not slow"
```

### Mock Leakage

Ensure mocks don't persist between tests - use function-scoped fixtures.
