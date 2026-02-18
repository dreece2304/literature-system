# Literature Management System Architecture

## Directory Structure (Updated January 2026)

```
research/
├── src/                              # Core application code
│   ├── literature_core/              # Database models, config, utilities
│   │   ├── models.py                 # SQLAlchemy ORM models (Paper, PaperChunk, etc.)
│   │   ├── database.py               # Session management
│   │   ├── config.py                 # Settings and paths (auto-detects project root)
│   │   ├── response.py               # Response formatting helpers
│   │   ├── chunks.py                 # Chunk dataclasses for embeddings
│   │   ├── constants.py              # Application constants (ReadStatus, limits)
│   │   ├── exceptions.py             # Custom exceptions hierarchy
│   │   ├── fts.py                    # Full-text search (FTS5)
│   │   └── logging_config.py         # Logging setup
│   │
│   ├── services/                     # Business logic layer
│   │   ├── paper_service.py          # Paper CRUD, store_extraction
│   │   ├── search_service.py         # FTS5, RRF fusion
│   │   ├── unified_search_service.py # Smart search facade (acronyms, spelling)
│   │   ├── embedding_service.py      # ChromaDB vector search
│   │   ├── collection_service.py     # Collection management
│   │   ├── note_service.py           # Notes on papers
│   │   ├── pdf_service.py            # PDF acquisition & management
│   │   ├── citation_service.py       # BibTeX, citations, manuscript scanning
│   │   ├── import_export_service.py  # Import/export operations
│   │   ├── external_search.py        # CrossRef, Semantic Scholar, arXiv APIs
│   │   ├── extraction_service.py     # AI-powered extraction (Ollama/Claude)
│   │   ├── validation_service.py     # Paper validation
│   │   └── search_constants.py       # Domain constants (ACRONYM_EXPANSIONS, etc.)
│   │
│   ├── mcp_server/                   # MCP Server (Claude interface)
│   │   ├── server.py                 # Main MCP server entry point
│   │   ├── tools/                    # MCP tool implementations
│   │   │   ├── papers.py             # Paper CRUD, store_extraction
│   │   │   ├── search.py             # Unified search tool with modes
│   │   │   ├── collections.py        # Collection management
│   │   │   ├── notes.py              # Note management
│   │   │   ├── pdf.py                # PDF acquisition
│   │   │   ├── external.py           # External API lookups
│   │   │   ├── project.py            # LaTeX/BibTeX project tools
│   │   │   ├── discovery.py          # Paper similarity
│   │   │   ├── extraction.py         # AI extraction, PDF processing queue
│   │   │   ├── import_export.py      # BibTeX import/export
│   │   │   ├── validation.py         # Paper validation
│   │   │   ├── citation_network.py   # Citation graph analysis
│   │   │   ├── browser_pdf.py        # Browser-based PDF queue
│   │   │   └── zotero.py             # Zotero sync
│   │   └── resources/                # MCP resources
│   │
│   ├── embeddings/                   # Vector search
│   │   ├── generator.py              # EmbeddingGenerator (sentence-transformers)
│   │   ├── vectorstore.py            # VectorStore, ChunkVectorStore (ChromaDB)
│   │   └── chunker.py                # Text chunking logic
│   │
│   ├── extractors/                   # Data extractors
│   │   ├── zotero_sync.py            # Zotero web API sync
│   │   ├── zotero_local_api.py       # Zotero local API
│   │   └── pdf_extractor.py          # PDF text extraction
│   │
│   ├── config/                       # Application settings
│   │   └── ai_settings.py            # Ollama/LLM configuration
│   │
│   ├── alembic/                      # Database migrations
│   │   ├── versions/                 # Migration scripts
│   │   └── env.py                    # Alembic environment
│   │
│   └── scripts/                      # CLI utilities
│       ├── reindex_embeddings.py     # Rebuild ChromaDB index
│       └── check_paper_health.py     # Health checks
│
├── data/                             # Data storage (SOURCE OF TRUTH)
│   ├── literature.db                 # SQLite database (~493 papers)
│   ├── pdfs/                         # Locally acquired PDFs
│   ├── vectorstore/                  # ChromaDB collections (327MB)
│   │   └── chroma.sqlite3            # Embeddings (~491 papers indexed)
│   ├── config/                       # Runtime configuration
│   │   ├── credentials.yml           # Zotero API key (git-ignored)
│   │   └── settings.yml              # Zotero settings
│   ├── cache/                        # Search index cache
│   └── metadata/                     # Extracted metadata
│
├── tests/                            # Test suite
│   ├── unit/                         # Unit tests (services, models)
│   ├── integration/                  # Integration tests (MCP tools)
│   ├── fixtures/                     # Shared test fixtures
│   └── conftest.py                   # pytest fixtures
│
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md               # This file
│   ├── WORKFLOWS.md                  # Import & Query workflows
│   ├── TOOL_REFERENCE.md             # MCP tool documentation
│   └── archive/                      # Historical docs
│
└── archive/                          # Archived code
    └── scripts/                      # Deprecated scripts
```

