# MCP Tools Assessment - Living Document

**Last Updated**: 2026-01-01 (Session 5)
**Database**: 441 papers, 393 with PDFs (89%)
**Status**: OCR support added, Discovery tools audited

---

## Critical Issues

### 1. Database Corruption (FIXED)
- **Problem**: SQLite database had corruption ("disk image is malformed")
- **Fix Applied**: Recovered using `.recover` command
- **Status**: RESOLVED

### 2. FTS5 Multi-Word Query Issue (FIXED ✓)
- **Problem**: FTS5 uses implicit AND - multi-word queries return 0 results
- **Fix Applied**: Modified `search_fts()` to use OR logic for multi-word queries
- **File Changed**: `src/literature_core/fts.py`
- **Status**: RESOLVED - multi-word queries now work correctly
- **Test Results**:
  ```
  keyword_search("EUV lithography photoresist") → 5 results ✓
  smart_search("EUV lithogrpahy") → 5 results (typo corrected!) ✓
  ```

### 3. DOI Resolution Bug (CONFIRMED - PENDING FIX)
- **Problem**: CrossRef DOI lookups return WRONG papers
- **Root Cause**: CrossRef API matching "DOI" as author name in query
- **Affected Tools**: `lookup_paper_metadata`, `get_citation_count`, `enrich_paper`
- **Workaround**: Use title+author lookup via OpenAlex instead of DOI
- **Status**: Will fix when reviewing External/Metadata tools section

---

## Search Tools - Unified Search System

### Session 4: Search Tool Consolidation

Consolidated 7 search tools into 1 unified `search` tool with backwards compatibility:

**Before (7 tools)**:
- `smart_search`, `hybrid_search`, `keyword_search`, `semantic_search`
- `search_by_author`, `search_by_tag`, `get_search_status`
- `search_papers` (already deprecated)

**After (4 active + 4 backwards-compatible)**:
- `search` (unified with `mode` parameter) - **RECOMMENDED**
- `search_by_author`, `search_by_tag`, `get_search_status`
- Old tools redirect to `search` with appropriate mode

### Unified Search API

```python
# Smart mode (default) - typo correction, acronym expansion, hybrid search
search("ALD thin films")
search("lithogrpahy", mode="smart")  # typo corrected

# Keyword mode - FTS5 exact matching
search("photoresist", mode="keyword")

# Semantic mode - embedding similarity
search("how do thin films grow", mode="semantic")

# Hybrid mode - balanced keyword + semantic
search("membrane coating", mode="hybrid", alpha=0.65)
```

### Test Results (Session 4)

| Test | Mode | Time | Results | Notes |
|------|------|------|---------|-------|
| ALD thin films | smart | 9.730s* | 3 | *First load, acronym expanded |
| photoresist | keyword | 0.008s | 3 | FTS5 working |
| how thin films grow | semantic | 0.043s | 3 | Chunk search |
| membrane coating | hybrid | 0.097s | 3 | RRF fusion |
| lithogrpahy EUV | smart | <1s | 3 | Typo + acronym |

*9.73s on first call due to model loading; subsequent calls <1s

### Files Created/Modified (Session 3-4)

- `src/services/unified_search_service.py` (NEW - Session 4)
- `src/services/smart_search_service.py` (NEW - Session 3)
- `src/literature_core/fts.py` (OR logic added)
- `src/services/search_service.py` (FTS5 integration)
- `src/mcp_server/tools/search.py` (unified search + deprecations)
- `src/mcp_server/server.py` (prompt updated)

### Current Search Tools

| Tool | Status | Use Case |
|------|--------|----------|
| `search` | **ACTIVE - RECOMMENDED** | Unified search with mode parameter |
| `search_by_author` | ACTIVE | Author lookup |
| `search_by_tag` | ACTIVE | Tag-based filtering |
| `get_search_status` | ACTIVE | System diagnostics |
| `smart_search` | DEPRECATED | Redirects to `search(mode="smart")` |
| `hybrid_search` | DEPRECATED | Redirects to `search(mode="hybrid")` |
| `keyword_search` | DEPRECATED | Redirects to `search(mode="keyword")` |
| `semantic_search` | DEPRECATED | Redirects to `search(mode="semantic")` |
| `search_papers` | DEPRECATED | Use `search` instead |

### Supported Acronyms (25+)
ALD, CVD, PVD, EUV, DUV, MOCVD, PECVD, XPS, XRD, SEM, TEM, AFM, FTIR,
ML, DL, DFT, MD, CMOS, FET, LED, OLED, PV, HTE, DOE, etc.

---

