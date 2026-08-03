# Literature Management System Architecture

## Directory Structure (Updated July 2026)

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
│   │   ├── reranking_service.py      # Cross-encoder re-ranking
│   │   ├── search_diagnostics_service.py # Search health diagnostics
│   │   ├── collection_service.py     # Collection management
│   │   ├── note_service.py           # Notes on papers
│   │   ├── pdf_service.py            # PDF acquisition & management
│   │   ├── citation_service.py       # BibTeX, citations, manuscript scanning
│   │   ├── import_export_service.py  # Import/export operations
│   │   ├── paper_import_service.py   # Import wizard (duplicate check, enrichment)
│   │   ├── external_search.py        # CrossRef, Semantic Scholar, arXiv APIs
│   │   ├── extraction_service.py     # AI-powered extraction (Ollama/Claude)
│   │   ├── extraction_prompts.py     # Extraction prompt templates
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
│   │   │   ├── pdf.py                # PDF acquisition (acquire_pdf, manage_pdf)
│   │   │   ├── external.py           # External API lookups
│   │   │   ├── project.py            # LaTeX/BibTeX project tools
│   │   │   ├── citations.py          # Manuscript analysis, citation formatting
│   │   │   ├── discovery.py          # semantic_find, embeddings, reading queue
│   │   │   ├── extraction.py         # AI extraction, PDF processing queue
│   │   │   ├── import_export.py      # import_paper, export, enrichment queue
│   │   │   ├── validation.py         # Paper validation
│   │   │   ├── citation_network.py   # Citation graph, claim citations
│   │   │   └── browser_pdf.py        # Internal helpers for pdf.py (no tools)
│   │   └── resources/                # MCP resources
│   │
│   ├── embeddings/                   # Vector search
│   │   ├── generator.py              # EmbeddingGenerator (sentence-transformers)
│   │   ├── vectorstore.py            # VectorStore, ChunkVectorStore (ChromaDB)
│   │   └── chunker.py                # Text chunking logic
│   │
│   ├── extractors/                   # UNUSED legacy package (no imports from src/)
│   │   ├── metadata_extractor.py     # Regex DOI/arXiv metadata parsing (unused)
│   │   └── pdf_extractor.py          # PDF text extraction (unused; live path is PDFService)
│   │
│   ├── config/                       # Application settings
│   │   └── ai_settings.py            # Ollama/LLM configuration
│   │
│   ├── alembic/                      # Database migrations
│   │   ├── versions/                 # Migration scripts
│   │   └── env.py                    # Alembic environment
│   │
│   └── scripts/                      # CLI utilities
│       ├── zotero_import.py          # Offline Zotero import (reads zotero.sqlite snapshot)
│       ├── reindex_embeddings.py     # Rebuild ChromaDB index
│       ├── health_check.py           # Health checks
│       └── ...                       # backup, maintenance, batch extraction, etc.
│
├── data/                             # Data storage (SOURCE OF TRUTH)
│   ├── literature.db                 # SQLite database (~600 papers)
│   ├── pdfs/                         # Locally acquired PDFs
│   ├── vectorstore/                  # ChromaDB collections
│   │   └── chroma.sqlite3            # Paper + chunk embeddings
│   ├── config/                       # LEGACY — not read by any code (see note below)
│   │   ├── credentials.yml           # Old Zotero API key file (git-ignored, unused)
│   │   └── settings.yml              # Old Zotero settings (unused)
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

AI/embedding configuration lives in `src/config/ai_settings.py` (env prefixes `OLLAMA_`,
`EMBEDDING_`, `RERANKER_`).

**Legacy config note**: `data/config/settings.yml` and `data/config/credentials.yml` are
leftovers from the pre-refactor Zotero sync and are read by NO current code.
Do not edit them expecting behavior changes — real configuration is `LITCORE_*` env vars plus
`src/config/ai_settings.py`. The files are kept in place because credentials live there.

### 5. Embedding Architecture
- **Chunk-level**: Full-text chunks for deep content search
- **Paper-level**: Title + abstract for quick similarity
- Default model: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions); a dual-model
  setup (SPECTER2 paper-level + BGE chunk-level, 768 dimensions) is configured in
  `src/config/ai_settings.py` behind the `use_dual_models` flag
- Storage: ChromaDB with cosine similarity
- Stats: ~50K chunk embeddings from papers with full text

---

## Service Layer

| Service | Purpose |
|---------|---------|
| `PaperService` | Paper CRUD, metadata, store_extraction, batch operations |
| `SearchService` | FTS5 keyword search, RRF rank fusion |
| `UnifiedSearchService` | Smart search facade (acronyms, spelling, mode selection) |
| `EmbeddingService` | ChromaDB vector search (paper & chunk level) |
| `ExtractionService` | AI extraction (Ollama), PDF processing queue, quality checks |
| `RerankingService` | Cross-encoder re-ranking of search results |
| `CollectionService` | Hierarchical collections |
| `NoteService` | Paper annotations |
| `PDFService` | PDF download, text extraction |
| `CitationService` | BibTeX, manuscript scanning, citation health |
| `ImportExportService` | BibTeX import/export |
| `PaperImportService` | Import wizard (duplicate check, enrichment) |
| `ExternalSearchService` | CrossRef, Semantic Scholar, OpenAlex, arXiv APIs |
| `ValidationService` | Paper verification against external sources |

---

## MCP Tools

| Module | Key Tools |
|--------|-----------|
| papers | `list_papers`, `get_paper`, `add_paper`, `update_paper`, `store_extraction`, `get_paper_content`, `get_papers_summary`, `batch_update_papers`, `batch_delete_papers` |
| search | `search` (unified with mode parameter), `get_search_status` |
| pdf | `acquire_pdf`, `manage_pdf`, `find_duplicates` |
| extraction | `extract_paper`, `extract_papers_batch`, `prepare_extraction`, `get_extraction_status`, `manage_pdf_processing`, `manage_references`, `verify_extraction`, `flag_for_deep_extraction` |
| collections | `list_collections`, `get_collection`, `create_collection`, `update_collection`, `delete_collection`, `add_papers_to_collection`, `remove_papers_from_collection`, `get_collection_children` |
| notes | `list_notes`, `get_note`, `create_note`, `update_note`, `delete_note`, `delete_paper_notes` |
| import_export | `import_paper`, `export`, `get_enrichment_queue` |
| external | `lookup_paper_metadata`, `search_external_papers`, `enrich_paper`, `find_open_access_pdf`, `get_citation_count` |
| project | `manage_bibtex`, `citation_health_check`, `scan_citations`, `manage_project` |
| citations | `manuscript_tools`, `format_citation` |
| discovery | `semantic_find`, `manage_embeddings`, `get_reading_queue`, `suggest_paper_tags` |
| validation | `validate_papers`, `get_validation_status` |
| citation_network | `get_citations`, `get_local_citations`, `find_common_references`, `build_citation_graph`, `import_references_from_paper`, `link_papers_citation`, claim-citation tools |
| browser_pdf | (no tools — internal helpers used by `pdf.py`) |

Zotero import is not an MCP tool: run `src/scripts/zotero_import.py` (offline reader of a
`zotero.sqlite` snapshot; dry-run by default, `--execute` to apply).

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
Runs automatically on import or via the `store_extraction` tool:
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
