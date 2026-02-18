# Extraction Workflow Test Plan

## Overview
Test the new two-tier extraction workflow (Schema v2.1) with a single paper before batch processing.

## Pre-requisites
1. **Restart MCP server** - Required for new `flag_for_deep_extraction` tool
2. **Ensure Ollama is running** - `ollama serve` with model loaded
3. **Check Ollama model**: `ollama list` should show `qwen2.5:7b-instruct-q4_K_M` or similar

---

## Phase 1: Quick Extraction Test (No PDF needed)

### Step 1.1: Import a paper by DOI
```
# Using MCP tool - pick a paper with abstract available:
import_from_external(doi="10.1038/s41586-023-06735-9")

# Or search and import:
search_external_papers(query="atomic layer deposition review 2023", limit=3)
import_from_external(doi="<selected_doi>")
```

### Step 1.2: Check initial status
```
get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "needs_pdf" (no PDF) or "needs_chunking" (has PDF)
```

### Step 1.3: Run quick extraction
Claude Code should analyze the abstract and call:
```
store_extraction(
    paper_id=<new_id>,
    paper_type="<type>",
    topics=["topic1", "topic2", "topic3"],
    one_sentence_summary="<summary>",
    is_quick=True  # Default
)
```

### Step 1.4: Verify quick extraction
```
get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "complete"

get_paper_content(paper_id=<new_id>)
# Expected: paper_type, topics, one_sentence_summary populated
#           quick_extraction_date set
```

---

## Phase 2: Deep Extraction Test (Requires PDF + Ollama)

### Step 2.1: Acquire PDF
```
acquire_paper_pdf(paper_id=<new_id>)
# Or if not open access:
queue_pdf_download(paper_id=<new_id>)  # For browser automation
```

### Step 2.2: Check status after PDF
```
get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "needs_chunking", file_path populated
```

### Step 2.3: Process PDF (extract text, create chunks)
```
queue_pdf_processing(paper_id=<new_id>)
process_pdf_queue(limit=1)
```

### Step 2.4: Check status after chunking
```
get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "needs_extraction"

get_pdf_processing_status(paper_id=<new_id>)
# Expected: chunking_status = "complete", chunk_count > 0
```

### Step 2.5: Flag for deep extraction
```
flag_for_deep_extraction(paper_id=<new_id>)

get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "needs_deep_extraction"
```

### Step 2.6: Run deep extraction (Ollama)
```
extract_paper_deep(paper_id=<new_id>, backend="ollama")
# This runs 2-pass extraction: chunk analysis → consolidation
```

### Step 2.7: Verify deep extraction
```
get_paper(paper_id=<new_id>)
# Expected: enrichment_status = "complete"

get_paper_content(paper_id=<new_id>)
# Expected: 
#   - Quick fields preserved: paper_type, topics, one_sentence_summary
#   - Deep fields populated: deep_paper_type, deep_topics, deep_one_sentence_summary
#   - Extended fields: key_findings, methodology_summary
#   - Verification: comparison of quick vs deep
#   - deep_extraction_date set
```

---

## Phase 3: Batch Re-extraction Commands

After single paper test succeeds, run these from terminal:

### 3.1: Check current status distribution
```bash
cd /home/dreece23/projects/research/misc/research
/home/dreece23/miniforge3/bin/mamba run -n litai python -c "
from literature_core import get_session, Paper, EnrichmentStatus
with get_session() as s:
    counts = {}
    for status in EnrichmentStatus.ALL:
        counts[status] = s.query(Paper).filter(Paper.enrichment_status == status).count()
    for k, v in sorted(counts.items()):
        print(f'{k}: {v}')
"
```

### 3.2: Process all PDFs needing chunking
```bash
/home/dreece23/miniforge3/bin/mamba run -n litai python -c "
from services.extraction_service import ExtractionService
result = ExtractionService.process_extraction_queue(limit=100)
print(f'Processed: {result}')
"
```

### 3.3: Batch deep extraction (Ollama) - run in batches
```bash
# Run multiple times, processing 10 papers at a time
/home/dreece23/miniforge3/bin/mamba run -n litai python -c "
import asyncio
from services.extraction_service import ExtractionService
result = asyncio.run(ExtractionService.extract_batch(limit=10, backend='ollama', delay=2.0))
print(f'Result: {result}')
"
```

### 3.4: Flag high-relevance papers for deep extraction
```bash
# After quick extraction, flag papers based on relevance
/home/dreece23/miniforge3/bin/mamba run -n litai python -c "
from services.paper_service import PaperService
from literature_core import get_session, Paper, EnrichmentStatus

# Example: Flag all 'complete' papers that have PDFs for deep extraction
with get_session() as s:
    papers = s.query(Paper).filter(
        Paper.enrichment_status == EnrichmentStatus.COMPLETE,
        Paper.file_path.isnot(None)
    ).all()
    paper_ids = [p.id for p in papers]
    print(f'Found {len(paper_ids)} papers to flag')

if paper_ids:
    result = PaperService.batch_flag_for_deep_extraction(paper_ids)
    print(f'Flagged: {result}')
"
```

---

## Expected Final State

After full workflow:
- All papers with abstracts: have quick extraction (paper_type, topics, summary)
- All papers with PDFs: have chunks extracted
- High-relevance papers: have deep extraction with verification

## Troubleshooting

### Ollama not available
```bash
# Check if running
curl http://localhost:11434/api/tags

# Start if needed
ollama serve
```

### Check LLM status via MCP
```
get_llm_status()
```

### View extraction errors
```
get_extraction_status()
get_pdf_processing_queue(status="failed")
```