## Tool-by-Tool Assessment

### Paper Management Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `list_papers` | EXCELLENT | Yes | All filters work |
| `get_paper` | EXCELLENT | Yes | Complete metadata |
| `update_paper` | EXCELLENT | Yes | Tested with rating/status |
| `add_paper` | EXCELLENT | Yes | Added 14 papers this session |
| `batch_update_papers` | NOT TESTED | No | Should work |
| `batch_delete_papers` | NOT TESTED | No | Should work |

---

### Search Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `search` | **UNIFIED - RECOMMENDED** | Yes | All modes: smart/keyword/semantic/hybrid |
| `search_by_author` | EXCELLENT | Yes | Partial matching works |
| `search_by_tag` | EXCELLENT | Yes | Exact matching works |
| `get_search_status` | EXCELLENT | Yes | Comprehensive diagnostics |
| `smart_search` | DEPRECATED | Yes | Redirects to search(mode=smart) |
| `keyword_search` | DEPRECATED | Yes | Redirects to search(mode=keyword) |
| `semantic_search` | DEPRECATED | Yes | Redirects to search(mode=semantic) |
| `hybrid_search` | DEPRECATED | Yes | Redirects to search(mode=hybrid) |
| `search_papers` | DEPRECATED | - | Use search instead |

**Search Infrastructure Status**:
- FTS5: ENABLED (441 papers indexed)
- Vector store: 432 papers, 51,069 chunks
- Embeddings: 98% coverage (432/441 papers)
- Model: sentence-transformers/all-MiniLM-L6-v2

---

### Collection Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `list_collections` | EXCELLENT | Yes | Returns with paper counts |
| `get_collection` | EXCELLENT | Yes | Returns paper IDs |
| `create_collection` | EXCELLENT | Yes | Created "EUV Lithography" |
| `update_collection` | NOT TESTED | No | Should work |
| `delete_collection` | NOT TESTED | No | Should work |
| `add_papers_to_collection` | EXCELLENT | Yes | Added 3 papers |
| `remove_papers_from_collection` | NOT TESTED | No | Should work |
| `get_collection_children` | NOT TESTED | No | Hierarchical |

**Current Collections**:
1. "ALD for Membrane Applications" - 5 papers
2. "Electrocatalysis Review" - 0 papers
3. "Test Collection" - 0 papers
4. "EUV Lithography" - 3 papers

---

### PDF Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `get_pdf_status` | EXCELLENT | Yes | 393/441 have PDFs (89%) |
| `find_duplicates` | EXCELLENT | Yes | Found 1 title duplicate |
| `acquire_paper_pdf` | GOOD | Yes | Works with VPN/OpenURL |
| `queue_pdf_download` | GOOD | Yes | Browser automation queue |
| `queue_batch_pdf_download` | GOOD | Yes | Batch queuing works |
| `get_download_queue_status` | GOOD | Yes | Shows pending/completed |
| `process_downloaded_pdfs` | FIXED | Yes | Cross-device copy fixed |

**Session 5 Improvements**:
- Added OCR support via Tesseract for image-based PDFs
- Fixed cross-device copy (WSL↔Windows) using shutil.copy2
- Fixed status.json path handling for Windows paths
- Re-extracted text from 21 PDFs (20 successful via OCR)

---

### Notes Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `list_notes` | EXCELLENT | Yes | With pagination |
| `get_note` | NOT TESTED | No | |
| `create_note` | EXCELLENT | Yes | Created on paper 78 |
| `update_note` | NOT TESTED | No | |
| `delete_note` | NOT TESTED | No | |
| `get_paper_notes` | NOT TESTED | No | |
| `delete_paper_notes` | NOT TESTED | No | |

---

### Citation/Bibliography Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `generate_bibtex` | EXCELLENT | Yes | Proper formatting |
| `suggest_citation_key` | EXCELLENT | Yes | authorYEARword format |
| `format_bibliography` | EXCELLENT | Yes | APA tested |
| `validate_citations` | EXCELLENT | Yes | Identifies missing fields |
| `get_paper_content` | EXCELLENT | Yes | Full text extraction |

---

### Discovery Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `find_similar_papers` | EXCELLENT | Yes | Scores 0.73-0.78 |
| `find_papers_like_text` | EXCELLENT | Yes | Scores 0.63-0.70, great for research questions |
| `suggest_citations_for_text` | EXCELLENT | Yes | Returns matching chunks + scores |
| `get_reading_queue` | GOOD | Yes | Returns unread papers by rating |
| `suggest_paper_tags` | FIXED | Yes | Fixed dict/string tag mismatch bug |
| `get_embedding_status` | EXCELLENT | Yes | 100% paper, 94.6% chunk coverage |
| `get_paper_citations` | GOOD | Yes | Semantic Scholar works |
| `get_paper_references` | EXCELLENT | Yes | Returns full metadata from Semantic Scholar |
| `find_common_references` | GOOD | Yes | Works when references available |
| `build_citation_graph` | GOOD | Yes | 5 nodes/2 edges found |

