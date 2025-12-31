# Search Architecture

## Overview

The literature management system implements industry-standard **hybrid search** combining:

1. **SQLite FTS5** - Full-text keyword search with BM25 ranking
2. **ChromaDB** - Semantic vector search with embeddings
3. **Reciprocal Rank Fusion (RRF)** - Intelligent result merging

This architecture ensures comprehensive search coverage:
- **Keyword search** finds exact term matches using proven BM25 algorithm
- **Semantic search** finds conceptually similar content even without keyword overlap
- **Hybrid search** combines both for best-of-both-worlds discovery

## Search Tools

| Tool | Best For | Algorithm |
|------|----------|-----------|
| `hybrid_search` ⭐ | General literature discovery | FTS5 + ChromaDB + RRF |
| `keyword_search` | Exact term matching | SQLite FTS5 BM25 |
| `semantic_search` | Conceptual similarity | ChromaDB embeddings |
| `search_by_author` | Author lookup | SQL partial match |
| `search_by_tag` | Tag filtering | SQL partial match |
| `get_search_status` | Troubleshooting | Health diagnostics |

## Architecture Diagram

```
                           User Query
                               │
                               ▼
                    ┌─────────────────────┐
                    │   hybrid_search     │  (MCP Tool)
                    │   alpha = 0.65      │
                    └─────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
    ┌──────────────────┐              ┌──────────────────┐
    │   FTS5 Search    │              │ Semantic Search  │
    │   (Keyword)      │              │  (Embeddings)    │
    │                  │              │                  │
    │  Porter Stemmer  │              │  MiniLM-L6-v2    │
    │  BM25 Ranking    │              │  384 dimensions  │
    └──────────────────┘              └──────────────────┘
              │                                 │
              │ weight: 1 - alpha               │ weight: alpha
              │        (0.35)                   │      (0.65)
              │                                 │
              └────────────────┬────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Reciprocal Rank     │
                    │ Fusion (k=60)       │
                    │                     │
                    │ score = Σ(w/(k+r))  │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Merged Results     │
                    │  with diagnostics   │
                    └─────────────────────┘
```

## Components

### 1. FTS5 Full-Text Search

**Module**: `src/literature_core/fts.py`

SQLite FTS5 provides:
- **Porter stemmer tokenization** - "running" matches "run", "runs"
- **BM25 ranking** - Term frequency-inverse document frequency
- **Snippet generation** - Highlighted matching text
- **Unicode support** - Full international character handling

**Schema**:
```sql
CREATE VIRTUAL TABLE papers_fts USING fts5(
    title, abstract, full_text,
    content='papers',
    content_rowid='id',
    tokenize='porter unicode61'
);
```

**Sync triggers** automatically keep FTS5 indexed with the papers table.

### 2. ChromaDB Semantic Search

**Module**: `src/embeddings/`

ChromaDB provides:
- **Vector storage** for paper embeddings
- **Cosine similarity** search
- **Chunk-level search** for finding content within paper bodies

**Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2`
- 384 dimensions
- CUDA acceleration when available
- Normalized embeddings for cosine similarity

**Search Levels**:
- `"paper"` - Searches title + abstract embeddings (faster)
- `"chunk"` - Searches full-text chunks (more precise, finds content in paper body)

### 3. Hybrid Search Service

**Module**: `src/services/hybrid_search_service.py`

Implements **Reciprocal Rank Fusion (RRF)**:

```
score(d) = Σ(weight_i × 1/(k + rank_i(d)))
```

Where:
- `k = 60` (standard RRF constant)
- `weight_keyword = 1 - alpha`
- `weight_semantic = alpha`
- `alpha = 0.65` (default, balanced toward semantic)

**Alpha parameter**:
- `alpha = 0.0` → Keyword only (pure FTS5 BM25)
- `alpha = 1.0` → Semantic only (pure ChromaDB)
- `alpha = 0.65` → Balanced (default, slightly prefers semantic)

### 4. Search Diagnostics

**Module**: `src/services/search_diagnostics_service.py`

Provides health checks for:
- FTS5 index availability and paper count
- ChromaDB vector store status
- Embedding coverage percentage
- Actionable recommendations

Use `get_search_status(detailed=true)` to troubleshoot search issues.

## Configuration

### Similarity Threshold

Default: `0.35` (discovery-focused)

Located in:
- `src/config/ai_settings.py` - `score_threshold`
- `src/literature_core/config.py` - `chroma_score_threshold`
- `src/literature_core/constants.py` - `DEFAULT_MIN_SIMILARITY`

Lower values (0.2-0.4) find more results with broader relevance.
Higher values (0.6-0.8) are more restrictive but higher confidence.

### Chunking Parameters

Located in `src/literature_core/config.py`:
- `chunk_size: 512` - Characters per chunk
- `chunk_overlap: 128` - Overlap between chunks

## Usage Examples

### Hybrid Search (Recommended)

```python
# Best for general literature discovery
hybrid_search(query="ALD precursor chemistry")

