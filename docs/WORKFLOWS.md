# Literature Management Workflows

This document covers the two main workflows for the Literature Management System.

Tool names below match the current consolidated tool set — see `docs/TOOL_REFERENCE.md`
for exact signatures.

---

## 1. Import & Update Pipeline

### Entry Points

| Source | Primary Tools | Auto Steps |
|--------|---------------|------------|
| **DOI** | `import_paper(doi=)` | Duplicate check, enrich, embed |
| **arXiv ID** | `import_paper(arxiv_id=)` | Duplicate check, enrich, download PDF, embed |
| **Title only** | `search_external_papers` → select → `import_paper(doi=)` | Enrich, embed |
| **PDF file** | `import_paper(pdf_path=)` or `manage_pdf(action="process")` | Extract text, chunk, embed |
| **BibTeX** | `import_paper(source="bibtex", bibtex_content=)` or `manage_bibtex(action="import")` | Enrich each entry |
| **Zotero** | `src/scripts/zotero_import.py` (offline CLI, see below) | Reads zotero.sqlite snapshot |

### Standard Import Flow

```
1. Entry Point (DOI/arXiv/title/PDF)
       ↓
2. Duplicate Check
   - Automatic with import_paper(source="wizard")  # the default
   - Or manual: find_duplicates(method="title")    # or "hash" for PDFs
       ↓
3. Create Paper Entry
   - import_paper() or add_paper()
       ↓
4. Metadata Enrichment
   - enrich_paper(paper_id)
   - Sources: CrossRef → OpenAlex → Semantic Scholar → arXiv
       ↓
5. PDF Acquisition
   - find_open_access_pdf(doi=)
   - acquire_pdf(paper_id)                          # open access download
   - Or: acquire_pdf(paper_id, method="browser_queue")  # Windows browser automation
       ↓
6. Text Extraction & Chunking
   - manage_pdf_processing(action="add", paper_id=)  # queue for chunking
   - manage_pdf_processing(action="process")         # run the queue
   - Creates PaperChunk records
       ↓
7. Embedding Generation
   - manage_embeddings(action="embed", paper_id=)
   - Or: manage_embeddings(action="process")  # batch
       ↓
8. Paper Complete
```

### PDF Acquisition Strategies

| Method | Tool | When to Use |
|--------|------|-------------|
| Open Access | `acquire_pdf(paper_id)` | Unpaywall finds OA version |
| arXiv | Auto with `import_paper(arxiv_id=)` | Has arXiv ID |
| VPN | `acquire_pdf(paper_id, use_vpn=True)` | Connected to institutional VPN |
| Browser | `acquire_pdf(paper_id, method="browser_queue")` | Need manual browser login |

### Batch Import

```python
# BibTeX file
manage_bibtex(action="parse", file_path="refs.bib")  # Preview entries
manage_bibtex(action="import", file_path="refs.bib", tags=["project-x"])

# Zotero (offline snapshot import — no MCP tool; run the CLI)
# cd src && mamba run -n litai python -m scripts.zotero_import          # dry-run report
# cd src && mamba run -n litai python -m scripts.zotero_import --execute

# Batch PDF download via Windows browser queue
acquire_pdf(paper_ids=[...], method="browser_queue")
manage_pdf(action="queue_status")
manage_pdf(action="process")  # import downloaded PDFs
```

### Enrichment Status Values

| Status | Meaning | Next Action |
|--------|---------|-------------|
| `pending` | Just added, needs triage | `enrich_paper()` |
| `needs_pdf` | Has metadata, waiting for PDF | `acquire_pdf()` |
| `needs_chunking` | Has PDF, needs text extraction | `manage_pdf_processing(action="add")` |
| `needs_extraction` | Has chunks, queued for quick extraction | `extract_paper(tier="quick")` |
| `complete` | Quick extraction done (or deep complete) | None (or flag for deep) |
| `needs_deep_extraction` | Flagged for deep extraction | `extract_paper(tier="deep")` |
| `needs_review` | Auto-process found issue | Manual review |
| `failed` | Unrecoverable error | Manual fix |

### Enrichment Flow Diagram

```
PENDING → NEEDS_PDF → NEEDS_CHUNKING → NEEDS_EXTRACTION → COMPLETE
             ↘            ↘                ↘                  ↓
            FAILED       FAILED           FAILED    NEEDS_DEEP_EXTRACTION → COMPLETE
```

### Flagging for Deep Extraction

Papers marked `complete` after quick extraction can be flagged for deep extraction:

```python
# Single paper
flag_for_deep_extraction(paper_id=123)

# Batch (e.g., based on relevance scoring)
flag_for_deep_extraction(paper_ids=[1, 2, 3, 4, 5])
```

---

## 2. Two-Tier Extraction Pipeline

### Overview

