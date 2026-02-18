# Extraction System Redesign - Schema V2.1

**Status**: ✅ Schema Complete | ✅ Docs Updated | 🔜 Tests & Re-extraction
**Last Session**: 2026-01-06

---

## Session Summary: Schema V2.1 Complete

### Steps Completed

| Step | Description | Status |
|------|-------------|--------|
| 1-6 | Schema V2.0 Migration (quick/deep dates) | ✅ Complete |
| 7 | Chunking flow review + NEEDS_CHUNKING status | ✅ Complete |
| 7b | Separate quick/deep extraction fields (v2.1) | ✅ Complete |
| 8 | Documentation updates | ✅ Complete |
| 9 | Run tests and verify | 🔜 Next |
| 10 | Plan re-extraction run | 🔜 Pending |

### Key Changes This Session

**1. Added `NEEDS_CHUNKING` enrichment status:**
```
PENDING → NEEDS_PDF → NEEDS_CHUNKING → NEEDS_EXTRACTION → COMPLETE
```
- Migration: `6a8c7b18a684_add_needs_chunking_status.py`
- Updated: `EnrichmentStatus` in constants.py
- Updated: `process_extraction_single`, `queue_extraction`, PDF attachment logic

**2. Schema V2.1: Separate Quick/Deep Fields**
```
PaperContent:
  # Quick tier (from abstract - preserved)
  paper_type, topics, one_sentence_summary
  quick_extraction_date, extractor_model
  
  # Deep tier (from PDF - separate fields)
  deep_paper_type, deep_topics, deep_one_sentence_summary
  deep_extraction_date, deep_extractor_model
  
  # Deep-only extended fields
  key_findings, methodology_summary, structured_data
  
  # Verification
  verification  # JSON: {paper_type_matches, topics_overlap, ...}
```
- Migration: `fe8f5f99913b_add_deep_extraction_fields.py`
- Updated: `ExtractionService._store_extraction`
- Updated: `PaperService.store_extraction`

**3. Cleared extraction data for fresh start:**
- Backup: `literature_backup_before_fresh_start.db`
- Cleared: `paper_contents`, `paper_chunks`, `extraction_metadata`, `paper_tables`, `paper_figures`, `paper_references`
- Reset: All papers to `needs_chunking` or `needs_pdf`

**4. Documentation updated:**
- `docs/WORKFLOWS.md`: Added two-tier extraction section, updated status table
- `docs/ARCHITECTURE.md`: Updated schema section, AI pipeline details

---

## Current Database State

| Status | Count | Description |
|--------|-------|-------------|
| `needs_chunking` | 401 | Have PDF, ready for text extraction |
| `needs_pdf` | 95 | No PDF yet |
| **Total** | 496 | |

**Backups available:**
- `literature_backup_before_v2.db` - Before schema v2.0
- `literature_backup_before_fresh_start.db` - Before clearing extractions

---

## Migration Chain

```
a1f82a6d225a (initial)
       ↓
fc458fc0c8ad - Drop paper full_text column
       ↓
42754b808c18 - Update enrichment_status values
       ↓
3190e4a915cb - Extraction schema v2.0 (quick/deep dates)
       ↓
1aa6b5d4e79d - Drop legacy extraction_date column
       ↓
6a8c7b18a684 - Add needs_chunking status
       ↓
fe8f5f99913b - Add deep extraction fields (v2.1)
```

---

## Next Steps

### Step 9: Run Tests
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q
```

**Pre-existing failures to investigate:**
- `test_external_tools.py::TestLookupPaperMetadataTool::test_lookup_by_doi`
- `test_external_tools.py::TestGetCitationCountTool::test_get_citation_count_by_doi`

### Step 10: Re-extraction Plan

1. **Chunking phase** (401 papers with PDFs):
   ```python
   # Queue all papers needing chunking
   for paper_id in papers_needing_chunking:
       queue_pdf_processing(paper_id)
   
   # Process in batches
   process_pdf_queue(limit=50)
   ```

2. **Quick extraction** (all papers):
   - Run via Claude Code during normal usage
   - Or batch via MCP tool

3. **Deep extraction** (relevant papers only):
   ```python
   # Select papers based on relevance
   for paper in high_relevance_papers:
       extract_paper_deep(paper_id)
   ```

---

## Two-Tier Extraction Design

```
QUICK TIER (ALL papers when abstract available):
  Model:  Claude Code
  Input:  title + journal + abstract
  Output: paper_type, topics, one_sentence_summary
  Stored: paper_type, topics, one_sentence_summary, quick_extraction_date
  
DEEP TIER (SELECTIVE papers with PDF chunks):
  Model:  Ollama (qwen2.5:7b)
  Pass 1: Each chunk → section_type, key_points, data, techniques, claims
  Pass 2: Consolidate → Full schema + verification
  Stored: deep_paper_type, deep_topics, deep_one_sentence_summary,
          key_findings, methodology_summary, structured_data,
          deep_extraction_date, verification
```

**Key principle**: Quick extraction is NEVER overwritten by deep. Both persist for comparison.

---

## Files Modified This Session

```
src/literature_core/constants.py           # Added NEEDS_CHUNKING
src/literature_core/models.py              # PaperContent v2.1 fields
src/services/extraction_service.py         # _store_extraction, process_extraction_single
src/services/paper_service.py              # store_extraction, update
src/services/pdf_service.py                # Status → NEEDS_CHUNKING
src/services/paper_import_service.py       # _determine_enrichment_status
docs/WORKFLOWS.md                          # Two-tier extraction docs
docs/ARCHITECTURE.md                       # Schema v2.1 docs
src/alembic/versions/6a8c7b18a684_*.py     # NEEDS_CHUNKING migration
src/alembic/versions/fe8f5f99913b_*.py     # Deep extraction fields migration
```
