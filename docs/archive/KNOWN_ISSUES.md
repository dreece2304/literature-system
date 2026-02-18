# Known Issues and Future Improvements

## Fixed Issues

### `import_bib_to_database` and `export_database_to_bib` routing bugs (FIXED - Dec 2024)
**Fixed by**: Tool registry pattern implementation in `src/mcp_server/server.py`

The old pattern-matching routing (`if name.startswith("import_")...`) caused tools to be
routed to the wrong module. Now all 86 tools are registered directly from their modules,
eliminating routing conflicts.

---

## Database Maintenance

### Paper validation (IMPLEMENTED - Dec 2024)
**Status**: Implemented
**Location**: `src/services/validation_service.py`, `src/mcp_server/tools/validation.py`

Features:
- ValidationService with batch and single-paper validation
- Paper model now has validation fields (status, source, date, confidence)
- 5 MCP tools: get_validation_status, get_validation_queue, validate_paper,
  validate_papers_batch, reset_validation

---

### LLM extraction (IMPLEMENTED - Dec 2024)
**Status**: Implemented
**Location**: `src/services/extraction_service.py`, `src/mcp_server/tools/extraction.py`

Features:
- ExtractionService with Ollama (local) and Claude API backends
- Queue-based processing with rate limiting
- 5 MCP tools: get_extraction_status, get_llm_status, extract_paper,
  extract_papers_batch, delete_extraction
- Automatic JSON parsing with code block handling

---

### `export_papers` pagination (FIXED - Dec 2024)
**Status**: Fixed
**Location**: `src/mcp_server/tools/import_export.py`, `src/services/import_export_service.py`

Added `limit` (default: 50, max: 500) and `offset` parameters to prevent token overflow
when exporting large paper sets. Results are ordered by paper ID for consistent pagination.

---

### `get_paper_content` overflow (FIXED - Dec 2024)
Added `max_chars`, `offset`, and `include_full_text` parameters to prevent token overflow.

---

*Last updated: 2025-12-31*
