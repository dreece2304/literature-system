# Semantic Search Architecture

## Overview

The literature management system supports two types of semantic search:

1. **Paper-level search** (`search_level="paper"`) - Searches title + abstract embeddings
2. **Chunk-level search** (`search_level="chunk"`) - Searches full-text content chunks

Chunk-level search is the default and finds content within paper bodies, not just abstracts.

## Architecture

```
Query → EmbeddingGenerator → Query Embedding
                                   ↓
                          ChunkVectorStore (ChromaDB)
                                   ↓
                          Chunk Results (with paper_id)
                                   ↓
                          Deduplicate by Paper
                                   ↓
                          Fetch Paper Metadata (SQLAlchemy)
                                   ↓
                          SearchResults with matching_chunks
```

## Components

### 1. EmbeddingGenerator (`infrastructure/literature-ai/src/embeddings/generator.py`)

Generates embeddings using sentence-transformers:

- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Dimension**: 384
- **Device**: CUDA (GPU) when available

Key methods:
- `generate(text)` - Generate embedding for a query
- `chunk_paper(paper_id, full_text)` - Split paper into TextChunk objects
- `embed_paper_chunks(paper_id, full_text)` - Generate ChunkEmbedding objects

### 2. ChunkVectorStore (`infrastructure/literature-ai/src/embeddings/vectorstore.py`)

ChromaDB collection for chunk embeddings:

- **Collection**: `chunks`
- **Metric**: Cosine similarity
- **Storage**: `infrastructure/literature-ai/data/vectorstore/`

Key methods:
- `add_chunks(chunk_ids, embeddings, texts, metadatas)` - Add chunk embeddings
- `search_chunks(query_embedding, limit, min_score)` - Search for similar chunks
- `delete_paper_chunks(paper_id)` - Remove chunks before re-indexing
- `get_stats()` - Get collection statistics

### 3. SearchService (`src/services/search_service.py`)

Business logic for search operations:

- `semantic_search(query, limit, min_similarity, search_level)` - Main entry point
- `_search_chunks()` - Chunk-level search with paper deduplication
- `_search_papers()` - Paper-level search (title + abstract only)

### 4. MCP Tool (`infrastructure/literature-ai/src/mcp_server/tools/search.py`)

Exposes semantic search to Claude Code:

```python
# Chunk-level search (default) - finds content in paper body
semantic_search(query="ALD precursor mechanism", search_level="chunk")

# Paper-level search - faster, title+abstract only
semantic_search(query="machine learning", search_level="paper")
```

## Chunk Schema

### TextChunk (dataclass)
```python
@dataclass
class TextChunk:
    paper_id: int
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    section: str | None  # e.g., "introduction", "methods", "results"

    @property
    def chunk_id(self) -> str:
        return f"{paper_id}_{chunk_index}"
```

### ChunkEmbedding (dataclass)
```python
@dataclass
class ChunkEmbedding:
    chunk_id: str
    paper_id: int
    chunk_index: int
    text: str
    embedding: list[float]
    section: str | None
```

## Chunking Strategy

- **Chunk size**: ~500 characters (configurable)
- **Overlap**: ~50 characters between chunks
- **Minimum size**: 100 characters (smaller chunks skipped)
- **Section detection**: Identifies academic paper sections (Introduction, Methods, Results, etc.)
- **Sentence boundaries**: Prefers ending chunks at sentence boundaries

## Reindexing

To regenerate chunk embeddings:

```bash
# Show current stats
python -m scripts.reindex_embeddings --stats

# Dry run (preview only)
python -m scripts.reindex_embeddings --dry-run

# Full reindex
python -m scripts.reindex_embeddings

# Single paper
python -m scripts.reindex_embeddings --paper-id 123

# Custom chunk size
python -m scripts.reindex_embeddings --chunk-size 600 --chunk-overlap 100
```

## Statistics (as of indexing)

- Papers with full text: 365
- Papers indexed: 364
- Total chunks: 50,209
- Average chunks per paper: ~138

## Search Response Format

```json
{
  "query": "ALD precursor delivery",
  "search_type": "semantic_chunk",
  "count": 3,
  "results": [
    {
      "id": 279,
      "title": "Recent developments in molecular precursors...",
      "year": 2024,
      "authors": ["Smith, J.", "Jones, A."],
      "abstract": "...",
      "doi": "10.1234/example",
      "tags": ["ALD", "precursors"],
      "score": 0.7,
      "matching_chunks": [
        {
          "text": "...precursor delivery mechanism involves...",
          "score": 0.7,
          "section": "methods",
          "chunk_index": 42
        }
      ]
    }
  ],
  "matching_chunks": {
    "279": [...all matching chunks for paper 279...]
  }
}
```

## Troubleshooting

### "No results" for chunk search
1. Verify chunks are indexed: `python -m scripts.reindex_embeddings --stats`
2. Lower `min_similarity` threshold (default: 0.5)
3. Check papers have full_text populated

### Import errors with SearchService
The `infrastructure/literature-ai/src/services/__init__.py` re-exports from `src/services/` to avoid shadowing. If issues persist, ensure `src/` is on sys.path before infrastructure paths.

### Slow search performance
- Chunk search queries 3x the limit then deduplicates
- Consider using `search_level="paper"` for faster results
- GPU (CUDA) significantly speeds up embedding generation
