# Claude Extraction Session State

> **Purpose**: Source of truth for resuming deep extraction sessions.
> **Last Updated**: January 4, 2026 - End of Day

## Current Progress

| Metric | Value |
|--------|-------|
| Papers with chunks (ready for extraction) | 396 |
| Papers extracted | 338 |
| Papers remaining | 153 |
| Extraction coverage | 85.4% |

## Session Status: PAUSED

15 parallel Claude instances ran today. Many used abstract-only extraction instead of reading full text chunks. Need audit.

## Tomorrow's Tasks

### 1. Audit Extraction Quality
Many of the 338 extractions may be shallow (abstract-only when full text exists).
```sql
-- Find papers with full text but shallow extraction
SELECT p.id, p.title,
       (SELECT COUNT(*) FROM paper_chunks WHERE paper_id = p.id) as chunk_count,
       pc.one_sentence_summary
FROM papers p
JOIN paper_contents pc ON p.id = pc.paper_id
JOIN paper_chunks pch ON p.id = pch.paper_id
WHERE length(COALESCE(pc.key_findings, '[]')) < 100
GROUP BY p.id
ORDER BY chunk_count DESC
LIMIT 50;
```

### 2. Re-extract Low Quality Papers
Delete and re-run extraction for papers that only used abstract.

### 3. Extract Remaining 153 Papers
Use corrected workflow or Ollama multi-pass script.

### 4. Generate 3 Missing Embeddings
```bash
# MCP tool: process_embedding_queue(limit=3)
```

## Ollama Multi-Pass Script
New script for overnight batch processing:
```bash
cd /home/dreece23/projects/research/misc/research
/home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.multipass_extraction --batch 50
```

Features:
- Reads papers in 20K char chunks (like Claude workflow)
- Saves notes after each chunk (crash protection)
- Consolidates into final extraction
- Can resume with `--continue` flag

### Completed Extractions
| Paper ID | Title | Type | Status |
|----------|-------|------|--------|
| 2 | TiO2 ALD on polypropylene for underwater superoleophobicity | research_article | Done |
| 4 | Review on ALD surface engineering of synthetic nanopores | review | Done |
| 5 | ZIF-8 membrane VPLT for gas separation tuning | research_article | Done |
| 6 | LIPS method for ZIF membranes (Science) | research_article | Done |
| 7 | VPI review - Leng & Losego (Materials Horizons) | review | Done |
| 8 | Li battery dendrite suppression - Fu et al. (Nature Materials) | research_article | Done |

### Next Paper to Extract
Paper 9

---

## Extraction Workflow

### CRITICAL: How to Check for Full Text
```
# DO NOT trust prepare_extraction(tier='quick') - it shows full_text=null even when full text exists!
# ALWAYS call get_paper_content FIRST to check actual content:

get_paper_content(paper_id=X, max_chars=500)
# Look at response._truncation.total_chars
# If total_chars > 1000 → full text EXISTS, use multi-pass
# If total_chars < 1000 or missing → abstract-only
```

### For Papers WITH Full Text (total_chars > 1000) - Multi-Pass Required
```
1. get_paper_content(paper_id, offset=0, max_chars=20000)      # Chunk 1
2. SAVE NOTES IMMEDIATELY after each chunk:
   create_note(paper_id=X, content="CHUNK 1: [findings]", note_type="comment")
3. get_paper_content(paper_id, offset=20000, max_chars=20000)  # Chunk 2
4. create_note(paper_id=X, content="CHUNK 2: [findings]", note_type="comment")
5. Continue until remaining_chars=0, saving notes after EACH chunk
6. Before final extraction, retrieve all notes:
   get_paper_notes(paper_id=X)
7. Consolidate findings from notes
8. store_full_extraction(paper_id, ...)
9. Clean up temp notes:
   delete_paper_notes(paper_id=X, note_type="comment")
```

### Why Save Notes After Each Chunk?
If conversation compacts mid-extraction, your earlier chunk notes are LOST.
Saving to database protects against this - you can recover and continue.

### For Abstract-Only Papers (total_chars < 1000)
```
1. prepare_extraction(paper_id, tier='quick')
2. Extract from abstract only
3. store_full_extraction(paper_id, ...)
```

