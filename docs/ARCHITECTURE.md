# Literature Management System Architecture

## Directory Structure (Post-Refactor December 2024)

```
research/
├── src/                              # Core application code (CANONICAL)
│   ├── literature_core/              # Database models, config, utilities
│   │   ├── models.py                 # SQLAlchemy ORM models (with indexes)
│   │   ├── database.py               # Session management
│   │   ├── config.py                 # Settings and paths
│   │   ├── response.py               # Response formatting
│   │   ├── chunks.py                 # Chunk dataclasses for embeddings
│   │   ├── constants.py              # Application constants
│   │   ├── exceptions.py             # Custom exceptions
│   │   └── logging_config.py         # Logging setup
│   │
│   ├── services/                     # Business logic layer (CANONICAL)
│   │   ├── paper_service.py          # Paper CRUD, store_extraction
│   │   ├── search_service.py         # Keyword & semantic search
│   │   ├── collection_service.py     # Collection management
│   │   ├── note_service.py           # Notes on papers
│   │   ├── pdf_service.py            # PDF acquisition & management
│   │   ├── citation_service.py       # BibTeX, citations, manuscript scanning
│   │   ├── import_export_service.py  # Import/export operations
│   │   └── external_search.py        # CrossRef, Semantic Scholar, arXiv APIs
│   │
│   └── scripts/                      # CLI utilities
│       ├── add_indexes.py            # Database index management
│       └── reindex_embeddings.py     # Chunk embedding indexer
│
├── infrastructure/
│   ├── literature-ai/
│   │   ├── config/                   # MCP server configuration
│   │   │   └── settings.py
│   │   │
│   │   └── src/
│   │       ├── mcp_server/           # MCP Server (Claude Code interface)
│   │       │   ├── server.py         # Main MCP server entry point
│   │       │   ├── tools/            # MCP tool implementations
│   │       │   │   ├── papers.py     # list_papers, get_paper, add_paper, update_paper
│   │       │   │   ├── search.py     # keyword_search, semantic_search
│   │       │   │   ├── collections.py
│   │       │   │   ├── notes.py
│   │       │   │   ├── pdf.py        # acquire_paper_pdf, get_pdf_status
│   │       │   │   ├── external.py   # lookup_metadata, search_external
│   │       │   │   ├── citations.py  # scan_manuscript, check_citations
│   │       │   │   ├── import_export.py
│   │       │   │   ├── project.py    # LaTeX/BibTeX project tools
│   │       │   │   ├── zotero.py     # Zotero sync
│   │       │   │   └── browser_pdf.py
│   │       │   └── resources/        # MCP resources
│   │       │
│   │       ├── embeddings/           # Vector search
│   │       │   ├── generator.py      # EmbeddingGenerator (sentence-transformers)
│   │       │   ├── vectorstore.py    # VectorStore, ChunkVectorStore (ChromaDB)
│   │       │   └── chunker.py        # Text chunking logic
│   │       │
│   │       └── context/              # Manuscript parsing
│   │           └── parser.py         # ManuscriptParser for LaTeX/Markdown
│   │
│   └── literature-database/
│       └── src/
│           ├── extractors/           # External data extractors
│           │   ├── zotero_sync.py    # Zotero web API sync
│           │   ├── zotero_local_api.py
│           │   ├── pdf_extractor.py
│           │   └── metadata_extractor.py
│           ├── cli.py                # CLI tool (standalone)
│           └── utils/                # Utility functions
│
├── data/                             # Data storage
│   ├── literature.db                 # SQLite database
│   └── vectorstore/                  # ChromaDB collections
│       └── chunks/                   # Chunk-level embeddings (50k+)
│
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md               # This file
│   ├── SEARCH.md                     # Semantic search details
│   └── ...
│
└── archive/                          # Legacy code (not used)
    ├── fastapi-api/                  # Old HTTP API layer
    └── legacy-infrastructure/        # Archived modules
```

## Architecture Flow

```
Claude Code → MCP Server → Services → SQLAlchemy → SQLite
                  ↓
            Embeddings → ChromaDB
```

## Key Design Decisions

### 1. Services as Canonical Location
All business logic lives in `src/services/`. The MCP tools are thin wrappers that:
- Parse arguments from Claude Code
- Call service methods
- Format responses for MCP protocol

### 2. No HTTP API Layer
Direct database access via SQLAlchemy. The FastAPI HTTP layer was removed in December 2024 refactor.
- Old: `MCP → HTTP → FastAPI → SQLAlchemy → SQLite`
- New: `MCP → Services → SQLAlchemy → SQLite`

### 3. Single Source of Truth
- Database models: `src/literature_core/models.py` only
- Services: `src/services/` only
- Embeddings: `infrastructure/literature-ai/src/embeddings/` only
- Legacy code moved to `archive/`

### 4. Embedding Architecture
- **Chunk-level** (default): Full-text chunks (~500 chars) for content search
- **Paper-level**: Title + abstract for quick similarity
- Model: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- Storage: ChromaDB with cosine similarity
- Stats: 50,209 chunks from 364 papers

## Service Layer

| Service | Purpose |
|---------|---------|
| `PaperService` | Paper CRUD, metadata, store_extraction, batch operations |
| `SearchService` | Keyword, semantic (paper & chunk level), author, tag search |
| `CollectionService` | Organize papers into hierarchical collections |
| `NoteService` | Annotations and notes on papers |
| `PDFService` | PDF download, text extraction, status tracking |
| `CitationService` | BibTeX generation, manuscript scanning, citation checking |
| `ImportExportService` | BibTeX import/export, external source import |
| `ExternalSearchService` | CrossRef, Semantic Scholar, OpenAlex, arXiv APIs |

## MCP Tools (11 modules, 50+ tools)

| Module | Key Tools |
|--------|-----------|
| papers | list_papers, get_paper, add_paper, update_paper, store_extraction |
| search | keyword_search, semantic_search, search_by_author, search_by_tag |
| pdf | acquire_paper_pdf, get_pdf_status, find_open_access_pdf |
| collections | list_collections, create_collection, add_papers_to_collection |
| notes | list_notes, create_note, get_paper_notes |
| citations | scan_manuscript, check_citations, generate_bibtex |
| import_export | import_bibtex, export_papers, import_from_external |
| external | lookup_paper_metadata, search_external_papers, get_citation_count |
| project | scan_tex_citations, citation_health_check, sync_bib_from_database |
| zotero | sync_from_zotero, sync_to_zotero, push_paper_to_zotero |
| browser_pdf | queue_pdf_download, get_download_queue_status |

## Database Indexes

Performance-critical indexes on:
- `papers.doi`, `papers.arxiv_id`, `papers.zotero_key`
- `papers.title`, `papers.year`, `papers.read_status`
- `paper_authors.paper_id`, `paper_authors.author_id`
- `paper_tags.paper_id`, `paper_tags.tag_id`
- `paper_collections.paper_id`, `paper_collections.collection_id`
- `notes.paper_id`
