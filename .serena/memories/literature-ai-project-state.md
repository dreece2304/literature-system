# Literature AI Project State

## Overview
The literature-ai service is part of a monorepo for research literature management. It provides LLM-powered services for academic research including paper search, metadata enrichment, and PDF acquisition.

## Current Status (December 2024)

### Database
- **426 papers** in literature-database
- **66 papers** were missing abstracts (to be enriched)
- Schema supports: `full_text`, `file_path`, `abstract`, `doi`, `arxiv_id`, `pubmed_id`, `citation_count`

### API Keys Configured
| API | Status | Environment Variable |
|-----|--------|---------------------|
| CrossRef | ✅ Working | `CROSSREF_EMAIL` |
| OpenAlex | ✅ Working | `OPENALEX_EMAIL` |
| Semantic Scholar | ✅ Working (1 req/sec) | `SEMANTIC_SCHOLAR_API_KEY` |
| Springer Meta v2 | ✅ Working | `SPRINGER_API_KEY` |
| Springer Open Access | ✅ Working | `SPRINGER_OPENACCESS_API_KEY` |
| Unpaywall | ✅ Working | `UNPAYWALL_EMAIL` |
| arXiv | ✅ Working | No key needed |
| PubMed | ✅ Working | `PUBMED_EMAIL` |
| Wiley | ✅ Configured | `WILEY_API_TOKEN` |

### Scripts Available
1. **`scripts/enrich_papers.py`** - Enriches papers missing abstracts using external APIs
2. **`scripts/acquire_pdfs.py`** - Downloads open access PDFs and extracts full text
3. **`scripts/sync_papers.py`** - Syncs papers from literature-database to vectorstore

### Overnight Dev Setup
- Config: `.overnight-dev.json`
- Git hooks installed at repo root
- Test command runs both services (252 tests total)
- Uses `litai` conda environment

## Environment
- **Conda environment**: `litai`
- **Python**: 3.11
- **GPU**: RTX 4070 8GB VRAM
- **LLM**: Qwen via Ollama (local)

## Key Files
- `config/settings.py` - Pydantic settings configuration
- `src/services/external_search.py` - External API integrations
- `src/embeddings/embedding_service.py` - Sentence transformer embeddings
- `src/context/vectorstore.py` - ChromaDB vectorstore

## Running Tests
```bash
# Both services
cd infrastructure/literature-database && mamba run -n litai pytest tests/ -q
cd infrastructure/literature-ai && mamba run -n litai pytest tests/ -q
```

## Common Tasks
```bash
# Enrich papers missing abstracts
mamba run -n litai python scripts/enrich_papers.py

# Acquire open access PDFs
mamba run -n litai python scripts/acquire_pdfs.py

# Sync papers to vectorstore
mamba run -n litai python scripts/sync_papers.py
```
