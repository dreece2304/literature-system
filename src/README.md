# Literature Management System - Source Code

Consolidated source code for the literature management MCP server.

## Directory Structure

```
src/
├── literature_core/     # Core database models and configuration
│   ├── models.py        # SQLAlchemy ORM models (Paper, Author, Collection, etc.)
│   ├── database.py      # Database session management
│   └── config.py        # Pydantic settings with env var support
│
├── services/            # Business logic layer
│   ├── paper_service.py     # Paper CRUD operations
│   ├── search_service.py    # Keyword and semantic search
│   ├── collection_service.py # Collection management
│   ├── note_service.py      # Notes/annotations
│   ├── citation_service.py  # BibTeX and citation management
│   └── external_search.py   # CrossRef, OpenAlex, arXiv APIs
│
├── mcp_server/          # MCP Server for Claude Code integration
│   ├── server.py        # Main MCP server entry point
│   ├── tools/           # MCP tool implementations
│   │   ├── papers.py    # Paper CRUD, store_extraction
│   │   ├── search.py    # Unified search tool
│   │   ├── collections.py
│   │   ├── notes.py
│   │   ├── citations.py # Manuscript analysis, citation formatting
│   │   ├── external.py  # External API lookups
│   │   ├── pdf.py       # acquire_pdf, manage_pdf
│   │   ├── import_export.py  # import_paper, export
│   │   ├── project.py   # manage_bibtex, citation health
│   │   ├── discovery.py # semantic_find, embeddings
│   │   ├── extraction.py     # AI extraction, PDF processing queue
│   │   ├── validation.py     # Paper validation
│   │   ├── citation_network.py  # Citation graph, claim citations
│   │   └── browser_pdf.py    # Internal helpers for pdf.py (no tools)
│   └── resources/       # MCP resource handlers
│
├── embeddings/          # Vector search infrastructure
│   ├── generator.py     # Sentence transformer embeddings
│   ├── chunker.py       # Text chunking
│   └── vectorstore.py   # ChromaDB vector store
│
├── extractors/          # UNUSED legacy package (nothing imports it)
│   ├── metadata_extractor.py  # Regex DOI/arXiv metadata parsing (unused)
│   └── pdf_extractor.py       # PDF text extraction (unused; live path is PDFService)
│
├── context/             # Context detection
│   └── parser.py        # LaTeX/Markdown manuscript parser
│
├── config/              # Configuration
│   ├── __init__.py      # Re-exports from literature_core
│   └── ai_settings.py   # AI/embedding-specific settings
│
└── scripts/             # Utility scripts
    ├── health_check.py  # System health verification
    ├── zotero_import.py # Offline Zotero import (reads zotero.sqlite snapshot)
    └── ...              # backup, maintenance, reindex, batch extraction
```

## Running the MCP Server

The MCP server is configured in `.mcp.json` at the project root:

```bash
# From project root
mamba run -n litai python -m mcp_server.server
```

Or run from src/:

```bash
cd src
mamba run -n litai python -m mcp_server.server
```

## Health Check

Verify all components are working:

```bash
cd src
mamba run -n litai python -m scripts.health_check
```

## Configuration

Settings are loaded from environment variables with the `LITCORE_` prefix:

- `LITCORE_DATABASE_PATH` - SQLite database location
- `LITCORE_PDF_STORAGE_PATH` - PDF file storage
- `LITCORE_CHROMA_PATH` - ChromaDB vector store
- `LITCORE_ZOTERO_API_KEY` - Zotero web API key

See `literature_core/config.py` for all options. AI/embedding settings use the `OLLAMA_`,
`EMBEDDING_`, and `RERANKER_` prefixes (see `config/ai_settings.py`).

Note: `data/config/settings.yml` and `data/config/credentials.yml` are legacy files from the
old Zotero sync (archive/zotero) and are not read by any current code. Editing them has no
effect; use the environment variables above instead.

## Data Directories

- `data/` - Runtime data (database, vectorstore, PDFs)