| Tier | Input | Output | When | Model |
|------|-------|--------|------|-------|
| **Quick** | Title + abstract | paper_type, topics, one_sentence_summary | All papers on import | Claude Code |
| **Deep** | PDF chunks | Full 15-field schema + verification | Relevant papers only | Ollama |

### Quick Extraction (Abstract-Only)

Fast categorization for all papers with abstracts:

```python
# Automatic on import, or manual trigger
store_extraction(
    paper_id=123,
    paper_type="research_article",
    topics=["atomic layer deposition", "thin films", "HfO2"],
    one_sentence_summary="This paper demonstrates...",
)
```

**Output fields:**
- `paper_type`: research_article, review, perspective, letter, conference, etc.
- `topics`: 3-5 hierarchical topics (broad → specific)
- `one_sentence_summary`: 20-40 word summary

### Deep Extraction (PDF-Based)

Comprehensive extraction using 2-pass approach:

```python
# Pass 1: Process each chunk
for chunk in paper_chunks:
    result = extract_chunk(title, chunk_text, chunk_num, total_chunks)
    # → section_type, key_points, quantitative_data, techniques, claims

# Pass 2: Consolidate
final = consolidate_chunks(title, abstract, quick_extraction, chunk_results)
# → Full schema with verification against quick extraction
```

**Additional deep fields:**
- `key_findings`: Specific findings with quantitative data
- `methodology_summary`: Experimental/computational setup
- `quantitative_results`: Metrics, values, units, conditions
- `citable_claims`: Quotable assertions
- `techniques_used`: Methods with purposes and specifics
- `experimental_conditions`: Materials, temperatures, parameters
- `verification`: Comparison of quick vs deep results

### Schema v2.1: Separate Storage

Quick and deep extractions are stored separately (not overwritten):

| Field | Source | Description |
|-------|--------|-------------|
| `paper_type` | Quick | From abstract |
| `deep_paper_type` | Deep | From full PDF (may differ) |
| `topics` | Quick | From abstract |
| `deep_topics` | Deep | From full PDF |
| `one_sentence_summary` | Quick | From abstract |
| `deep_one_sentence_summary` | Deep | From full PDF |
| `verification` | Auto | Comparison of quick vs deep |

### Extraction Workflow

```
1. Paper Imported (status: pending/needs_pdf)
       ↓
2. PDF Acquired & Chunked
   - Text extraction → PaperChunk records
   - Status: needs_chunking → needs_extraction
       ↓
3. Quick Extraction (Claude Code)
   - Uses title + abstract
   - Sets: paper_type, topics, one_sentence_summary
   - Sets: quick_extraction_date
   - Status: needs_extraction → complete
       ↓
4. Relevance Check / Manual Review
   - Score paper against project topics
   - Decide: flag for deep or leave complete
   - flag_for_deep_extraction(paper_id) → status: needs_deep_extraction
       ↓
5. Deep Extraction (Ollama) [if flagged]
   - Pass 1: Per-chunk extraction
   - Pass 2: Consolidation + verification
   - Sets: deep_paper_type, deep_topics, deep_one_sentence_summary
   - Sets: key_findings, methodology_summary, etc.
   - Sets: deep_extraction_date, verification
   - Status: needs_deep_extraction → complete
       ↓
6. Complete (with both quick and deep data preserved)
```

---

## Enrichment Batch (Overnight)

Backfills chunks, deep-extracts, and verifies extractions in one resumable
pass — designed to run unattended overnight, one Ollama model resident per
stage.

```bash
# 1. Pull the models used across stages (once, or after an upgrade)
ollama pull qwen3.5:9b                        # deep extraction + judge fallback vision
ollama pull qwen3:4b-instruct-2507-q4_K_M     # quick extraction
ollama pull bespoke-minicheck:7b              # Tier 1 NLI claim verification
ollama pull llama3.1:8b                       # Tier 2 cross-family judge

# 2. Run the pipeline (chunk backfill → deep extraction → verification)
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.enrich_pipeline --stage all --limit 20

# Dry run first to see what would be processed, with no writes:
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.enrich_pipeline --stage all --dry-run
```

```python
# 3. Inspect the review queue — papers with verification_score below the
#    accept threshold, worst first
verify_extraction(scope="queue", limit=20)
# → [{paper_id, title, verification_score, routing, failures}, ...]
```

**Routing thresholds** (`VerificationService`):

| Score | Routing | Meaning |
|-------|---------|---------|
| ≥ 0.85 | `accept` | Extraction trusted as-is |
| 0.60 – 0.85 | `reextract` | One automatic re-extraction attempt |
| < 0.60 (or still below 0.85 after retry) | `review` | Needs manual review via the queue |

