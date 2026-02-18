# Literature Management System - Project State

## Overview
A unified research literature management system with MCP (Model Context Protocol) integration for Claude Code and Claude Desktop. Provides paper search, metadata enrichment, citation management, and PDF acquisition.

## Current Status (January 2026)

### Completed: Schema v2.1 Two-Tier Extraction Migration

**Schema Changes:**
- Added `NEEDS_CHUNKING` enrichment status (between NEEDS_PDF and NEEDS_EXTRACTION)
- Added `NEEDS_DEEP_EXTRACTION` status (for flagging papers after quick extraction)
- Separate quick/deep extraction fields:
  - Quick: `paper_type`, `topics`, `one_sentence_summary`
  - Deep: `deep_paper_type`, `deep_topics`, `deep_one_sentence_summary`
  - Verification: `verification` JSON comparing quick vs deep
- Extraction dates: `quick_extraction_date`, `deep_extraction_date`
- Model tracking: `extractor_model`, `deep_extractor_model`

**Workflow Changes:**
```
PENDING → NEEDS_PDF → NEEDS_CHUNKING → NEEDS_EXTRACTION → COMPLETE
                                                           ↓
                                          NEEDS_DEEP_EXTRACTION → COMPLETE
```

**Database State (Fresh Start):**
- All extraction data cleared for re-extraction
- Papers with PDF: 401 (status: needs_chunking)
- Papers without PDF: 95 (status: needs_pdf)
- All PaperContent, PaperChunk, ExtractionMetadata cleared

**New MCP Tool:**
- `flag_for_deep_extraction(paper_id/paper_ids)`: Set status to needs_deep_extraction

### Key Services

- `ExtractionService._store_extraction(is_quick)`: Stores to appropriate fields, sets status to COMPLETE
- `ExtractionService.extract_paper_quick()`: Quick tier using abstract only
- `ExtractionService.extract_paper_deep()`: Deep tier using PDF chunks
- `PaperService.flag_for_deep_extraction()`: Flag for deep extraction
- `PaperService.batch_flag_for_deep_extraction()`: Batch flagging

### Database Stats
- **Total papers**: ~496
- **Papers needing chunking**: 401
- **Papers needing PDF**: 95
- **Extractions**: 0 (cleared for fresh start)

## Environment
- **Conda environment**: `litai`
- **Python**: 3.11
- **GPU**: RTX 4070 8GB VRAM
- **LLM**: Qwen 2.5 7B via Ollama (local), 28K context + 3K output

## Commands
```bash
# Tests
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q

# MCP Server
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m mcp_server.server

# Linting
/home/dreece23/miniforge3/bin/mamba run -n litai python -m flake8 src/

# Database migrations
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai alembic upgrade head
```

## Current Task: Test New Extraction Workflow

**Status**: Ready to test in new Claude session

**What was completed (January 6, 2026):**
1. Schema v2.1 migration with two-tier extraction fields
2. Added `NEEDS_CHUNKING` status (between NEEDS_PDF and NEEDS_EXTRACTION)
3. Added `NEEDS_DEEP_EXTRACTION` status (for flagging after quick extraction)
4. Separate quick/deep storage fields (quick data preserved when deep runs)
5. Added `flag_for_deep_extraction` MCP tool and service methods
6. Fixed workflow transitions (chunking → NEEDS_EXTRACTION, not COMPLETE)
7. All 721 tests pass (2 pre-existing external API mock failures)

**Test plan saved**: `scripts/test_extraction_workflow.md`

**Next steps for new session:**
1. Restart MCP server (load new tools)
2. Import a test paper by DOI
3. Test quick extraction workflow
4. Test deep extraction with Ollama
5. Run batch commands for remaining papers

## Database State (Ready for Re-extraction)
- **401 papers**: status `needs_chunking` (have PDF, need text extraction)
- **95 papers**: status `needs_pdf` (waiting for PDF)
- **All extraction data cleared** for fresh start with v2.1 schema

## Remaining Tasks
1. **Test single paper workflow** (see `scripts/test_extraction_workflow.md`)
2. **Batch process PDFs** needing chunking (401 papers)
3. **Quick extraction** for all papers with abstracts
4. **Deep extraction** for high-relevance papers
5. Fix 2 pre-existing test failures (external API mocks)

## Key Files Changed (January 6, 2026)
- `src/literature_core/constants.py` - Added NEEDS_CHUNKING, NEEDS_DEEP_EXTRACTION
- `src/literature_core/models.py` - Added deep_* fields, verification to PaperContent
- `src/services/extraction_service.py` - Updated _store_extraction, process_extraction_single
- `src/services/paper_service.py` - Added flag_for_deep_extraction methods, updated store_extraction
- `src/services/paper_import_service.py` - Fixed auto-chunk status (NEEDS_EXTRACTION not COMPLETE)
- `src/mcp_server/tools/extraction.py` - Added flag_for_deep_extraction tool
- `docs/WORKFLOWS.md` - Updated with new status values and flow
- `scripts/test_extraction_workflow.md` - NEW: Test plan for workflow verification

## Alembic Migrations Created
- `6a8c7b18a684_add_needs_chunking_status.py` - NEEDS_CHUNKING status, data migration
- `fe8f5f99913b_add_deep_extraction_fields.py` - deep_* columns, verification field
- `3190e4a915cb_extraction_schema_v2.py` - quick/deep extraction dates, ProjectRelevance updates

## Commands for New Session