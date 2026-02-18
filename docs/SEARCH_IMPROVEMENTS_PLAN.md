# Search & Embedding Improvements Plan

## Overview

This plan covers all improvements to the search and embedding system:
1. Dual model approach (SPECTER2 + BGE)
2. Fix known paper lookup issue
3. HNSW tuning
4. Cross-encoder re-ranking
5. Chunking improvements
6. Batch size optimization

## Phase 1: Fix Known Paper Lookup (Quick Win)

### Problem
- Smart search always runs hybrid (keyword + semantic), adding latency
- Multi-word queries use OR logic, hurting precision
- No exact match prioritization

### Solution
Add "exact" search mode to UnifiedSearchService:
1. For short queries (<5 words), try exact title match first via SQL LIKE
2. Add phrase search option using FTS5 quoted syntax
3. Skip semantic search for obvious exact lookups

### Files to modify
- `src/services/unified_search_service.py` - Add exact mode
- `src/mcp_server/tools/search.py` - Expose exact mode

## Phase 2: Dual Model Embedding Architecture

### Paper-level: SPECTER2
- Model: `allenai/specter2_base`
- Dimension: 768
- Purpose: Paper similarity, related work discovery
- Index: Papers only (title + abstract)

### Chunk-level: BGE-base-en-v1.5
- Model: `BAAI/bge-base-en-v1.5`
- Dimension: 768
- Purpose: Full-text retrieval, factual lookup
- Index: PDF chunks

### Implementation
1. Add model configs to `ai_settings.py`
2. Create separate ChromaDB collections
3. Update `vectorstore.py` for dual models
4. Migration script for re-indexing

## Phase 3: HNSW Tuning

### Current (defaults)
- ef_construction: 100
- ef_search: 10
- M: 16

### Recommended
- ef_construction: 200 (better index quality)
- ef_search: 64 (better recall)
- M: 32 (more connections)

### Implementation
- Update ChromaDB collection metadata
- Requires re-indexing

## Phase 4: Cross-encoder Re-ranking

### Model
- `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Fast, good quality for re-ranking

### Strategy
1. Retrieve top-50 candidates via hybrid search
2. Re-rank with cross-encoder
3. Return top-20

### Implementation
- Add to `ai_settings.py`
- Create `services/reranking_service.py`
- Integrate into unified search

## Phase 5: Chunking Improvements

### Current
- Size: 512 tokens
- Overlap: 128 tokens

### Recommended
- Size: 768-1024 tokens (more context)
- Overlap: 192-256 tokens (better boundaries)
- Consider: sentence-aware chunking

### Implementation
- Update `ai_settings.py`
- Re-chunk all PDFs
- Re-embed chunks

## Phase 6: Batch Size Optimization

### Current: 32
### Recommended: 64

With RTX 4070 (8GB VRAM):
- BGE-base: ~1.5GB model
- Batch 64 @ 768 tokens: ~2GB working memory
- Total: ~3.5GB, well within limits

## Implementation Order

1. **Phase 1** (Quick): Fix exact lookup (immediate impact)
2. **Phase 3** (Easy): HNSW tuning (config change + reindex)
3. **Phase 6** (Easy): Batch size (config change)
4. **Phase 2** (Medium): Dual models (new architecture)
5. **Phase 5** (Medium): Re-chunk PDFs
6. **Phase 4** (Medium): Cross-encoder re-ranking

## Re-indexing Strategy

After all changes, run:
```bash
# 1. Re-chunk PDFs with new settings
cd src && mamba run -n litai python scripts/chunk_pdfs.py --all --force

# 2. Re-embed papers with SPECTER2
cd src && mamba run -n litai python scripts/reindex_embeddings.py --papers --model specter2

# 3. Re-embed chunks with BGE
cd src && mamba run -n litai python scripts/reindex_embeddings.py --chunks --model bge
```

## Configuration Changes Summary

```python
# ai_settings.py additions

class EmbeddingSettings:
    # Paper-level embeddings (SPECTER2)
    paper_model_name: str = "allenai/specter2_base"
    paper_dimension: int = 768

    # Chunk-level embeddings (BGE)
    chunk_model_name: str = "BAAI/bge-base-en-v1.5"
    chunk_dimension: int = 768

    # Improved chunking
    chunk_size: int = 768  # was 512
    chunk_overlap: int = 192  # was 128

    # Batch size
    batch_size: int = 64  # was 32

class ChromaDBSettings:
    # HNSW tuning
    hnsw_ef_construction: int = 200  # was 100
    hnsw_ef_search: int = 64  # was 10
    hnsw_m: int = 32  # was 16

class RerankerSettings:
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k_candidates: int = 50
    top_k_results: int = 20
```