**Calibration note**: before trusting auto-accept on a new corpus or after a
prompt/model change, spot-check roughly 30-50 papers via
`verify_extraction(scope="queue")` (and a similar sample of accepted papers)
to confirm the score bands line up with actual extraction quality. Adjust
expectations — not the thresholds — unless a systematic bias shows up across
many papers.

---

## 3. Query & Cite Pipeline

### Search Modes

| Mode | Best For | Example |
|------|----------|---------|
| `smart` (default) | Most searches - handles typos, acronyms | `search("ALD thin films")` |
| `keyword` | Exact phrase matching | `search("hafnium oxide", mode="keyword")` |
| `semantic` | Conceptual search | `search("how atoms deposit", mode="semantic")` |
| `hybrid` | Balanced keyword + semantic | `search(query, mode="hybrid", alpha=0.65)` |
| `exact` | Fast known-paper lookup | `search("exact title", mode="exact")` |

### Finding Papers

```python
# Search library
search(query="topic", mode="smart", limit=20)
list_papers(author="Smith")   # filter by author
list_papers(tag="methods")    # filter by tag

# Expand from good results
semantic_find(input_type="paper", paper_id=42, limit=10)
semantic_find(input_type="text", text="paragraph describing need")

# Search external databases
search_external_papers(query="topic", sources=["crossref", "semantic_scholar"])
```

### Citation Network

```python
# Who cited this paper?
get_citations(direction="incoming", paper_id=42)

# What does it cite?
get_citations(direction="outgoing", paper_id=42)

# Local citation graph (no API calls)
get_local_citations(paper_id=42)

# Papers citing same sources
find_common_references(paper_id=42)

# Build network visualization
build_citation_graph(paper_ids=[...], depth=1)
```

### Citation Suggestions

```python
# Get suggestions for a paragraph
semantic_find(
    input_type="citation",
    text="Your paragraph needing citations",
    limit=5,
    include_bibtex=True,
    prefer_type="review",  # or "primary" for specific claims
)
```

### Manuscript Citation Health

```python
# Setup project
manage_project(
    action="set",
    project_path="/path/to/thesis",
    bib_files=["thesis.bib"],
    tex_paths=["chapters/"],
)

# Full health check
citation_health_check(bib_path="thesis.bib", tex_path="chapters/")
# Returns: missing citations, orphan entries, incomplete entries, duplicates

# Individual checks
citation_health_check(check="missing", bib_path=..., tex_path=...)     # \cite{} not in .bib
citation_health_check(check="orphans", bib_path=..., tex_path=...)     # Entries never cited
citation_health_check(check="incomplete", bib_path=...)                # Missing required fields
citation_health_check(check="duplicates", bib_path=...)                # Duplicate entries

# Scan manuscript for citation keys
scan_citations(file_path="chapters/", mode="scan")

# Sync database to bib
manage_bibtex(action="sync", file_path="thesis.bib", dry_run=True)   # Preview changes
manage_bibtex(action="sync", file_path="thesis.bib", dry_run=False)  # Apply changes
```

### Bibliography Generation

```python
# Export by IDs
export(paper_ids=[1, 2, 3], format="bibtex")

# Export a collection
export(source="collection", collection_id=5, format="bibtex",
       include_subcollections=True)

# Export by tag (BibTeX file)
manage_bibtex(action="export", tag="thesis-ch3", output_path="ch3.bib")

# Generate formatted bibliography
format_citation(action="bibliography", papers=[...], style="apa")  # or 'mla', 'chicago'

# Generate citation key
format_citation(action="suggest_key", title="...", authors="Smith, John")
```

---

## Reading Queue Management

```python
# View queue
get_reading_queue(limit=20, min_rating=4, tag="priority")

# Update status
update_paper(paper_id, read_status='reading')  # Start
update_paper(paper_id, read_status='read', rating=4)  # Complete

# Note-taking
create_note(paper_id, content="Key finding...", note_type='highlight', page_number=5)
list_notes(paper_id=paper_id)
```

**Read status values**: `unread`, `reading`, `read`

**Note types**: `highlight`, `comment`, `summary`

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `PAPER_NOT_FOUND` | Invalid paper_id | Verify with `list_papers()` |
| `DUPLICATE_DOI` | Paper already exists | Return existing paper_id |
| `EXTERNAL_API_ERROR` | API rate limit or down | Wait and retry, try alternative source |
| `PDF_DOWNLOAD_FAILED` | Paywall or network | Queue for browser download |
| `SEARCH_NO_RESULTS` | Query too specific | Broaden terms, try synonyms |
| `CITATION_KEY_MISMATCH` | Typo in `\cite{}` | Check exact key spelling |

### Recovery Strategies

**API rate limited**: Wait 60 seconds, retry with different source

**PDF not accessible**: Try `find_open_access_pdf()`, then
`acquire_pdf(paper_id, method="browser_queue")` for browser download

**Search returns wrong results**: Try different mode, use more specific terms, filter by author
