# Research — Literature Management System

Intelligent literature management for a research library, exposed to Claude Code
and Claude Desktop over MCP (Model Context Protocol). Papers, PDFs, full-text and
semantic search, citation graphs, and local-LLM extraction all run against a
single SQLite database plus a ChromaDB vector store.

## Quick Start

### 1. Environment

```bash
mamba env create -f environment.yml   # creates the `litai` env
```

### 2. Verify setup

```bash
cd src && mamba run -n litai python -m scripts.health_check
```

Expected output:

```
[PASS] Database: Database OK: 601 papers
[PASS] Services: PaperService OK
[PASS] Embeddings: OK
[PASS] Keyword Search: OK
[PASS] Semantic Search: OK
ALL CHECKS PASSED
```

### 3. Use with Claude Code

`.mcp.json` in the repo root registers the server; Claude Code connects
automatically when you open this project. The config is path-independent — it
resolves `${MAMBA_EXE}` and `${CLAUDE_PROJECT_DIR}` at launch, so it needs no
edits when the repo moves or is cloned onto another machine.

Then just ask, in natural language:

- "Find papers about ALD precursor chemistry"
- "Generate BibTeX for papers 42, 55, 78"
- "Verify the citations in my chapter.tex"
- "Get the citation count for paper 123"

## Layout

```
research/
├── src/
│   ├── literature_core/    # SQLAlchemy models, DB session, config, constants
│   ├── services/           # Business logic (search, papers, extraction, ...)
│   ├── mcp_server/         # MCP server + tool modules (thin wrappers)
│   ├── embeddings/         # ChromaDB vector store and generator
│   ├── context/            # Manuscript parsing
│   ├── config/             # AI/Ollama settings
│   ├── scripts/            # Operational scripts (health_check, backup, ...)
│   └── alembic/            # Database migrations
├── tests/                  # unit/, integration/, fixtures/
├── data/                   # Runtime state (git-ignored)
│   ├── literature.db       # SQLite database
│   ├── pdfs/               # PDF storage
│   └── vectorstore/        # ChromaDB embeddings
├── docs/                   # Documentation (see below)
├── notebooks/              # Exploratory notebooks
└── environment.yml         # Conda environment spec
```

## Library Snapshot

| Metric | Count |
|--------|-------|
| Papers | 601 |
| Papers with PDFs | 473 |
| Papers with chunked text | 475 |
| Collections | 6 |

## Search

Search is a single `search` tool with a `mode` parameter, backed by SQLite FTS5
(BM25) and ChromaDB vectors fused with Reciprocal Rank Fusion:

```
search("ALD precursor chemistry")                  # mode="smart" (default)
search("hafnium oxide", mode="keyword")            # exact term matching
search("thin film growth mechanisms", mode="semantic")
search("area-selective deposition", mode="hybrid") # BM25 + vectors via RRF
get_search_status(detailed=true)                   # search health
```

`smart` mode adds acronym expansion, spelling correction, and automatic mode
selection on top of the above.

## Common Commands

```bash
# Tests (from repo root)
mamba run -n litai python -m pytest tests/ -q

# Lint
mamba run -n litai python -m flake8 src/

# Database migrations (from src/)
mamba run -n litai alembic upgrade head

# Data integrity
mamba run -n litai python -m scripts.integrity_check
mamba run -n litai python -m scripts.paper_health_check

# Enrichment batch runner (chunk -> deep-extract -> verify)
mamba run -n litai python -m scripts.enrich_pipeline --stage all --limit 20
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — schema, services, data flow, config
- [Workflows](docs/WORKFLOWS.md) — import and query pipelines
- [Tool Reference](docs/TOOL_REFERENCE.md) — all MCP tool signatures
- [Porting](docs/PORTING.md) — moving the system to another machine
- [Source Guide](src/README.md) — code structure
- [Claude Guidelines](CLAUDE.md) — conventions for AI agent sessions

Superseded design docs are kept under `docs/archive/` for reference.

## Requirements

- Python 3.11 via mamba/conda (`litai` environment)
- Ollama for local-LLM extraction — optional; every other feature degrades
  gracefully without it
- GPU optional; embeddings run CPU-only, just slower