**Session 5 Improvements**:
- Fixed `suggest_paper_tags` bug (PaperService returns tags as dicts, not strings)
- Tested `find_papers_like_text` - works excellently for research text matching
- Confirmed `get_paper_references` now works (previous "API issue" was transient)

---

### External/Metadata Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `lookup_paper_metadata` | FIXED ✓ | Yes | Now uses direct DOI lookup |
| `search_external_papers` | EXCELLENT | Yes | Multi-source works |
| `find_open_access_pdf` | FIXED ✓ | Yes | AttributeError fixed |
| `enrich_paper` | FIXED ✓ | Yes | Returns abstract correctly |
| `get_citation_count` | FIXED ✓ | Yes | Returns 406 citations for ALD paper |

**Session 5 Fixes**:
- Fixed DOI lookup: Was using text search `_search_crossref_multi(f"doi:{doi}")` instead of `lookup_by_doi(doi)`
- Fixed `is_open_access` AttributeError in `find_open_access_pdf`
- Fixed `get_citation_count` to use Semantic Scholar's `DOI:{doi}` endpoint

---

### Import/Export Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `export_papers` | EXCELLENT | Yes | BibTeX/JSON/CSV work |
| `import_bibtex` | EXCELLENT | Yes | Parses BibTeX string, imports papers |
| `import_from_external` | EXCELLENT | Yes | DOI lookup via CrossRef/OpenAlex |
| `export_collection` | EXCELLENT | Yes | With abstracts |
| `parse_bib_file` | EXCELLENT | Yes | 5 entries parsed |
| `import_bib_to_database` | EXCELLENT | Yes | Reads .bib file and imports |
| `export_database_to_bib` | EXCELLENT | Yes | Exports to file or returns string |

**Session 5 Tests**:
- `import_bibtex`: Imported 1 test paper from BibTeX string
- `import_from_external`: Imported Nature paper (DOI: 10.1038/nature12373) successfully
- `import_bib_to_database`: Imported 2 papers from .bib file
- `export_database_to_bib`: Exports with paper_ids filter, file output works

---

### BibTeX/LaTeX Integration Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `link_bib_to_database` | EXCELLENT | Yes | 100% DOI match |
| `find_duplicate_bib_entries` | EXCELLENT | Yes | 0 duplicates |
| `find_incomplete_bib_entries` | EXCELLENT | Yes | All complete |
| `scan_tex_citations` | EXCELLENT | Yes | Found 6 citations, 4 unique keys |
| `citation_health_check` | EXCELLENT | Yes | Reports orphans, missing, duplicates |
| `find_orphan_citations` | EXCELLENT | Yes | Found 1 orphan entry |
| `find_missing_citations` | EXCELLENT | Yes | Found 1 missing citation |
| `sync_bib_from_database` | EXCELLENT | Yes | DOI matching works (dry_run tested) |
| `get_citation_locations` | EXCELLENT | Yes | Returns line numbers and context |

**Session 5 Tests**:
- Created test .tex and .bib files with intentional issues
- `scan_tex_citations`: Found 6 citations, 4 unique keys correctly
- `find_orphan_citations`: Found "orphan2021unused" (not cited in .tex)
- `find_missing_citations`: Found "missing2024paper" (cited but not in .bib)
- `citation_health_check`: Full report with status="issues_found"
- `get_citation_locations`: Returns 3 locations for "li2018static" with line/context

---

### Project Configuration Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `get_project_config` | GOOD | Yes | Shows detected files |
| `set_project_config` | NOT TESTED | No | |

---

### Zotero Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `check_zotero_connection` | GOOD | Yes | API configured |
| `get_zotero_sync_status` | GOOD | Yes | 425/441 linked |
| `sync_from_zotero` | NOT TESTED | No | Needs Zotero running |
| `sync_to_zotero` | NOT TESTED | No | |
| `push_paper_to_zotero` | NOT TESTED | No | |
| `push_pdf_to_zotero` | NOT TESTED | No | |

---

