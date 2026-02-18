# Literature MCP Server - Integration Guide

## Overview

This MCP server provides tools for managing academic literature directly from Claude Code or Claude Desktop:

- **418 papers** with full metadata
- **365 papers** with extracted full text
- **373 PDFs** stored and indexed
- Semantic search with ChromaDB embeddings
- BibTeX generation and citation management
- Zotero synchronization
- PDF acquisition and management

## Starting the Server

### Prerequisites

- Python 3.11+
- Conda/Mamba environment: `litai`
- NVIDIA GPU with CUDA support (recommended for embeddings)
- Database at `data/sqlite/literature.db`

### Environment Setup

```bash
# Create environment from environment.yml
mamba env create -f environment.yml

# Or quick manual setup:
mamba create -n litai python=3.11 pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia -c conda-forge
mamba activate litai
pip install sentence-transformers chromadb httpx mcp pydantic pydantic-settings \
    loguru pyyaml pypdf pdfplumber pyzotero bibtexparser pytest pytest-asyncio

# Copy and configure API keys
cp archive/infrastructure/literature-ai/.env .env
# Edit .env with your API keys (Semantic Scholar, CrossRef, etc.)
```

### Manual Start

```bash
cd /path/to/research/src
mamba activate litai
python -m mcp_server.server
```

### As MCP Server (stdio mode)

The server communicates via stdio when launched by an MCP client. It does not expose HTTP endpoints.

## Integration with Claude Code

### Option 1: Project-level config (.mcp.json)

Add to your project root `.mcp.json`:

```json
{
  "mcpServers": {
    "literature": {
      "type": "stdio",
      "command": "/path/to/miniforge3/bin/mamba",
      "args": ["run", "-n", "litai", "python", "-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/research/src",
      "env": {
        "PYTHONPATH": "/absolute/path/to/research/src"
      }
    }
  }
}
```

### Option 2: User-level settings

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "literature": {
      "type": "stdio",
      "command": "/home/user/miniforge3/bin/mamba",
      "args": ["run", "-n", "litai", "python", "-m", "mcp_server.server"],
      "cwd": "/home/user/projects/research/src",
      "env": {
        "PYTHONPATH": "/home/user/projects/research/src"
      }
    }
  }
}
```

**Important:**
- Use absolute paths. Claude Code doesn't expand `~` or relative paths reliably.
- The `env.PYTHONPATH` is required so Python can find the `mcp_server` module when Claude Code launches the server from a different project directory.

## Integration with Claude Desktop

Add to Claude Desktop config:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "literature": {
      "command": "/path/to/miniforge3/bin/mamba",
      "args": ["run", "-n", "litai", "python", "-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/research/src",
      "env": {
        "PYTHONPATH": "/absolute/path/to/research/src"
      }
    }
  }
}
```

## Available Tools

### Paper Management

| Tool | Description |
|------|-------------|
| `list_papers` | List papers with optional filters (limit, offset, read_status, year, author, tag) |
| `get_paper` | Get full details for a paper by ID |
| `add_paper` | Add a new paper to the database |
| `update_paper` | Update paper fields (read_status, rating, tags) |
| `batch_update_papers` | Bulk update multiple papers |
| `batch_delete_papers` | Bulk delete papers (with confirmation) |

### Search

| Tool | Description |
|------|-------------|
| `hybrid_search` ⭐ | **Recommended.** Combines keyword (BM25) + semantic search with RRF fusion |
| `keyword_search` | Full-text search using SQLite FTS5 with BM25 ranking |
| `semantic_search` | AI-powered similarity search using ChromaDB embeddings |
| `search_by_author` | Find papers by author name (partial match) |
| `search_by_tag` | Find papers by tag (partial match by default) |
| `find_duplicates` | Find duplicate papers by hash or title similarity |
| `get_search_status` | Health check for search indices and embedding coverage |

**Hybrid Search (Best for most use cases):**
```python
hybrid_search(query="ALD precursor chemistry", alpha=0.65)
# alpha: 0=keyword only, 1=semantic only, 0.65=balanced (default)
```

**Semantic Search Levels:**
- `search_level="paper"` - Search title + abstract only (faster)
- `search_level="chunk"` - Search full paper text chunks (more precise)

**Tag Search:**
- `search_by_tag("ML")` → partial match (matches "machine-learning", "ML-theory")
- `search_by_tag("ML", exact_match=true)` → exact match only

### Content & Extraction

| Tool | Description |
|------|-------------|
| `get_paper_content` | Get full text and any stored extractions |
| `store_extraction` | Store AI-generated summary, key findings, methodology |
| `get_extraction_queue` | Get papers needing AI extraction |

### Collections

| Tool | Description |
|------|-------------|
| `list_collections` | List all collections (optionally hierarchical) |
| `get_collection` | Get collection details with paper count |
| `create_collection` | Create new collection |
| `update_collection` | Update collection name/description |
| `delete_collection` | Delete a collection |
| `add_papers_to_collection` | Add papers to collection |
| `remove_papers_from_collection` | Remove papers from collection |
| `get_collection_children` | Get child collections |

### Notes

