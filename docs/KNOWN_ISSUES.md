# Known Issues and Future Improvements

## Fixed Issues

### `import_bib_to_database` and `export_database_to_bib` routing bugs (FIXED - Dec 2024)
**Fixed by**: Tool registry pattern implementation in `src/mcp_server/server.py`

The old pattern-matching routing (`if name.startswith("import_")...`) caused tools to be
routed to the wrong module. Now all 86 tools are registered directly from their modules,
eliminating routing conflicts.

---

## Database Maintenance

### 3. Paper validation not automated
**Status**: Infrastructure exists, no automation
**Location**: External API tools exist but no batch validation

**Need**:
- ValidationService to verify papers exist in external databases
- `verified` status field on papers
- Batch validation tool

---

### 4. LLM extraction not automated
**Status**: Storage exists, no extraction service
**Location**: PaperContent model exists, store_extraction tool exists

**Need**:
- ExtractionService to run LLM extraction in background
- Integration with Ollama (Qwen 7B) or Claude API
- Queue-based processing

---

## Potential Overflow Issues

### 5. `export_papers` no pagination
**Status**: Not fixed
**Location**: `src/mcp_server/tools/import_export.py`

**Problem**: Exporting all 427 papers could exceed token limits.

**Need**: Add `limit` parameter or automatic pagination.

---

## Fixed Issues

### `get_paper_content` overflow (FIXED - Dec 2024)
Added `max_chars`, `offset`, and `include_full_text` parameters to prevent token overflow.

---

*Last updated: 2025-12-31*
