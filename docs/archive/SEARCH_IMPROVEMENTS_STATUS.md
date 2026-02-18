# Search Improvements Project Status

**Last Updated**: 2025-12-31
**Branch**: `feature/mcp-plugin`
**Status**: Core Implementation Complete

---

## Executive Summary

Implemented industry-standard hybrid search combining **SQLite FTS5** (BM25 keyword search) with **ChromaDB** (semantic/vector search) using **Reciprocal Rank Fusion (RRF)** for result merging. This replaces the previous broken search that used slow SQL LIKE queries.

---

## Completed Work

### Phase 1: FTS5 Full-Text Search Infrastructure ✅

| Item | File | Description |
|------|------|-------------|
| FTS5 Module | `src/literature_core/fts.py` | FTS5 virtual tables, triggers, BM25 search |
| FTS5 Tests | `tests/unit/services/test_fts_service.py` | 28 tests covering all FTS functionality |
| Database Init | `src/literature_core/database.py` | Auto-creates FTS5 tables on init |
| Migration Script | `src/scripts/migrate_fts5.py` | CLI tool: `--check`, `--rebuild`, `--optimize` |

**Key Features:**
- Porter stemmer tokenization
- Content-less FTS5 tables (references papers table)
- Auto-sync triggers for INSERT/UPDATE/DELETE
- BM25 ranking with snippet support

**Migration Run**: 427 papers indexed successfully

### Phase 2: Hybrid Search Service ✅

| Item | File | Description |
|------|------|-------------|
| Hybrid Service | `src/services/hybrid_search_service.py` | RRF algorithm, combines keyword + semantic |
| Hybrid Tests | `tests/unit/services/test_hybrid_search_service.py` | 18 tests for RRF and hybrid search |
| MCP Tool | `src/mcp_server/tools/search.py` | `hybrid_search` tool exposed via MCP |

**Key Features:**
- Reciprocal Rank Fusion: `score(d) = Σ(weight_i * 1/(k + rank_i(d)))` with k=60
- Configurable alpha (0=keyword only, 1=semantic only, 0.65=balanced default)
- Graceful fallback when components unavailable
- Detailed diagnostics in response

### Phase 3: Diagnostics & Fallback Tracking ✅

| Item | File | Description |
|------|------|-------------|
| Diagnostics Service | `src/services/search_diagnostics_service.py` | Health checks for FTS5, ChromaDB, embeddings |
| Diagnostics Tests | `tests/unit/services/test_search_diagnostics_service.py` | 17 tests |
| Status MCP Tool | `src/mcp_server/tools/search.py` | `get_search_status` tool |
| Fallback Tracking | `src/services/search_service.py` | `fallback_used`, `fallback_reason` fields |

**Key Features:**
- Shows FTS5 index status and paper count
- Shows ChromaDB availability and embedding coverage
- Generates actionable recommendations
- Explicit fallback tracking (no more silent failures)

### Phase 4: Configuration & Tag Search ✅

| Item | Change | Before | After |
|------|--------|--------|-------|
| `src/config/ai_settings.py` | score_threshold | 0.7 | 0.35 |
| `src/literature_core/config.py` | chroma_score_threshold | 0.7 | 0.35 |
| `src/literature_core/constants.py` | DEFAULT_MIN_SIMILARITY | 0.5 | 0.35 |
| `src/services/search_service.py` | Tag search | Exact match only | Partial matching default |

**Key Features:**
- Discovery-focused 0.35 threshold (finds more relevant papers)
- Tag search now uses case-insensitive partial matching by default
- `exact_match` parameter available when needed

---

## New MCP Tools Available

| Tool | Description |
|------|-------------|
| `hybrid_search` | Advanced search combining keyword (BM25) + semantic with RRF fusion |
| `get_search_status` | Health check showing FTS5, ChromaDB, embedding coverage, recommendations |
| `keyword_search` | Now uses FTS5 BM25 (was: SQL LIKE) |
| `semantic_search` | Now reports fallback when unavailable |
| `search_by_tag` | Now supports partial matching |