| Tool | Description |
|------|-------------|
| `list_notes` | List notes (optionally filtered by paper or type) |
| `get_note` | Get note by ID |
| `create_note` | Add note to a paper |
| `update_note` | Update note content |
| `delete_note` | Delete a note |
| `get_paper_notes` | Get all notes for a paper |
| `delete_paper_notes` | Delete all notes for a paper |

### Citations & BibTeX

| Tool | Description |
|------|-------------|
| `generate_bibtex` | Generate BibTeX for specified papers |
| `format_bibliography` | Format bibliography in APA, MLA, Chicago styles |
| `suggest_citation_key` | Generate BibTeX key for a paper |
| `validate_citations` | Check citation data completeness |
| `scan_manuscript` | Find citation keys in LaTeX/Markdown file |
| `scan_tex_citations` | Extract all \cite{} commands with locations |
| `check_citations` | Check which citations exist in database |
| `get_citation_locations` | Find where a citation key is used |
| `citation_health_check` | Comprehensive citation analysis |
| `find_orphan_citations` | Find bib entries never cited |
| `find_missing_citations` | Find citations not in bib file |
| `find_incomplete_bib_entries` | Find entries missing required fields |
| `find_duplicate_bib_entries` | Find duplicate bib entries |

### BibTeX File Management

| Tool | Description |
|------|-------------|
| `parse_bib_file` | Parse BibTeX file and return entries |
| `link_bib_to_database` | Match bib entries to database papers |
| `sync_bib_from_database` | Update bib file with database metadata |
| `import_bib_to_database` | Import papers from bib file |
| `export_database_to_bib` | Export papers to BibTeX format |

### External APIs

| Tool | Description |
|------|-------------|
| `lookup_paper_metadata` | Look up metadata from CrossRef, OpenAlex, Semantic Scholar, arXiv |
| `search_external_papers` | Search external databases for papers not in library |
| `enrich_paper` | Fetch missing metadata from external sources |
| `get_citation_count` | Get citation count from Semantic Scholar |
| `find_open_access_pdf` | Find open access PDF URLs |

### PDF Management

| Tool | Description |
|------|-------------|
| `get_pdf_status` | Check PDF status for papers |
| `acquire_paper_pdf` | Attempt to download PDF (open access, VPN, proxy) |
| `queue_pdf_download` | Queue PDF for browser automation download |
| `queue_batch_pdf_download` | Queue multiple PDFs |
| `get_download_queue_status` | Check download queue status |
| `process_downloaded_pdfs` | Process PDFs downloaded by browser fetcher |
| `clear_download_queue` | Clear completed/failed downloads |

### Import/Export

| Tool | Description |
|------|-------------|
| `import_bibtex` | Import papers from BibTeX content |
| `import_from_external` | Import paper by DOI, arXiv ID, or title |
| `export_papers` | Export papers in BibTeX, JSON, or CSV |
| `export_collection` | Export all papers in a collection |

### Project Configuration

| Tool | Description |
|------|-------------|
| `get_project_config` | Get project citation configuration |
| `set_project_config` | Set bib files and tex paths for project |

### Zotero Integration

| Tool | Description |
|------|-------------|
| `check_zotero_connection` | Verify Zotero API connection |
| `get_zotero_sync_status` | Get sync status between database and Zotero |
| `sync_from_zotero` | Import papers from Zotero |
| `sync_to_zotero` | Push enriched metadata to Zotero |
| `push_paper_to_zotero` | Push single paper to Zotero |
| `push_pdf_to_zotero` | Upload PDF to Zotero |

## Example Usage

### Finding Papers for a Topic (Recommended: Hybrid Search)

```
User: Find papers about ALD precursor chemistry

Claude uses: hybrid_search("ALD precursor chemistry mechanisms")

Returns: Top papers ranked by combined keyword + semantic relevance, with diagnostics
```

### Keyword-Only Search (When You Know Exact Terms)

```
User: Find papers mentioning "hafnium oxide" exactly

Claude uses: keyword_search("hafnium oxide")

Returns: Papers containing exact keywords, ranked by BM25
```

### Semantic Search (Conceptual Similarity)

```
User: Find papers about thin film growth even if they don't mention "ALD"

Claude uses: semantic_search("atomic layer deposition thin film growth", search_level="chunk")

Returns: Papers with similar concepts, even without exact keyword matches
```

### Checking Search Health

```
User: Why am I getting no search results?

Claude uses: get_search_status(detailed=true)

Returns: FTS5 index status, ChromaDB status, embedding coverage, recommendations
```

### Generating Citations

```
User: Generate BibTeX for papers 42, 55, and 78

Claude uses: generate_bibtex(paper_ids=[42, 55, 78])

Returns: Formatted BibTeX entries
```

### Checking Thesis Citations

```
User: Check if all citations in my chapter exist in the database

Claude uses: scan_manuscript("/path/to/chapter.tex")
Claude uses: check_citations(manuscript_citations=[...])

Returns: List of found/missing citations with suggestions
```

### Enriching Paper Metadata

```
User: Get the citation count and abstract for paper 123

Claude uses: enrich_paper(paper_id=123)

Returns: Updated paper with metadata from external sources
```

