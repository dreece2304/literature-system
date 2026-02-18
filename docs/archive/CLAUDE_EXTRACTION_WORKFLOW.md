# Claude-Powered Paper Extraction Workflow

## Overview

Use Claude (in Claude Code session) to extract structured content from papers. This leverages Claude's superior reasoning for high-quality extractions with project relevance scoring.

## Two-Tier Extraction System

### Quick Tier (Title + Abstract)
Fast categorization in ~10-30 seconds:
- Paper type classification
- Topic extraction (3-5 tags)
- One-sentence summary
- Project relevance scores

### Deep Tier (Full Text)
Comprehensive extraction in ~1-3 minutes:
- All quick tier fields
- Key findings with specific numbers
- Quantitative results
- Methodology details
- Citable claims
- Papers worth following

## Workflow

### CRITICAL: Checking for Full Text
```
# prepare_extraction(tier='quick') shows full_text=null EVEN WHEN FULL TEXT EXISTS!
# You MUST call get_paper_content to check actual content:

get_paper_content(paper_id=X, max_chars=500)
→ Check response._truncation.total_chars
→ If total_chars > 1000: FULL TEXT EXISTS - use multi-pass below
→ If total_chars < 1000: Abstract-only - use quick extraction
```

### Full Text Extraction (Multi-Pass with Compaction Protection)
```
User: "Extract paper 444"
    ↓
Claude calls: get_paper_content(paper_id=444, max_chars=500)
    ↓
Tool returns: _truncation.total_chars = 85000 (has full text!)
    ↓
Claude reads chunks AND SAVES NOTES after each:
  - get_paper_content(paper_id=444, offset=0, max_chars=20000)
  - create_note(paper_id=444, content="CHUNK 1: [key findings...]", note_type="comment")

  - get_paper_content(paper_id=444, offset=20000, max_chars=20000)
  - create_note(paper_id=444, content="CHUNK 2: [methods...]", note_type="comment")

  - get_paper_content(paper_id=444, offset=40000, max_chars=20000)
  - create_note(paper_id=444, content="CHUNK 3: [results...]", note_type="comment")

  - ... until remaining_chars=0
    ↓
Claude retrieves saved notes: get_paper_notes(paper_id=444)
    ↓
Claude consolidates findings from ALL notes
    ↓
Claude calls: store_full_extraction(paper_id=444, ...)
    ↓
Claude cleans up: delete_paper_notes(paper_id=444, note_type="comment")
    ↓
Done
```

### Why Save Notes After Each Chunk?
If conversation gets compacted mid-extraction, earlier chunk findings are LOST from context.
Saving notes to database protects against this - you can always retrieve and continue.

### Abstract-Only Extraction
```
User: "Extract paper 444"
    ↓
Claude calls: get_paper_content(paper_id=444, max_chars=500)
    ↓
Tool returns: _truncation.total_chars = 0 (no full text)
    ↓
Claude calls: prepare_extraction(paper_id=444, tier="quick")
    ↓
Claude extracts from abstract only
    ↓
Claude calls: store_full_extraction(paper_id=444, ...)
    ↓
Done
```

## MCP Tools

### `get_paper_content` (USE THIS TO CHECK FOR FULL TEXT)
Returns paper content with pagination support:

```
paper_id: int       # Required
max_chars: int      # Max chars to return (default: 50000)
offset: int         # Start position for pagination (default: 0)
```

**Returns:**
- `full_text`: The text content (or portion of it)
- `word_count`: Total word count of full text
- `_truncation`: {total_chars, returned_chars, offset, remaining_chars}

**IMPORTANT:** Check `_truncation.total_chars` to see if full text exists!

### `prepare_extraction`
Gets metadata and project context (but NOT reliable for checking full text):

```
paper_id: int      # Required - Paper to extract
tier: string       # "quick" (default) or "deep"
max_chars: int     # Max full text chars (default: 80000)
```

**Returns:**
- `paper`: {id, title, authors, year, abstract, full_text (if deep)}
- `projects`: [{name, topics, focus, relevance_hints, paper_in_bib, citation_key}]
- `existing_extraction`: {has_extraction, paper_type, summary}
- `review_detection`: {likely_review, recommendation}
- `extraction_schema`: {tier, required_fields, instructions}

**WARNING:** `full_text=null` in tier='quick' does NOT mean no full text exists!
Always use `get_paper_content` to check for actual content.

### `store_full_extraction`
Stores comprehensive extraction with all fields:

**Core fields:**
- `paper_id` (required)
- `paper_type`: research_article, review, letter, conference, etc.
- `topics`: List of themes
- `one_sentence_summary`: WHAT + HOW + RESULT

**Extended fields:**
- `key_findings`: List with specific numbers
- `quantitative_results`: [{metric, value, unit, conditions}]
- `citable_claims`: Specific quotable assertions
- `techniques_used`: [{technique, purpose, specifics}]
- `methodology_summary`: Methods description
- `discussion_summary`: Key interpretations
- `research_context`: {problem_addressed, novelty, limitations, significance}
- `citation_contexts`: {introduction, methods, results, discussion}
- `future_directions`: Suggested follow-up

