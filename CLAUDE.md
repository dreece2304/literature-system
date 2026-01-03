# Claude Code Guidelines - Literature Management System

## Project Overview

**Project**: Literature Management System with MCP Integration
**Purpose**: Intelligent paper management, search, and citation tools for research
**Interface**: MCP (Model Context Protocol) server for Claude Code/Desktop
**Environment**: Python 3.11 via mamba (`litai` environment)

## Project Structure

```
research/
├── src/                    # Main source code
│   ├── mcp_server/         # MCP server and tools
│   │   ├── server.py       # Server entry point
│   │   └── tools/          # Tool implementations
│   ├── services/           # Business logic layer
│   │   ├── paper_service.py
│   │   ├── search_service.py
│   │   ├── pdf_service.py
│   │   └── ...
│   ├── literature_core/    # Database models and config
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── database.py     # DB connection
│   │   └── fts.py          # Full-text search
│   ├── embeddings/         # Vector search (ChromaDB)
│   ├── extractors/         # Zotero sync
│   └── config/             # Settings
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── fixtures/           # Shared fixtures
├── data/                   # Runtime data (git-ignored)
│   ├── sqlite/             # SQLite database
│   ├── pdfs/               # PDF storage
│   └── vectorstore/        # ChromaDB embeddings
├── docs/                   # Documentation
└── infrastructure/         # Legacy (data only)
```

## Development Commands

### Running Tests
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q
```

### Linting
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -m flake8 src/
```

### Health Check
```bash
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.health_check
```

### Running MCP Server (for testing)
```bash
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m mcp_server.server
```

## Code Style

### Imports and Type Hints
Always use future annotations for forward references:
```python
from __future__ import annotations
from typing import Optional
from dataclasses import dataclass
```

### Line Length
- **120 characters max** (configured in `.flake8`)
- E402 (module-level import not at top) is ignored in `mcp_server/` due to path setup

### Module Docstrings
Every module should have a docstring with usage examples:
```python
"""Paper Service - Business logic for paper operations.

Usage:
    from services import PaperService

    paper = PaperService.get(123)
    papers, total = PaperService.list(author="Smith", limit=20)
"""
```

## Code Patterns

### Exception Handling
Use the custom exception hierarchy from `literature_core`:
```python
from literature_core import (
    PaperNotFoundError,    # Entity not found
    ValidationError,        # Invalid input
    ExternalAPIError,       # External service failed
    LiteratureError,        # Base class for all errors
)

# Raising exceptions
raise PaperNotFoundError(paper_id=123)
raise ValidationError("field_name", "Error message")

# In MCP tools - exceptions are caught and formatted
try:
    result = PaperService.get(paper_id)
except PaperNotFoundError:
    return error(f"Paper {paper_id} not found")
```

### Response Helpers
Use standard response helpers for consistency:
```python
from literature_core import success, error, paginated, created, batch_result

# Success with data
return success({"count": 10})

# Error response
return error("Something went wrong")

# Paginated list
return paginated(papers, total=100, limit=20, offset=0)

# Created entity
return created({"id": 123, "title": "New Paper"})
```

### Logging
Use the centralized logger:
```python
from literature_core import get_logger

logger = get_logger(__name__)

logger.info("Processing paper", extra={"paper_id": 123})
logger.error("Failed to fetch", extra={"error": str(e)})
```

### Dataclasses for Return Types
Use dataclasses for structured returns:
```python
@dataclass
class PaperListResult:
    papers: list[dict]
    total: int
    limit: int
    offset: int
```

### Service Layer
Services are stateless with class methods:
```python
class PaperService:
    @staticmethod
    def get(paper_id: int) -> dict:
        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                raise PaperNotFoundError(paper_id)
            return paper.to_dict()
```

### MCP Tools
Tools are thin wrappers over services:
```python
async def handle_get_paper(arguments: dict) -> list[TextContent]:
    try:
        paper_id = arguments["paper_id"]
        result = PaperService.get(paper_id)
        return [TextContent(type="text", text=json.dumps(success(result)))]
    except PaperNotFoundError:
        return [TextContent(type="text", text=json.dumps(error(f"Paper {paper_id} not found")))]
```

### Constants
Use enums and constants from `literature_core.constants`:
```python
from literature_core import (
    ReadStatus,           # "unread", "reading", "read"
    DEFAULT_SEARCH_LIMIT, # 20
    MAX_SEARCH_LIMIT,     # 500
    MIN_RATING,           # 1
    MAX_RATING,           # 5
)
```

## Git Conventions

### Branch Naming
```
feature/mcp-plugin     # Current development branch
fix/search-ranking     # Bug fixes
refactor/services      # Code improvements
```

### Commit Format
```
<scope>: <type>: <description>

Examples:
- mcp: feat: Add pagination to export_papers tool
- mcp: fix: Handle missing DOI in search results
- services: refactor: Extract embedding logic
- tests: feat: Add citation service tests
```

## Key Design Principles

1. **Single Source of Truth**: All paper data in SQLite, embeddings in ChromaDB
2. **Service Layer Pattern**: Business logic in services, MCP tools are thin wrappers
3. **Graceful Degradation**: If embeddings unavailable, fall back to keyword search
4. **Explicit Over Implicit**: No magic - configuration in `src/config/`

## What NOT to Do

- Don't create new services without adding corresponding tests
- Don't bypass services by querying the database directly from MCP tools
- Don't commit to `main` directly (use feature branches)
- Don't add dependencies without updating `environment.yml`

## GPU/LLM Notes

When implementing AI features (extraction, summarization):
- Local LLM via Ollama (RTX 4070, 8GB VRAM)
- Max model size: ~14B with 4-bit quantization
- Use `src/config/ai_settings.py` for model configuration
- Prefer batch processing over real-time for large operations

## Testing Patterns

### Test Organization
Tests mirror the source structure:
```
tests/
├── unit/services/          # Unit tests for services
├── integration/tools/      # Integration tests for MCP tools
├── fixtures/               # Shared test fixtures
└── conftest.py             # pytest fixtures (db, session, etc.)
```

### Test Class Naming
Group related tests in descriptive classes:
```python
class TestPaperServiceCreate:
    """Tests for paper creation."""

    def test_create_paper_minimal(self, db):
        """Test creating a paper with only required fields."""
        result = PaperService.create(title="Test Paper")
        assert result["id"] is not None

    def test_create_paper_full(self, db):
        """Test creating a paper with all fields."""
        ...
```

### Using Fixtures
Use the `db` fixture for database tests (auto-cleans up):
```python
def test_get_paper(self, db):
    # db fixture provides clean database state
    paper = PaperService.create(title="Test")
    result = PaperService.get(paper["id"])
    assert result["title"] == "Test"
```

### Testing Exceptions
```python
def test_get_nonexistent_paper(self, db):
    with pytest.raises(PaperNotFoundError):
        PaperService.get(99999)
```

### Requirements
- Unit tests for all new service methods
- Integration tests for MCP tools
- Run full suite before committing:
  ```bash
  /home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q
  ```
