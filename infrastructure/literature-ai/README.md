# Literature AI Service

LLM-powered services for paper triage, writing assistance, and Q&A. Part of the research monorepo infrastructure.

## Overview

The literature-ai service provides intelligent AI capabilities for academic research:

1. **Writer Agent**: Context-aware citation suggestions for manuscripts
2. **Triager Agent**: Intelligent paper scoring and prioritization (0-10 scale)
3. **Reader Agent**: RAG-powered Q&A over your paper collection
4. **MCP Server**: Claude Code integration for direct AI-powered paper management

## MCP Server for Claude Code (Recommended)

The system now includes an MCP (Model Context Protocol) server that integrates directly with Claude Code. This means **Claude Code itself becomes the AI** - no local LLMs or separate API keys needed.

### Quick Start with Claude Code

```bash
# 1. Start literature-database
cd infrastructure/literature-database
mamba run -n litai uvicorn src.api.main:app --port 8001

# 2. Restart Claude Code in the research project
# The MCP server is already configured in ~/.claude.json

# 3. Ask Claude to use literature tools:
#    "Search for papers about machine learning"
#    "Get the content of paper 42 and summarize it"
#    "Find papers by author Smith"
```

### MCP Tools Available (23)

| Category | Tools |
|----------|-------|
| Paper Management | list_papers, get_paper, add_paper, update_paper, search_papers, get_paper_content, store_extraction, get_extraction_queue |
| Search | keyword_search, semantic_search, search_by_author, search_by_tag |
| External APIs | lookup_paper_metadata, find_open_access_pdf, enrich_paper, search_external_papers, get_citation_count |
| Citations | scan_manuscript, check_citations, suggest_citation_key, generate_bibtex, format_bibliography, validate_citations |

See [QUICKSTART.md](QUICKSTART.md) for detailed usage.

---

## Standalone Mode (Legacy)

For local LLM processing with GPU acceleration:

## Architecture

- **LLM Provider**: Ollama with Qwen 7B models
- **Vector Database**: ChromaDB (SQLite-backed)
- **Embedding Model**: sentence-transformers/all-MiniLM-L6-v2 (384d, 80MB)
- **API Framework**: FastAPI with async support
- **Task Queue**: Celery + Redis for background embedding generation
- **Event-Driven**: Consumes paper.added/updated events from literature-database

## GPU Requirements

Optimized for **RTX 4070 8GB VRAM**:
- Writer: qwen:7b-q5_K_M (~5.5GB VRAM, temperature 0.7)
- Triager: qwen:7b-q4_K_M (~4.5GB VRAM, temperature 0.3)
- Reader: qwen:7b-q5_K_M (~5.5GB VRAM, temperature 0.1)
- Models are serialized (one at a time) with 60s keep-alive

## Quick Start

### 1. Prerequisites
```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve

# Pull required models
ollama pull qwen:7b-q5_K_M
ollama pull qwen:7b-q4_K_M
```

### 2. Create Environment
```bash
cd infrastructure/literature-ai
conda env create -f environment.yml
conda activate litai
```

### 3. Configure Service
```bash
# Create .env file (optional - defaults work for local development)
cp .env.example .env

# Edit if needed
nano .env
```

### 4. Start API Server
```bash
# From literature-ai directory
uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload

# Server will be available at http://localhost:8002
# API documentation at http://localhost:8002/docs
```

### 5. Test the Service
```bash
# Run API tests
python scripts/test_api.py

# Or use curl
curl http://localhost:8002/health
```

## API Endpoints

Full interactive documentation available at: **http://localhost:8002/docs**

### System Endpoints
- `GET /` - Service information
- `GET /api/v1/health` - Health check with component status
- `GET /api/v1/stats` - System statistics
- `GET /api/v1/gpu` - GPU status and memory usage

### Writer Agent ✅ **IMPLEMENTED**
- `POST /api/v1/writer/suggest-citations` - Get citation suggestions for text
- `POST /api/v1/writer/expand-outline` - Expand outline with citations
- `POST /api/v1/writer/detect-missing-citations` - Find unsupported claims
- `POST /api/v1/writer/enhance-citation` - Improve existing citation usage

### Context Management ✅ **IMPLEMENTED**
- `POST /api/v1/context/load-manuscript` - Load LaTeX/Markdown manuscript
- `POST /api/v1/context/update` - Update writing context
- `GET /api/v1/context/current` - Get current writing context
- `GET /api/v1/context/outline` - Get manuscript structure
- `POST /api/v1/context/refresh` - Reload manuscript from disk
- `GET /api/v1/context/stats` - Context tracking statistics

### Search & Bibliography ✅ **IMPLEMENTED**
- `POST /api/v1/search/` - Semantic search across papers
- `POST /api/v1/search/similar` - Find similar papers
- `POST /api/v1/search/paper/summary` - Get paper details
- `GET /api/v1/search/stats` - Collection statistics
- `POST /api/v1/search/bibliography` - Generate bibliography (APA/MLA/Chicago/BibTeX)
- `POST /api/v1/search/inline-citation` - Format inline citations

### Triager Agent 🚧 **PLANNED**
- `POST /api/v1/triager/score-paper` - Score single paper (0-10)
- `POST /api/v1/triager/score-batch` - Batch score multiple papers
- `GET /api/v1/triager/top-papers` - Get top-scored papers

### Reader Agent 🚧 **PLANNED**
- `POST /api/v1/reader/ask` - Ask question about papers (RAG)
- `POST /api/v1/reader/summarize` - Summarize specific paper
- `GET /api/v1/reader/related` - Find related papers

## Configuration Files