### Embedding/AI Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `get_embedding_status` | EXCELLENT | Yes | 98% coverage |
| `process_embedding_queue` | TESTED | Yes | 7 papers processed |
| `embed_paper` | NOT TESTED | No | |
| `get_extraction_status` | EXCELLENT | Yes | 0% extraction |
| `get_llm_status` | EXCELLENT | Yes | Ollama + Claude |
| `extract_paper` | NOT TESTED | No | |
| `extract_papers_batch` | NOT TESTED | No | |
| `delete_extraction` | NOT TESTED | No | |
| `get_extraction_queue` | NOT TESTED | No | |
| `store_extraction` | NOT TESTED | No | |

**Embedding Issues Found**:
- Papers 120, 342: Metadata NoneType error (missing year?)
- Paper 381: Batch too large (5573 chunks > 5461 max)

---

### Validation Tools

| Tool | Status | Tested | Notes |
|------|--------|--------|-------|
| `get_validation_status` | EXCELLENT | Yes | 445 papers, 430 with DOIs |
| `get_validation_queue` | EXCELLENT | Yes | Returns papers prioritized by DOI |
| `validate_paper` | EXCELLENT | Yes | CrossRef verification, confidence=1.0 |
| `validate_papers_batch` | EXCELLENT | Yes | Batch verified 3 papers |
| `reset_validation` | EXCELLENT | Yes | Reset 4→0 validated papers |

**Session 5 Tests**:
- `get_validation_status`: 445 papers, 430 with DOIs, 0% validated
- `get_validation_queue`: Returns 5 papers with DOIs first
- `validate_paper`: Paper 1 verified via CrossRef (confidence=1.0)
- `validate_papers_batch`: Papers 2,3,4 verified (papers_verified=3)
- `reset_validation`: Reset 4 validated papers back to unvalidated

---

## Summary Statistics

| Category | Total | Tested | Working | Issues |
|----------|-------|--------|---------|--------|
| Paper Management | 6 | 4 | 4 | 0 |
| Search | 9 | 9 | 4 active | 5 deprecated (backwards-compatible) |
| Collections | 7 | 4 | 4 | 0 |
| PDF | 6 | 2 | 2 | 0 |
| Notes | 7 | 2 | 2 | 0 |
| Citation/Bib | 5 | 5 | 5 | 0 |
| Discovery | 10 | 10 | 10 | 0 |
| External/Metadata | 5 | 5 | 5 | 0 (DOI bugs FIXED) |
| Import/Export | 7 | 7 | 7 | 0 |
| BibTeX/LaTeX | 9 | 9 | 9 | 0 |
| Project Config | 2 | 1 | 1 | 0 |
| Zotero | 6 | 2 | 2 | 0 |
| Embedding/AI | 10 | 4 | 3 | 1 (embedding errors) |
| Validation | 5 | 5 | 5 | 0 |

**Overall**: 93 tools, 63 tested, 58 working (5 search deprecated but working)

**Session 4 Improvements**:
- ✓ Unified `search` tool with mode parameter
- ✓ Deprecated smart_search, hybrid_search, keyword_search, semantic_search
- ✓ Backwards compatibility maintained (old tools redirect)
- ✓ Prompt templates updated to use new search API

**Session 3 Improvements**:
- ✓ FTS5 multi-word search FIXED (OR logic)
- ✓ Smart search added (typos, acronyms, hybrid)
- ✓ search_papers DEPRECATED
- ✓ NLTK + pyspellchecker installed

---

## Improvement Priorities

### High Priority
1. ~~**Fix `keyword_search` multi-word**~~ - ✓ DONE (OR logic added)
2. ~~**Consolidate search tools**~~ - ✓ DONE (unified search tool)
3. **Fix DOI resolution bug** - CrossRef returning wrong papers (PENDING)

### Medium Priority
4. Fix embedding errors (papers 120, 342, 381)
5. Run extraction batch - 422 papers need AI extraction
6. Fix `get_paper_references` API (returns 0)

### Low Priority
7. Test remaining untested tools (~40)
8. Add .tex files to test LaTeX integration
9. Start Zotero to test sync features

---

## Session Log

### Session 4 - 2026-01-01

#### Search Tool Consolidation

Consolidated 7 search tools into 1 unified `search` tool:

**Files Modified**:
- `src/services/unified_search_service.py` (NEW) - Central search dispatcher
- `src/mcp_server/tools/search.py` (REWRITTEN) - Unified tool + deprecations
- `src/mcp_server/server.py` - Updated prompt to use new API

**New Unified Search Tool**:
```python
search(query, mode="smart")  # Default - typos, acronyms, hybrid
search(query, mode="keyword") # FTS5 only
search(query, mode="semantic") # Embeddings only
search(query, mode="hybrid")  # Balanced with alpha
```