## Architecture Flow

```
Claude Code → MCP Server → Services → SQLAlchemy → SQLite
                  ↓
            Embeddings → ChromaDB
```

## Key Design Decisions

### 1. Services as Canonical Location
All business logic lives in `src/services/`. MCP tools are thin wrappers that:
- Parse arguments from Claude
- Call service methods
- Format responses for MCP protocol

### 2. No HTTP API Layer
Direct database access via SQLAlchemy. The FastAPI HTTP layer was removed in December 2024.
- Old: `MCP → HTTP → FastAPI → SQLAlchemy → SQLite`
- New: `MCP → Services → SQLAlchemy → SQLite`

### 3. Single Source of Truth
- **Data storage**: `data/` directory (database, PDFs, vectorstore, config)
- **Database models**: `src/literature_core/models.py`
- **Services**: `src/services/`
- **Embeddings**: `src/embeddings/`
- **MCP tools**: `src/mcp_server/tools/`
- **Configuration**: `src/literature_core/config.py` (auto-detects project root)

### 4. Configuration System
The config system (`src/literature_core/config.py`) provides:
- **Auto-detection**: Finds project root via `.git` directory
- **Environment overrides**: All paths can be overridden via `LITCORE_*` variables
- **Default paths**:
  - Database: `{PROJECT_ROOT}/data/literature.db`
  - PDFs: `{PROJECT_ROOT}/data/pdfs/`
  - Vectorstore: `{PROJECT_ROOT}/data/vectorstore/`
  - Config: `{PROJECT_ROOT}/data/config/`

### 5. Embedding Architecture
- **Chunk-level**: Full-text chunks for deep content search
- **Paper-level**: Title + abstract for quick similarity
- Model: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- Storage: ChromaDB with cosine similarity
- Stats: ~50K chunks from ~400 papers with full text

---

## Service Layer

| Service | Purpose |
|---------|---------|
| `PaperService` | Paper CRUD, metadata, store_extraction, batch operations |
| `SearchService` | FTS5 keyword search, RRF rank fusion |
| `UnifiedSearchService` | Smart search facade (acronyms, spelling, mode selection) |
| `EmbeddingService` | ChromaDB vector search (paper & chunk level) |
| `ExtractionService` | AI extraction (Ollama), PDF processing queue, quality checks |
| `CollectionService` | Hierarchical collections |
| `NoteService` | Paper annotations |
| `PDFService` | PDF download, text extraction |
| `CitationService` | BibTeX, manuscript scanning, citation health |
| `ImportExportService` | BibTeX import/export |
| `ExternalSearchService` | CrossRef, Semantic Scholar, OpenAlex, arXiv APIs |
| `ValidationService` | Paper verification against external sources |

---

## MCP Tools

| Module | Key Tools |
|--------|-----------|
| papers | `list_papers`, `get_paper`, `add_paper`, `update_paper`, `store_extraction`, `get_paper_content` |
| search | `search` (unified with mode parameter), `search_by_author`, `search_by_tag` |
| pdf | `acquire_paper_pdf`, `get_pdf_status`, `find_duplicates` |
| extraction | `get_pdf_processing_status`, `queue_pdf_processing`, `process_pdf_queue`, `extract_paper`, `prepare_extraction` |
| collections | `list_collections`, `create_collection`, `add_papers_to_collection` |
| notes | `list_notes`, `create_note`, `get_paper_notes` |
| import_export | `import_bibtex`, `export_papers`, `import_from_external` |
| external | `lookup_paper_metadata`, `search_external_papers`, `enrich_paper` |
| project | `scan_tex_citations`, `citation_health_check`, `sync_bib_from_database` |
| discovery | `find_similar_papers`, `suggest_citations_for_text` |
| validation | `validate_paper`, `validate_papers_batch`, `get_validation_queue` |
| citation_network | `get_paper_citations`, `get_paper_references`, `build_citation_graph` |
| browser_pdf | `queue_pdf_download`, `get_download_queue_status`, `process_downloaded_pdfs` |
| zotero | `sync_from_zotero`, `sync_to_zotero`, `check_zotero_connection` |