- `config/settings.py` - Main service configuration (Pydantic settings)
- `config/models.yaml` - LLM model specifications and parameters
- `config/prompts/*.yaml` - Agent-specific prompt templates
- `.env` - Environment variables (API keys, database URLs)

## Project Structure

```
literature-ai/
├── config/              # Configuration files
│   ├── prompts/        # LLM prompt templates
│   ├── settings.py     # Main settings
│   └── models.yaml     # Model configurations
├── src/
│   ├── api/            # FastAPI application
│   │   ├── endpoints/  # API route handlers
│   │   ├── main.py     # Main FastAPI app
│   │   └── schemas.py  # Pydantic request/response models
│   ├── agents/         # Agent implementations
│   │   ├── base.py     # BaseAgent abstract class
│   │   ├── writer.py   # WriterAgent
│   │   ├── triager.py  # TriagerAgent
│   │   └── reader.py   # ReaderAgent
│   ├── embeddings/     # Embedding pipeline
│   │   ├── generator.py    # EmbeddingGenerator
│   │   ├── vectorstore.py  # ChromaDB wrapper
│   │   └── chunker.py      # Text chunking
│   ├── context/        # Manuscript context detection
│   │   ├── detector.py     # ContextDetector
│   │   ├── parser.py       # LaTeX/Markdown parser
│   │   └── tracker.py      # Context state tracking
│   ├── tasks/          # Celery async tasks
│   │   ├── celery_app.py   # Celery configuration
│   │   └── embedding_tasks.py  # Background tasks
│   ├── events/         # Event consumers
│   │   └── consumer.py     # Redis event listener
│   ├── services/       # Core services
│   │   ├── llm_service.py      # Ollama/Qwen wrapper
│   │   ├── search_service.py   # Semantic search
│   │   └── citation_service.py # BibTeX generation
│   └── utils/          # Utilities
│       ├── gpu_manager.py  # GPU memory management
│       ├── logging.py      # Structured logging
│       └── cache.py        # Response caching
├── tests/              # Test suite
│   ├── unit/          # Unit tests
│   └── integration/   # Integration tests
├── scripts/           # Utility scripts
├── data/              # Data storage
│   ├── vectorstore/   # ChromaDB persistence
│   └── cache/         # Cache storage
└── logs/              # Log files

```

## Development

### Running Tests
```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=src tests/
```

### Code Quality
```bash
# Format code
black src/ tests/

# Type checking
mypy src/

# Linting
ruff check src/
```

## Monitoring

- Health check: `GET /health`
- Metrics: `GET /metrics` (Prometheus format)
- Logs: `logs/literature-ai.log`

## Integration with Literature Database

The service automatically:
1. Listens for `paper.added` and `paper.updated` events via Redis
2. Generates embeddings for new/updated papers
3. Stores vectors in ChromaDB
4. Makes papers searchable within ~30 seconds

## External API Integration

The service integrates with multiple academic APIs for metadata enrichment and PDF acquisition:

| API | Purpose | Rate Limit |
|-----|---------|------------|
| CrossRef | DOI resolution, citation data | 50 req/sec with email |
| OpenAlex | Comprehensive academic metadata | 10 req/sec with email |
| Semantic Scholar | Paper search, citation counts | 1 req/sec with API key |
| Springer Meta v2 | Nature/Springer publications | Standard |
| Springer Open Access | Free full-text PDFs | Standard |
| Unpaywall | Open access PDF URLs | 100K req/day |
| arXiv | Preprints and e-prints | No limit |
| PubMed | Biomedical literature | 10 req/sec with email |

All APIs use exponential backoff for rate limiting (configured in `src/services/external_search.py`).

## Data Enrichment Scripts

### Enrich Paper Metadata
```bash
# Enrich papers missing abstracts using external APIs
mamba run -n litai python scripts/enrich_papers.py
```

This script:
- Fetches papers with missing/short abstracts
- Tries CrossRef → OpenAlex → Semantic Scholar → arXiv
- Captures citation counts from Semantic Scholar
- Updates papers via the literature-database API

### Acquire Open Access PDFs
```bash
# Download PDFs and extract full text
mamba run -n litai python scripts/acquire_pdfs.py
```

This script:
- Finds papers without PDFs but with DOI/arXiv ID
- Checks Unpaywall → Springer OA → Semantic Scholar → arXiv
- Downloads PDFs to `data/pdfs/`
- Extracts full text using pdfplumber
- Updates database with file_path, full_text, word_count

### Sync Papers to Vectorstore
```bash
# Sync all papers from database to ChromaDB
mamba run -n litai python scripts/sync_papers.py
```

## Overnight Development

The project is configured for autonomous overnight development with TDD:

```bash
# Configuration in .overnight-dev.json
# Git hooks installed at repo root

# Run both service tests (252 total)
cd infrastructure/literature-database && mamba run -n litai pytest tests/ -q
cd infrastructure/literature-ai && mamba run -n litai pytest tests/ -q
```

Git hooks enforce:
- All tests must pass before commit
- Linting with flake8
- Conventional commit format

## Troubleshooting

### GPU Memory Issues
```bash
# Check VRAM usage
nvidia-smi

# Clear Ollama cache
ollama ps
ollama stop <model-name>
```

### Vector Store Issues
```bash
# Reset vector store
rm -rf data/vectorstore/*
python scripts/initialize_embeddings.py
```

### Redis Connection Issues
```bash
# Check Redis
redis-cli ping

# Restart Redis
sudo systemctl restart redis
```

## Performance

Target metrics for <1K papers:
- Embedding generation: ~50 papers/minute
- Citation suggestion latency: <2s
- Paper scoring: <500ms per paper
- Q&A response: <3s

## License

Part of the research monorepo project.