---

## Commits Made

```
810797d search: feat: Lower similarity thresholds and add partial tag matching
4153bd2 search: fix: Add explicit fallback tracking for semantic search failures
4163b29 mcp: feat: Add search diagnostics service and get_search_status tool
[earlier] mcp: feat: Add hybrid_search tool combining BM25 + semantic search
[earlier] search: feat: Add hybrid search service with Reciprocal Rank Fusion
[earlier] search: feat: Add FTS5 database initialization and migration script
[earlier] search: feat: Add SQLite FTS5 full-text search infrastructure
```

---

## Remaining Work (Optional)

### Not Started

| Task | Priority | Description |
|------|----------|-------------|
| Auto-embed on paper add | Medium | Queue embedding generation when papers added |
| Embedding backfill script | Medium | Script to generate embeddings for existing papers |
| Update README | Low | Document new search capabilities |
| Add CHANGELOG entry | Low | Document changes for users |

### Technical Debt

| Issue | Location | Notes |
|-------|----------|-------|
| Some semantic tests use real mocks | `tests/unit/services/test_search_service.py` | Fixed but could be cleaner |

---

## How to Test

### Verify FTS5 Index
```bash
cd /home/dreece23/projects/research/misc/research
python src/scripts/migrate_fts5.py --check
```

### Run All Search Tests
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_search_service.py tests/unit/services/test_hybrid_search_service.py tests/unit/services/test_search_diagnostics_service.py -v
```
Expected: 55 tests pass

### Check Search System Health
```bash
cd /home/dreece23/projects/research/misc/research
PYTHONPATH=src python -c "from services import SearchDiagnosticsService; import json; print(json.dumps(SearchDiagnosticsService.get_search_health(), indent=2, default=str))"
```

---

## Key Files Reference

### New Files Created
- `src/literature_core/fts.py` - FTS5 infrastructure
- `src/services/hybrid_search_service.py` - Hybrid search with RRF
- `src/services/search_diagnostics_service.py` - Health checks
- `src/scripts/migrate_fts5.py` - Migration CLI
- `tests/unit/services/test_fts_service.py` - FTS tests
- `tests/unit/services/test_hybrid_search_service.py` - Hybrid tests
- `tests/unit/services/test_search_diagnostics_service.py` - Diagnostics tests

### Modified Files
- `src/literature_core/database.py` - FTS5 init on startup
- `src/services/search_service.py` - Fallback tracking, tag partial match
- `src/services/__init__.py` - Export new services
- `src/mcp_server/tools/search.py` - New tools, fixed descriptions
- `src/config/ai_settings.py` - Lower thresholds
- `src/literature_core/config.py` - Lower thresholds
- `src/literature_core/constants.py` - Lower thresholds

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│         hybrid_search MCP Tool       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│       HybridSearchService            │
│  ┌─────────────┐  ┌───────────────┐ │
│  │ FTS5 Search │  │Semantic Search│ │
│  │   (BM25)    │  │  (ChromaDB)   │ │
│  └─────────────┘  └───────────────┘ │
│         │                │          │
│         └───────┬────────┘          │
│                 ▼                   │
│     Reciprocal Rank Fusion (k=60)   │
│                 │                   │
│                 ▼                   │
│         Merged Results              │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│    SearchDiagnosticsService          │
│  (Health checks & recommendations)   │
└─────────────────────────────────────┘
```

---

## Next Steps for Future Sessions

1. **If embeddings are empty**: Create backfill script to populate ChromaDB
2. **If search still returns no results**: Check `get_search_status` for diagnostics
3. **To add more search features**: Extend `HybridSearchService`
4. **To update documentation**: Add README section and CHANGELOG

---

*This document should be updated as work progresses.*