# Adjust weighting
hybrid_search(query="hafnium oxide ALD", alpha=0.3)  # More keyword-focused
hybrid_search(query="thin film growth mechanisms", alpha=0.8)  # More semantic

# With year filtering
hybrid_search(query="plasma ALD", year_min=2020, year_max=2024)
```

### Keyword Search

```python
# Exact term matching with BM25 ranking
keyword_search(query="hafnium oxide")

# Boolean-like queries
keyword_search(query="ALD precursor delivery")
```

### Semantic Search

```python
# Find conceptually similar papers
semantic_search(query="atomic layer deposition thin film growth")

# Search within paper bodies
semantic_search(query="precursor mechanism", search_level="chunk")

# Title + abstract only (faster)
semantic_search(query="machine learning", search_level="paper")
```

### Check Search Health

```python
# Quick status
get_search_status()

# Detailed diagnostics with recommendations
get_search_status(detailed=true)
```

## Fallback Behavior

The system handles failures gracefully:

1. **If semantic search fails**: Returns results with `fallback_used: true` and `fallback_reason`
2. **If FTS5 unavailable**: Hybrid search uses semantic only
3. **If both unavailable**: Returns empty results with error diagnostics

## Maintenance

### Rebuild FTS5 Index

```bash
# Check index status
python src/scripts/migrate_fts5.py --check

# Rebuild from scratch
python src/scripts/migrate_fts5.py --rebuild

# Optimize index
python src/scripts/migrate_fts5.py --optimize
```

### Regenerate Embeddings

```bash
# Check embedding stats
python -m scripts.reindex_embeddings --stats

# Full reindex
python -m scripts.reindex_embeddings

# Single paper
python -m scripts.reindex_embeddings --paper-id 123
```

## Statistics

Current database:
- **427 papers** indexed in FTS5
- **365 papers** with full text
- **~50,000 chunks** in ChromaDB

## Files Reference

| File | Description |
|------|-------------|
| `src/literature_core/fts.py` | FTS5 virtual tables, triggers, BM25 search |
| `src/services/hybrid_search_service.py` | RRF algorithm, hybrid search logic |
| `src/services/search_service.py` | SearchService with keyword/semantic methods |
| `src/services/search_diagnostics_service.py` | Health checks and diagnostics |
| `src/mcp_server/tools/search.py` | MCP tool wrappers |
| `src/embeddings/generator.py` | Embedding generation |
| `src/embeddings/vectorstore.py` | ChromaDB vector store |
| `src/scripts/migrate_fts5.py` | FTS5 migration CLI |

## Troubleshooting

### No results from keyword search

1. Check FTS5 index: `python src/scripts/migrate_fts5.py --check`
2. If `needs_rebuild`, run: `python src/scripts/migrate_fts5.py --rebuild`

### No results from semantic search

1. Check embedding coverage: `get_search_status(detailed=true)`
2. If coverage is low, regenerate embeddings
3. Try lowering `min_similarity` (default 0.35)

### Slow search performance

1. For keyword search: Run `--optimize` on FTS5 index
2. For semantic search: Use `search_level="paper"` instead of `"chunk"`
3. GPU acceleration significantly speeds up embedding generation

---

*Last updated: 2025-12-31*