**Backwards Compatibility**:
Old tools (`smart_search`, `hybrid_search`, `keyword_search`, `semantic_search`)
still work but log deprecation and redirect to unified `search` tool.

**Test Results**:
All 5 test scenarios passed:
- Smart mode: acronym expansion working
- Keyword mode: 0.008s FTS5 search
- Semantic mode: 0.043s chunk search
- Hybrid mode: RRF fusion working
- Typo correction: "lithogrpahy" → "lithography"

---

### Session 3 - 2026-01-02

#### Smart Search Implementation
- **Created**: `src/services/smart_search_service.py`
- **Modified**: `src/literature_core/fts.py` (OR logic for multi-word)
- **Modified**: `src/services/search_service.py` (FTS5 integration)
- **Modified**: `src/mcp_server/tools/search.py` (smart_search tool)
- **Modified**: `src/mcp_server/tools/papers.py` (deprecated search_papers)

#### Features Added
1. **Spell Correction** - Uses pyspellchecker to fix typos
2. **Acronym Expansion** - 25+ scientific acronyms (ALD, EUV, XPS, etc.)
3. **FTS5 OR Logic** - Multi-word queries now use OR for better recall
4. **FTS5 Phrase Escaping** - Handles hyphens in "x-ray" correctly
5. **Synonym Expansion** - Optional WordNet + scientific domain synonyms

#### Packages Installed
```bash
pip install nltk pyspellchecker
nltk.download('wordnet')
nltk.download('omw-1.4')
```

#### Issues Fixed
- FTS5 multi-word queries returning 0 results ✓
- search_papers deprecated (was redundant) ✓

---

### Session 2 - 2026-01-02

#### Papers Added (14 new)
| ID | Title | Authors | Year | Abstract |
|----|-------|---------|------|----------|
| 429 | X-Rays and Extreme Ultraviolet Radiation | Attwood, Sakdinawat | 2016 | Yes |
| 430 | Metal containing resists for EUV | De Simone | 2016 | No |
| 431 | Chemical reactions MALD EUV | Le et al. | 2022 | Yes |
| 432 | Line-edge roughness EUV | Brunner et al. | 2017 | Yes |
| 433 | Combinatorial HT Screening | Potyrailo et al. | 2011 | Yes |
| 434 | Combinatorial thin-film materials | Ludwig | 2019 | No |
| 435 | Negative photoresists optical | Shaw et al. | 1997 | Yes |
| 436 | Novel trends HT screening | Mayr, Bojanic | 2009 | No |
| 437 | HT methodologies materials | Green et al. | 2013 | Yes |
| 438 | Hybrid perovskites photo | Wei et al. | 2020 | No |
| 439 | Evolution photolithography | Wu et al. | 2020 | No |
| 440 | Cramming components (Moore's Law) | Moore | 1965 | Yes |
| 441 | Chips down Moore's law | Waldrop | 2016 | No |
| 442 | Photoelectron Spectroscopy | Hüfner | 2003 | No |

#### Fixes Applied
- FTS5 migration run: `python src/scripts/migrate_fts5.py`
- FTS5 now healthy: 441 papers indexed
- Embeddings generated for 7 papers via `process_embedding_queue`
- Write operations confirmed working

#### Key Findings
- FTS5 uses implicit AND (multi-word queries fail)
- `hybrid_search` is the best search tool (semantic fallback)
- DOI lookup bug: CrossRef matches "DOI" as author name
- OpenAlex title+author lookup works correctly
- Research confirms "less is more" for MCP tool design

#### Commands Reference
```bash
# FTS5 migration
cd /home/dreece23/projects/research/misc/research && \
  mamba run -n litai python src/scripts/migrate_fts5.py

# Check FTS5 status
python src/scripts/migrate_fts5.py --check

# Rebuild FTS5 index
python src/scripts/migrate_fts5.py --rebuild --optimize
```

---

### Session 1 - 2026-01-01 (Previous)

- Database corruption fixed with `.recover`
- Initial tool testing (48 tools tested)
- Search status tools confirmed working
- Collection "EUV Lithography" created
- Note created on paper 78

---

## Next Steps

1. ~~**Implement keyword_search fix**~~ - ✓ DONE (OR logic added)
2. ~~**Consolidate search tools**~~ - ✓ DONE (unified search tool)
3. **Continue tool review**: Sections 4-14 remaining (PDF, Notes, Discovery, etc.)
4. **Fix DOI resolution**: Debug CrossRef API query construction
5. **Run batch operations**: Validation, extraction when ready
6. **Test remaining untested tools**: ~40 tools still need testing
