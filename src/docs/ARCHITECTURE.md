# Literature Management System Architecture

## Overview

The literature management system provides tools for managing academic papers,
including storage, search, citation management, and integration with external
services like Zotero and CrossRef.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Claude Code / MCP Client                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         MCP Server (literature-ai)                   │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                        Tool Modules                              ││
│  │  papers.py │ search.py │ collections.py │ notes.py │ pdf.py    ││
│  │  import_export.py │ project.py │ browser_pdf.py │ zotero.py    ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Service Layer (src/services/)                │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  PaperService │ CollectionService │ NoteService │ SearchService ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Core Library (src/literature_core/)               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────────┐│
│  │  models.py │ │ database.py│ │ config.py  │ │ exceptions.py      ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────────────┘│
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────────────────┐│
│  │constants.py│ │ response.py│ │ logging_config.py                 ││
│  └────────────┘ └────────────┘ └────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           SQLite Database                            │
│                  (literature-database/data/metadata/)                │
└─────────────────────────────────────────────────────────────────────┘
```

## Layer Responsibilities

### 1. MCP Tool Layer (`infrastructure/literature-ai/src/mcp_server/tools/`)

**Purpose**: Thin wrappers that handle MCP-specific concerns

**Responsibilities**:
- Define tool schemas (inputSchema) for MCP protocol
- Convert service responses to `TextContent` for MCP
- Handle exceptions and format error responses
- Validate input at the protocol level

**Files**:
- `papers.py` - Paper CRUD, search, content, batch operations
- `search.py` - Keyword and semantic search
- `collections.py` - Collection management
- `notes.py` - Note/annotation management
- `pdf.py` - PDF acquisition and status
- `import_export.py` - BibTeX import/export
- `project.py` - Citation management for manuscripts
- `browser_pdf.py` - Browser-based PDF download queue
- `zotero.py` - Zotero synchronization
- `external.py` - External API lookups (CrossRef, Semantic Scholar)

### 2. Service Layer (`src/services/`)

**Purpose**: Business logic and data access operations

**Responsibilities**:
- Implement all business logic
- Handle database transactions
- Raise typed exceptions for error cases
- Return domain objects (dicts, dataclasses)
- Log operations for debugging

**Files**:
- `paper_service.py` - Paper operations (CRUD, search, batch)
- `collection_service.py` - Collection operations (future)
- `note_service.py` - Note operations (future)
- `search_service.py` - Search operations (future)
- `pdf_service.py` - PDF operations (future)

### 3. Core Library (`src/literature_core/`)

**Purpose**: Shared utilities and database layer

**Modules**:

#### `models.py` - SQLAlchemy ORM Models
```python
Paper, Author, Tag, Collection, Note, PaperContent, ...
```

#### `database.py` - Session Management
```python
get_session()  # Context manager for database sessions
get_engine()   # Get SQLAlchemy engine
init_db()      # Initialize database schema
```

#### `config.py` - Configuration
```python
settings = Settings()  # Pydantic settings from env vars
settings.database_url  # SQLite connection string
settings.pdf_storage_path  # Path to PDF storage
```

#### `exceptions.py` - Exception Hierarchy
```python
LiteratureError           # Base exception
├── EntityNotFoundError
│   ├── PaperNotFoundError
│   ├── CollectionNotFoundError
│   └── NoteNotFoundError
├── DuplicateError
│   ├── DuplicatePaperError
│   └── DuplicateTagError
├── ExternalServiceError
│   ├── CrossRefError
│   └── SemanticScholarError
├── PDFError
│   ├── PDFNotFoundError
│   └── PDFAcquisitionError
├── ValidationError
└── ImportExportError
```

#### `constants.py` - Constants and Enums
```python
ReadStatus.UNREAD, .READING, .READ
ExportFormat.BIBTEX, .JSON, .CSV
DEFAULT_SEARCH_LIMIT = 20
```

#### `response.py` - Response Helpers
```python
success(data)              # {"success": True, "data": ...}
error(message, code)       # {"success": False, "error": ...}
paginated(items, total)    # Includes pagination metadata
batch_result(processed)    # For batch operations
```

#### `logging_config.py` - Logging
```python
setup_logging(level="INFO")  # Configure logging
logger = get_logger(__name__)  # Get logger instance
```

## Data Flow Example

### Get Paper by ID

```
1. MCP Client calls get_paper tool with {"paper_id": 123}
   │
   ▼
2. papers.py:call_tool() receives request
   │
   ▼
