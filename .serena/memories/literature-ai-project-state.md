# Literature Management System - Project State

## Overview
A unified research literature management system with MCP (Model Context Protocol) integration for Claude Code and Claude Desktop. Provides paper search, metadata enrichment, citation management, and PDF acquisition.

## Current Status (January 2026)

### Database
- **445+ papers** in SQLite database
- **Data location**: `data/literature.db`
- **Vectorstore**: `data/vectorstore/` (ChromaDB, ~97% embedding coverage)
- **PDFs**: Most in Zotero (`/mnt/c/Users/dreec/Zotero/storage/`), some locally in `data/pdfs/`

### Project Structure
```
src/
├── mcp_server/         # MCP server and tools
├── services/           # Business logic (PaperService, SearchService, etc.)
├── literature_core/    # Database models, ORM, config, exceptions
├── embeddings/         # ChromaDB vector search
├── extractors/         # Zotero sync
└── config/             # Settings (ai_settings.py)
tests/
├── unit/services/      # Unit tests
├── integration/tools/  # MCP tool tests
└── fixtures/           # Shared fixtures
```

### API Keys Configured
| API | Status | Environment Variable |
|-----|--------|---------------------|
| CrossRef | ✅ Working | `CROSSREF_EMAIL` |
| OpenAlex | ✅ Working | `OPENALEX_EMAIL` |
| Semantic Scholar | ✅ Working (1 req/sec) | `SEMANTIC_SCHOLAR_API_KEY` |
| Springer | ✅ Working | `SPRINGER_API_KEY` |
| Unpaywall | ✅ Working | `UNPAYWALL_EMAIL` |
| arXiv | ✅ Working | No key needed |
| PubMed | ✅ Working | `PUBMED_EMAIL` |

## Environment
- **Conda environment**: `litai`
- **Python**: 3.11
- **GPU**: RTX 4070 8GB VRAM
- **LLM**: Qwen via Ollama (local) or Claude via MCP session

## Key Files
- `src/literature_core/config.py` - Settings configuration
- `src/services/` - All business logic services
- `src/mcp_server/server.py` - MCP server entry point
- `src/mcp_server/tools/` - MCP tool implementations

## Running Tests
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q
```

## Running MCP Server
```bash
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m mcp_server.server
```

## Common Tasks
```bash
# Health check
cd src && mamba run -n litai python -m scripts.health_check

# Linting
mamba run -n litai python -m flake8 src/
```