---

## Database Schema

### Core Tables
- **papers**: Main paper metadata (title, authors, year, doi, abstract, etc.)
- **paper_chunks**: Full text split into sections for embedding
- **paper_content**: AI-extracted structured content (summary, findings, etc.)
- **paper_figures**: Extracted figures metadata
- **paper_tables**: Extracted tables
- **paper_references**: Bibliography entries from papers
- **authors**: Normalized author records
- **paper_authors**: Many-to-many link
- **tags**: User-defined tags
- **paper_tags**: Many-to-many link
- **collections**: Hierarchical collections
- **paper_collections**: Many-to-many link
- **notes**: User annotations on papers

### Key Fields
- **enrichment_status**: `pending`, `needs_pdf`, `needs_chunking`, `needs_extraction`, `needs_review`, `complete`, `failed`
- **read_status**: `unread`, `reading`, `read`
- **validation_status**: `unverified`, `verified`, `failed`
- **extraction_depth**: `abstract_only` (quick), `comprehensive` (deep)

### Indexes
Performance-critical indexes on:
- `papers.doi`, `papers.arxiv_id`, `papers.zotero_key`
- `papers.title`, `papers.year`, `papers.read_status`, `papers.enrichment_status`
- `paper_chunks.paper_id`
- `paper_authors.paper_id`, `paper_authors.author_id`
- `paper_tags.paper_id`, `paper_tags.tag_id`
- `paper_collections.paper_id`, `paper_collections.collection_id`
- `notes.paper_id`

---

## AI Extraction Pipeline (Schema v2.1)

### Two-Tier Architecture

| Tier | Model | Input | Output |
|------|-------|-------|--------|
| **Quick** | Claude Code | Title + abstract | paper_type, topics, one_sentence_summary |
| **Deep** | Ollama | PDF chunks | Full 15-field schema + verification |

### Quick Extraction (All Papers)
Runs automatically on import or via `store_extraction(is_quick=True)`:
- Input: Title, journal, abstract
- Output: `paper_type`, `topics`, `one_sentence_summary`
- Stored in: `PaperContent.paper_type`, `.topics`, `.one_sentence_summary`

### Deep Extraction (Selected Papers)
Two-pass approach for comprehensive extraction:

```
PDF → Text Extraction → Section-Aware Chunking
                              ↓
Pass 1: Per-Chunk Extraction (Ollama)
  - section_type, key_points, quantitative_data
  - techniques_mentioned, materials_mentioned
  - claims_or_conclusions, cited_papers
                              ↓
Pass 2: Consolidation (Ollama)
  - Synthesize all chunks into final schema
  - Verify against quick extraction
  - Generate 15-field output + verification
```

### Ollama Configuration
- Model: `qwen2.5:7b-instruct-q4_K_M` (or similar)
- Context: 28K tokens (input) + 3K (output)
- GPU: RTX 4070 (8GB VRAM)

### PaperContent Schema (v2.1)

**Quick tier fields (from abstract):**
- `paper_type`: research_article, review, perspective, letter, conference, etc.
- `topics`: 3-5 hierarchical topics
- `one_sentence_summary`: Brief summary
- `quick_extraction_date`: When quick tier ran
- `extractor_model`: Model used (e.g., "claude-code")

**Deep tier fields (from PDF chunks):**
- `deep_paper_type`: May differ from quick
- `deep_topics`: May include more specific topics
- `deep_one_sentence_summary`: More detailed from full text
- `key_findings`: List of specific findings with data
- `methodology_summary`: Methods description
- `structured_data`: JSON with extended fields:
  - `quantitative_results`: Metrics with values, units, conditions
  - `citable_claims`: Quotable assertions
  - `techniques_used`: Methods with purposes
  - `experimental_conditions`: Materials, temps, parameters
  - `research_context`: Problem, novelty, limitations
  - `prior_work_comparison`: How this advances field
  - `citation_contexts`: Why cite in intro/methods/results/discussion
  - `future_directions`: Suggested follow-up
- `deep_extraction_date`: When deep tier ran
- `deep_extractor_model`: Model used (e.g., "qwen2.5:7b")
- `verification`: JSON comparing quick vs deep results