3. papers.py:_get_paper() calls PaperService.get(123)
   │
   ▼
4. PaperService.get() opens session, queries database
   │
   ├── If found: returns paper dict
   │   │
   │   ▼
   │   5a. papers.py wraps in success() response
   │   │
   │   ▼
   │   6a. Returns [TextContent(type="text", text=json)]
   │
   └── If not found: raises PaperNotFoundError
       │
       ▼
       5b. papers.py catches exception
       │
       ▼
       6b. Returns error() response with PAPER_NOT_FOUND code
```

### Add Paper with Authors and Tags

```
1. MCP Client calls add_paper with:
   {"title": "...", "authors": ["Alice", "Bob"], "tags": ["ML"]}
   │
   ▼
2. papers.py:_add_paper() calls PaperService.create()
   │
   ▼
3. PaperService.create():
   a. Opens database session
   b. Creates Paper object
   c. For each author: _get_or_create_author()
   d. For each tag: _get_or_create_tag()
   e. Commits transaction
   f. Returns paper dict
   │
   ▼
4. papers.py wraps in created() response
   │
   ▼
5. Returns [TextContent(type="text", text=json)]
```

## Database Schema

### Core Tables

```sql
papers
├── id (PK)
├── title, abstract, year
├── doi, arxiv_id, pubmed_id
├── journal, volume, issue, pages
├── file_path, file_hash
├── citation_key, citation_count
├── rating, read_status
├── full_text, word_count
├── date_added, date_modified, date_read
└── zotero_key, zotero_version

authors
├── id (PK)
└── name

tags
├── id (PK)
└── name

collections
├── id (PK)
├── name, description
└── parent_id (FK -> collections)

notes
├── id (PK)
├── paper_id (FK)
├── content, note_type
├── page_number, position
└── created_at, updated_at
```

### Association Tables

```sql
paper_authors (paper_id, author_id)
paper_tags (paper_id, tag_id)
paper_collections (paper_id, collection_id)
```

### Extraction Tables

```sql
paper_content
├── id (PK)
├── paper_id (FK)
├── paper_type
├── topics (JSON)
├── one_sentence_summary
├── key_findings (JSON)
├── methodology_summary
├── extraction_depth
└── extractor_model
```

## Configuration

### Environment Variables

All configuration uses the `LITCORE_` prefix:

```bash
# Database
LITCORE_DATABASE_PATH=/path/to/literature.db

# External APIs
LITCORE_ZOTERO_API_KEY=...
LITCORE_SEMANTIC_SCHOLAR_API_KEY=...

# Logging
LITCORE_LOG_LEVEL=INFO
```

### Default Paths

```
src/
└── literature_core/
    └── config.py  ──┐
                     │
                     ▼
infrastructure/literature-database/data/
├── metadata/literature.db    # SQLite database
├── pdfs/                     # PDF storage
├── chroma/                   # Vector store
└── whoosh/                   # Search index
```

## Error Handling

### Exception Hierarchy

All custom exceptions inherit from `LiteratureError`:

```python
try:
    paper = PaperService.get(paper_id)
except PaperNotFoundError as e:
    # e.paper_id - the ID that wasn't found
    # e.code - "PAPER_NOT_FOUND"
    # str(e) - "Paper 123 not found"
except LiteratureError as e:
    # Catch-all for any literature operation error
```

### Response Format

All MCP tools return consistent JSON responses:

```json
// Success
{
    "success": true,
    "data": { ... }
}

// Error
{
    "success": false,
    "error": "Paper 123 not found",
    "code": "PAPER_NOT_FOUND",
    "details": { "paper_id": 123 }
}

// Paginated
{
    "success": true,
    "data": [ ... ],
    "pagination": {
        "total": 100,
        "limit": 20,
        "offset": 0,
        "page": 1,
        "total_pages": 5,
        "has_more": true
    }
}
```

## Testing

### Running Tests

```bash
# Run all tests
cd infrastructure/literature-ai
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/test_papers.py -v

# Run with coverage
python -m pytest tests/ --cov=src
```

### Test Database

Tests use an in-memory SQLite database:

```python
@pytest.fixture
def test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```

## Future Improvements

1. **Remaining Services**: Create services for collections, notes, search, PDF
2. **Async Support**: Add async versions of services for better MCP performance
3. **Caching**: Add caching layer for frequently accessed data
4. **Batch Operations**: Optimize batch operations with bulk inserts
5. **Full-Text Search**: Improve Whoosh integration for better search