**Project relevance (stored in structured_data):**
```json
{
  "project_relevance": {
    "thesis": {
      "relevance": "high",
      "reason": "Directly discusses MLD thin films",
      "primary_use": "methods",
      "already_cited": false
    },
    "paper2": {
      "relevance": "medium",
      "reason": "Related EUV resist work",
      "primary_use": "discussion",
      "already_cited": true
    }
  }
}
```

## Project Registry

Projects are defined in `data/projects.json`:

```json
{
  "projects": [
    {
      "name": "thesis",
      "display_name": "PhD Thesis",
      "path": "/path/to/thesis",
      "bib_file": "thesis/uwthesis.bib",
      "topics": ["MLD", "ALD", "EUV"],
      "focus": "High-throughput screening of hybrid thin films",
      "relevance_hints": {
        "high": "Directly discusses MLD/ALD...",
        "medium": "Related thin film techniques...",
        "low": "General ALD/CVD basics..."
      }
    }
  ]
}
```

## Example Sessions

### Quick Extraction
```
User: Categorize paper 444

Claude: Let me prepare the extraction context.
[calls prepare_extraction(paper_id=444, tier="quick")]

Based on the abstract, I've extracted:
- Paper type: research_article
- Topics: ["atomic layer deposition", "thin films", "FTIR"]
- Summary: This paper demonstrates...
- Thesis relevance: HIGH (directly about ALD)
- Paper2 relevance: LOW (not EUV-related)

[calls store_full_extraction(...)]
Saved extraction for paper 444.
```

### Deep Extraction (Short Papers <20K chars)
```
User: Deep extract paper 444

Claude: Let me check the paper length first.
[calls prepare_extraction(paper_id=444, tier="quick")]
→ original_chars: 15000 (short paper)

[calls prepare_extraction(paper_id=444, tier="deep", max_chars=50000)]
→ Returns full_text without truncation

I've analyzed the full paper and extracted:
- Paper type: research_article
- Key findings: ["Achieved 1.1 Å/cycle growth rate", ...]
- Quantitative results: [{metric: "growth rate", value: "1.1", ...}]

[calls store_full_extraction(...)]
Complete extraction saved for paper 444.
```

### Deep Extraction (Long Papers >20K chars) - MULTI-PASS REQUIRED
```
User: Extract this long paper

Claude: Let me check the paper length first.
[calls prepare_extraction(paper_id=123, tier="quick")]
→ original_chars: 85000 (long paper - need multi-pass)

Reading chunk by chunk using get_paper_content:
[calls get_paper_content(paper_id=123, offset=0, max_chars=20000)]
→ Chunk 1: Introduction, Background... (notes: key context)

[calls get_paper_content(paper_id=123, offset=20000, max_chars=20000)]
→ Chunk 2: Methods section... (notes: techniques used)

[calls get_paper_content(paper_id=123, offset=40000, max_chars=20000)]
→ Chunk 3: Results... (notes: quantitative findings)

[calls get_paper_content(paper_id=123, offset=60000, max_chars=20000)]
→ Chunk 4: Discussion, Conclusions... (notes: claims, future work)

[calls get_paper_content(paper_id=123, offset=80000, max_chars=20000)]
→ remaining_chars: 0 (done reading)

Now consolidating all findings from chunks 1-5...

[calls store_full_extraction(...)]
Complete extraction saved.
```

### CRITICAL RULES - NO EXCEPTIONS
1. DO NOT use prepare_extraction(tier="deep") for long papers - it TRUNCATES
2. Use `get_paper_content` with offset pagination to read ALL chunks
3. Read until `remaining_chars=0`
4. **EXTRACT EVERY PAPER FULLY** - no skipping based on relevance
5. **NO JUDGMENT CALLS** - follow the workflow exactly for every paper
6. **SAME QUALITY FOR ALL** - "less relevant" papers get the same full extraction
7. Relevance scoring happens DURING extraction, not as a filter to skip papers

## Batch Extraction

For small batches (5-10 papers):
```
User: Quick extract papers 440-445

Claude: I'll process each paper with quick tier extraction.
[Processes sequentially, ~30 sec each]
```

For large batches, use Ollama overnight:
```bash
mamba run -n litai python scripts/continuous_extraction.py --backend ollama
```

## Token Limits

| Tier | ~Tokens/paper | Max batch |
|------|---------------|-----------|
| Quick | 1-2K | 20-30 papers |
| Deep | 15-50K | 1-3 papers |

## Local LLM Alternative

For overnight batch processing:
```bash
mamba run -n litai python scripts/continuous_extraction.py --backend ollama
```

## Configuration

Database: `data/literature.db`
Projects: `data/projects.json`
Settings: `src/config/ai_settings.py`