## Troubleshooting

### Server won't start

1. Check conda environment is activated: `mamba activate litai`
2. Verify working directory is `src/`
3. Check database file exists at configured path
4. Run health check: `python -m scripts.health_check`

### Search returns empty results

1. **Check search system health first:**
   ```
   get_search_status(detailed=true)
   ```

2. **FTS5 index issues:**
   - If `fts5.needs_rebuild` is true, rebuild the index:
     ```bash
     python src/scripts/migrate_fts5.py --rebuild
     ```
   - Verify papers are indexed: `fts5.indexed_count` should match total papers

3. **Semantic search issues:**
   - Check `embeddings.coverage_percent` - low coverage means many papers lack embeddings
   - If `vector_store.available` is false, ChromaDB may not be configured
   - Use `hybrid_search` which falls back gracefully if semantic unavailable

4. **Similarity threshold too high:**
   - Default is 0.35 (discovery-focused). Try lowering `min_similarity` parameter
   - For keyword search, there's no threshold - results ranked by BM25

5. **Use hybrid search for best results:**
   ```
   hybrid_search("your query")  # Combines both methods automatically
   ```

### Tools return empty results (non-search)

1. Verify database has papers: `list_papers(limit=1)`
2. For semantic search, ensure embeddings are indexed
3. Check ChromaDB path in settings

### Import errors

1. Ensure you're in the correct working directory (`src/`)
2. Check all dependencies installed
3. Verify no path conflicts with other projects

### Zotero connection fails

1. Check Zotero API key is configured
2. For local connector, ensure Zotero app is running
3. Verify library ID is correct

## Database Statistics

| Metric | Count |
|--------|-------|
| Total Papers | 418 |
| Papers with Full Text | 365 |
| Papers with PDFs | 373 |
| Collections | 3 |

## Architecture

```
MCP Client (Claude Code/Desktop)
    ↓ stdio
MCP Server (src/mcp_server/server.py)
    ↓
Tool Handlers (src/mcp_server/tools/*.py)
    ↓
Service Layer (src/services/*.py)
    ↓
SQLAlchemy ORM (src/literature_core/models.py)
    ↓
SQLite Database
```

No HTTP API layer - direct database access via services for minimal latency.

## Testing

The project includes a comprehensive test suite:

| Test Type | Count | Description |
|-----------|-------|-------------|
| Integration | 225 | MCP tool tests with in-memory database |
| Real API | 18 | Live external API tests |
| Unit | ~50 | Service layer tests |
| **Total** | **~293** | All tests passing |

### Running Tests

```bash
# Activate environment
mamba activate litai
cd /path/to/research

# Run integration tests (recommended)
pytest tests/integration/ -v

# Run all tests (excludes real API by default)
pytest tests/ -v --ignore=tests/integration/tools/test_external_tools_real.py

# Run real external API tests (requires API keys in .env)
pytest tests/integration/tools/test_external_tools_real.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Skip slow benchmarks
pytest tests/ -v -m "not slow"
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures (in-memory DB, mocks)
├── fixtures/                # Test data and mock factories
├── unit/
│   ├── services/           # Service layer tests
│   ├── models/             # ORM model tests
│   └── embeddings/         # Embedding/chunker tests
├── integration/
│   ├── tools/              # MCP tool handler tests
│   └── test_database_integrity.py
└── benchmarks/             # Performance tests
```

### Key Test Fixtures

- `db` - Isolated in-memory SQLite database per test
- `mock_external_apis` - Mocked CrossRef, Semantic Scholar, etc.
- `mock_embedding_generator` - Deterministic embeddings
- `mock_vector_store` - In-memory ChromaDB replacement

## Maintenance Scripts

Located in `src/scripts/`:

### Health Check

```bash
python -m scripts.health_check
python -m scripts.health_check --json  # For automation
```

Checks: database connectivity, ChromaDB status, PDF storage, disk/memory usage.

### Integrity Check

```bash
python -m scripts.integrity_check
python -m scripts.integrity_check --fix  # Auto-fix issues
```

Finds: orphan notes, missing PDFs, duplicate papers, broken Zotero links.

### Reindex

```bash
python -m scripts.reindex --incremental  # Only missing
python -m scripts.reindex --full         # Complete rebuild
python -m scripts.reindex --papers 1 2 3 # Specific papers
```

Rebuilds embeddings and search indexes.

### Backup

```bash
python -m scripts.backup --output-dir ~/backups
python -m scripts.backup -o ~/backups --include-pdfs --compress
python -m scripts.backup --list         # List existing backups
python -m scripts.backup --cleanup 5    # Keep last 5 backups
```

### Combined Maintenance

```bash
python -m scripts.maintenance              # Health + integrity
python -m scripts.maintenance --all        # All tasks
python -m scripts.maintenance --fix        # Auto-fix issues
```

### Scheduling (cron)

```bash
# Daily health check
0 6 * * * cd /path/to/src && python -m scripts.health_check --json >> /var/log/literature.log

# Weekly maintenance
0 2 * * 0 cd /path/to/src && python -m scripts.maintenance --all --backup-dir ~/backups
```
