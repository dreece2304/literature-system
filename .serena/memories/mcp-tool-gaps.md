# MCP Tool Gaps and Improvements

## 1. Link PDF to Existing Paper

**Status**: FIXED (2026-01-06)  
**Priority**: Medium  
**Discovered**: 2026-01-06

### Problem
No MCP tool to attach a local PDF file to an already-imported paper.

### Current workarounds
1. Direct Python: `paper.file_path = "/path/to/file.pdf"` + commit
2. Re-import with `import_paper_wizard(doi=..., pdf_path=...)` (may create duplicate)

### Recommended fix
**Option A**: Add `file_path` parameter to `update_paper` tool in `src/mcp_server/tools/papers.py`

```python
# In inputSchema properties:
"file_path": {
    "type": "string",
    "description": "Local path to PDF file to attach"
}
```

Then in `_update_paper()` handler, call PDFService to:
- Validate file exists
- Compute file_hash
- Extract word_count
- Update paper record

**Option B**: New dedicated `link_pdf` tool
```
link_pdf(paper_id: int, file_path: str) -> success/error
```

### Files to modify
- `src/mcp_server/tools/papers.py` - add parameter or new tool
- `src/services/pdf_service.py` - may need `link_local_pdf()` method

---

## 2. PDF Chunking Fails Silently After Quick Extraction

**Status**: FIXED (2026-01-06)  
**Priority**: High  
**Discovered**: 2026-01-06

### Problem
After running quick extraction (which creates `ExtractionMetadata`), PDF chunking returns 0 chunks because `extract_pdf_and_store()` returns early when metadata exists.

### Reproduction
1. Import paper: `import_paper_wizard(doi=...)`
2. Run quick extraction: `store_extraction(paper_id=...)` or `extract_paper_quick()`
3. Link PDF manually
4. Run `queue_pdf_processing()` + `process_pdf_queue()`
5. Result: `chunk_count: 0` (silent failure)

### Root cause
In `ExtractionService.extract_pdf_and_store()` (line ~1925):
```python
existing = session.query(ExtractionMetadata).filter(...)
if existing and not force:
    return PDFExtractionResult(...)  # Returns existing (empty) chunk_count
```

Quick extraction creates `ExtractionMetadata` with `chunk_count=0`, so subsequent PDF processing returns early.

### Workaround
Call with `force=True`:
```python
ExtractionService.extract_pdf_and_store(paper_id, force=True)
```

### Recommended fix
**Option A**: `process_pdf_queue` should pass `force=True` when `chunk_count=0`

**Option B**: Quick extraction shouldn't create ExtractionMetadata (use separate table for LLM extractions vs PDF metadata)

**Option C**: Add `force` parameter to `queue_pdf_processing` MCP tool

### Files to modify
- `src/services/extraction_service.py` - fix early return logic
- `src/mcp_server/tools/extraction.py` - add force parameter

---

## 3. No MCP Tool Exposes extract_pdf_and_store

**Status**: FIXED (2026-01-06) - Added `force` param to `process_pdf_queue`  
**Priority**: Medium  
**Discovered**: 2026-01-06

### Problem
`ExtractionService.extract_pdf_and_store()` is not exposed via any MCP tool. Must use Python directly.

### Current workaround
```python
from services.extraction_service import ExtractionService
ExtractionService.extract_pdf_and_store(paper_id, force=True)
```

### Recommended fix
Add to `queue_pdf_processing` or create dedicated tool:
```
extract_pdf_chunks(paper_id: int, force: bool = False)
```

---

## 4. PaperContent Cascade Delete Missing

**Status**: FIXED (2026-01-06)

### Problem
Deleting a paper failed with `NOT NULL constraint failed: paper_contents.paper_id` because `PaperContent` relationship lacked cascade configuration.

### Fix
Added `cascade='all, delete-orphan'` to `PaperContent.paper` relationship in `src/literature_core/models.py:280`.

---

## Complete Workflow (with workarounds)

For importing a paper with a local PDF and running deep extraction:

```bash
# 1. Import paper
import_paper_wizard(doi="10.xxx/xxx")

# 2. Rename PDF to include DOI
mv "paper.pdf" "data/pdfs/10.xxx_xxx.pdf"

# 3. Link PDF (Python workaround)
paper.file_path = "/path/to/10.xxx_xxx.pdf"
session.commit()

# 4. Extract PDF chunks (Python workaround with force=True)
ExtractionService.extract_pdf_and_store(paper_id, force=True)

# 5. Run deep extraction
extract_paper_deep(paper_id=xxx, backend="ollama")
```