### WARNING: Common Mistakes
- DO NOT use prepare_extraction(tier='deep') for long papers - it TRUNCATES
- DO NOT trust full_text=null from prepare_extraction - always check get_paper_content
- DO NOT skip chunks - read ALL until remaining_chars=0
- DO NOT skip papers based on relevance - extract ALL papers fully
- DO NOT make judgment calls about what to extract - follow the workflow exactly
- DO NOT abbreviate extractions for "less relevant" papers - every paper gets full treatment

### Required Fields for store_full_extraction
- `paper_id` (required)
- `paper_type`: research_article, review, letter, conference, etc.
- `topics`: List of 5-7 themes
- `one_sentence_summary`: WHAT + HOW + RESULT
- `key_findings`: List with specific numbers
- `methodology_summary`: Methods description

### Optional Fields (extract when available)
- `quantitative_results`: [{metric, value, unit, conditions}]
- `citable_claims`: Specific quotable assertions
- `techniques_used`: [{technique, purpose, specifics}]
- `experimental_conditions`: {materials, temperature_range, pressure, key_parameters}
- `research_context`: {problem_addressed, novelty, limitations, significance}
- `future_directions`: Suggested follow-up

---

## MCP Tools Reference

### Getting Paper Content
```python
# Step 1: Check paper metadata and length
prepare_extraction(paper_id=X, tier='quick')
# Returns: original_chars count, abstract, review_detection

# Step 2a: For SHORT papers (<20K chars) - single call
prepare_extraction(paper_id=X, tier='deep', max_chars=50000)
# Returns full_text in one response

# Step 2b: For LONG papers (>20K chars) - use get_paper_content with offset
get_paper_content(paper_id=X, offset=0, max_chars=20000)      # Chunk 1
get_paper_content(paper_id=X, offset=20000, max_chars=20000)  # Chunk 2
get_paper_content(paper_id=X, offset=40000, max_chars=20000)  # Chunk 3
# Continue until remaining_chars=0
```

### IMPORTANT: prepare_extraction vs get_paper_content
- `prepare_extraction`: Has `max_chars` but NO `offset` - truncates long papers
- `get_paper_content`: Has BOTH `offset` and `max_chars` - use for multi-pass

### Storing Extraction
```python
store_full_extraction(
    paper_id=X,
    paper_type="research_article",
    topics=["topic1", "topic2"],
    one_sentence_summary="...",
    key_findings=["finding1", "finding2"],
    methodology_summary="...",
    quantitative_results=[{"metric": "...", "value": "...", "unit": "...", "conditions": "..."}],
    # ... other optional fields
)
```

### Finding Papers to Extract
```python
# Get papers needing extraction
get_extraction_queue(limit=20)

# Check specific paper
get_paper(paper_id=X)
get_paper_content(paper_id=X, include_full_text=False)  # Check if has content
```

---

## Project Relevance Scoring

Papers are scored for relevance to active projects:

### Thesis Project
- **Topics**: MLD, ALD, thin films, EUV lithography, tincones, alucones, zincones
- **Focus**: High-throughput screening of hybrid organic-inorganic thin films

### Paper 2 Project
- **Topics**: EUV photoresist, alucones, zincones, resist performance
- **Focus**: Performance evaluation of alucone/zincone films as EUV resist candidates

### Relevance Levels
- **high**: Directly discusses core topics
- **medium**: Related techniques or chemistry
- **low**: Tangentially related
- **none**: Not relevant

---

## Database & File Locations

| Item | Path |
|------|------|
| SQLite Database | `data/literature.db` |
| Projects Config | `data/projects.json` |
| Workflow Doc | `docs/CLAUDE_EXTRACTION_WORKFLOW.md` |
| This State File | `docs/EXTRACTION_SESSION_STATE.md` |
| Serena Memory | `.serena/memories/claude-extraction-workflow.md` |

---

## Commands to Resume

```bash
# Check extraction queue
# In Claude Code, use: get_extraction_queue(limit=20)

# Get next paper info
# Use: get_paper(paper_id=8)  # or next ID

# Start extraction
# Use: prepare_extraction(paper_id=8, tier='deep')
```

---

## Notes

- Extractions are stored in `PaperContent` table (one_sentence_summary, key_findings, etc.)
- `ExtractionMetadata` stores PDF/chunking metadata (separate from AI extraction)
- User preference: one paper at a time for highest quality
- Long papers (>15K words): use multi-pass approach
- Always update this file after completing papers
