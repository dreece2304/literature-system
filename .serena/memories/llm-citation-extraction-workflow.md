# LLM Citation Extraction Workflow

## Overview

The deep extraction system extracts claims with citation references and links them to the paper's bibliography and library papers.

## Data Flow

```
PDF → Chunks → LLM (per-chunk) → claim_citations → Link to References → Link to Library
```

### Step 1: PDF Processing (`extract_pdf_and_store`)
- Extracts text chunks from PDF
- Parses bibliography section → `paper_references` table
- References stored with `reference_order` (0-indexed)

### Step 2: Chunk Extraction (LLM Pass 1)
For each chunk, the LLM extracts `claim_citations`:

```json
{
  "claim_citations": [
    {
      "claim": "ALD enables highly conformal coatings",
      "citation_numbers": [17, 23],
      "claim_type": "fact",
      "importance": "high"
    }
  ]
}
```

**Prompt Location**: `src/services/extraction_prompts.py` → `CHUNK_EXTRACTION_PROMPT`

**Citation Number Formats Handled**:
- Bracketed: `[1]`, `[17, 23]`, `[5-7]`
- Author-year: `(Smith 2020)` → requires manual linking

### Step 3: Post-Extraction Processing (`_process_claim_citations`)
After LLM extraction, each claim is linked:

1. **Clear old claims** for this paper
2. **For each citation number**:
   - Look up in `paper_references` by `reference_order` (0-indexed, so citation [1] → order 0)
   - If reference has `matched_paper_id` → link to library paper
   - Track match status: `matched`, `unmatched`, `reference_not_found`

### Step 4: Storage in `claim_citations` Table

| Column | Description |
|--------|-------------|
| `paper_id` | Source paper |
| `claim_text` | The claim without citation markers |
| `citation_numbers` | JSON array `[17, 23]` |
| `section` | introduction, methods, results, discussion |
| `chunk_index` | Which chunk this came from |
| `claim_type` | fact, method, comparison, limitation, background |
| `importance` | high, medium, low |
| `reference_ids` | JSON array of PaperReference IDs |
| `matched_paper_ids` | JSON array of Paper IDs (if in library) |
| `match_statuses` | JSON array of statuses per citation |

## Indexing Note

**Critical**: Citation numbers in papers are 1-indexed (e.g., [1], [2], [3]) but `reference_order` in `paper_references` is 0-indexed.

The lookup in `_process_claim_citations` handles this:
```python
ref = references.get(num - 1) if num > 0 else None
```

## Improving Extraction Quality

### Current Prompt Instructions (lines 308-325 of extraction_prompts.py)
```
claim_citations: Claims with explicit citation references [1], [17,23], (Smith 2020), etc.
  - claim: The exact claim text WITH the citation markers removed
  - citation_numbers: Array of reference numbers as integers (e.g., [17, 23])
  - claim_type: One of "fact", "method", "comparison", "limitation", "background"
  - importance: "high" (core result/claim), "medium" (supporting), "low" (background)

  SKIP:
  - Generic citations without specific claims (e.g., "See methods in ref. [4]")
  - Citations in reference lists
  - Only extract 3-8 most significant cited claims per chunk
```

### Tips for Better Results

1. **Focus on significant claims**: The prompt says 3-8 per chunk - adjust if needed
2. **Handle author-year citations**: Add explicit instruction for formats like (Smith 2020)
3. **Verify with full text**: Use `get_paper_content` with verification to check claims

## MCP Tools for Citation Analysis

| Tool | Purpose |
|------|---------|
| `get_citation_chain` | Trace claim → reference → that paper's claims |
| `get_local_citations` | View incoming/outgoing citation links |
| `manage_references` | View/match/import unmatched references |

## Testing Citation Extraction

```python
# 1. Run deep extraction on a paper with citations
from services.extraction_service import ExtractionService
result = ExtractionService.extract(paper_id=123, tier="deep")

# 2. Check claim citations
from literature_core import ClaimCitation, get_session
with get_session() as s:
    claims = s.query(ClaimCitation).filter(ClaimCitation.paper_id == 123).all()
    for c in claims:
        print(f"{c.claim_text[:50]}... -> refs {c.citation_numbers}")
```

## Known Limitations

1. **Reference parsing accuracy**: Bibliography parsing depends on PDF quality
2. **Citation number formats**: Complex formats (1a, 1-3) may not parse correctly
3. **Author-year matching**: Not automatically linked to reference_order
4. **Importance classification**: LLM subjective judgment

## Future Improvements

1. Add LLM-based reference parsing for better bibliography extraction
2. Handle author-year citation formats with text matching
3. Auto-match unmatched references using semantic search
4. Add verification score for claim accuracy
