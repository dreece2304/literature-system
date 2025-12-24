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
│   │   ├── papers.py    # Paper management tools
│   │   ├── search.py    # Search tools
│   │   ├── collections.py
│   │   ├── notes.py
│   │   ├── citations.py
│   │   ├── external.py
│   │   ├── pdf.py
│   │   ├── import_export.py
│   │   ├── project.py
│   │   ├── browser_pdf.py
│   │   └── zotero.py
│   └── resources/       # MCP resource handlers
│
├── embeddings/          # Vector search infrastructure
│   ├── generator.py     # Sentence transformer embeddings
│   └── vectorstore.py   # ChromaDB vector store
│
├── extractors/          # External data sources
│   ├── zotero_sync.py   # Zotero web API sync
│   └── zotero_local_api.py  # Zotero local connector API
│
├── context/             # Context detection
│   └── parser.py        # LaTeX/Markdown manuscript parser
│
├── config/              # Configuration
│   ├── __init__.py      # Re-exports from literature_core
│   └── ai_settings.py   # AI/embedding-specific settings
│
└── scripts/             # Utility scripts
    └── health_check.py  # System health verification
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

See `literature_core/config.py` for all options.

## Data Directories

- `data/` - Runtime data (database, vectorstore, PDFs)
- `infrastructure/literature-database/data/` - Legacy location (still has some data)
