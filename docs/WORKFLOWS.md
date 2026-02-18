# Literature Management Workflows

This document covers the two main workflows for the Literature Management System.

---

## 1. Import & Update Pipeline

### Entry Points

| Source | Primary Tools | Auto Steps |
|--------|---------------|------------|
| **DOI** | `import_from_external(doi=)` | Enrich, find PDF, embed |
| **arXiv ID** | `import_from_external(arxiv_id=)` | Enrich, download PDF, embed |
| **Title only** | `search_external_papers` → select → `import_from_external` | Enrich, embed |
| **PDF file** | `process_downloaded_pdfs()` | Extract text, chunk, embed |
| **BibTeX** | `import_bibtex(content)` | Enrich each entry |
| **Zotero** | `sync_from_zotero()` | Process new papers with PDFs |

### Standard Import Flow

```
1. Entry Point (DOI/arXiv/title/PDF)
       ↓
2. Duplicate Check
   - find_duplicates(method="title")  # or "hash" for PDFs
       ↓
3. Create Paper Entry
   - import_from_external() or add_paper()
       ↓
4. Metadata Enrichment
   - enrich_paper(paper_id)
   - Sources: CrossRef → OpenAlex → Semantic Scholar → arXiv
       ↓
5. PDF Acquisition
   - find_open_access_pdf(doi=)
   - acquire_paper_pdf(paper_id)
   - Or: queue_pdf_download() for browser automation
       ↓
6. Text Extraction & Chunking
   - Automatic when PDF is processed
   - Creates PaperChunk records
       ↓
7. Embedding Generation
   - embed_paper(paper_id)
   - Or: process_embedding_queue() for batch
       ↓
8. Paper Complete
```

### PDF Acquisition Strategies

| Method | Tool | When to Use |
|--------|------|-------------|
| Open Access | `acquire_paper_pdf(paper_id)` | Unpaywall finds OA version |
| arXiv | Auto with `import_from_external(arxiv_id)` | Has arXiv ID |
| VPN | `acquire_paper_pdf(paper_id, use_vpn=True)` | Connected to institutional VPN |
| Browser | `queue_pdf_download(paper_id)` | Need manual browser login |

### Batch Import

```python
# BibTeX file
parse_bib_file(file_path="refs.bib")  # Preview entries
import_bibtex(bibtex_content, tags=["project-x"])

# Zotero sync
check_zotero_connection()
sync_from_zotero()

# Batch PDF download
queue_batch_pdf_download(paper_ids=[...])
get_download_queue_status()
process_downloaded_pdfs()
```

### Enrichment Status Values

| Status | Meaning | Next Action |
|--------|---------|-------------|
| `pending` | Just added, needs triage | `enrich_paper()` |
| `needs_pdf` | Has metadata, waiting for PDF | `acquire_paper_pdf()` |
| `needs_chunking` | Has PDF, needs text extraction | `queue_pdf_processing()` |
| `needs_extraction` | Has chunks, queued for quick extraction | `extract_paper_quick()` |
| `complete` | Quick extraction done (or deep complete) | None (or flag for deep) |
| `needs_deep_extraction` | Flagged for deep extraction | `extract_paper_deep()` |
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

## 3. Two-Tier Extraction Pipeline

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
    is_quick=True  # Default for Claude
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

## 2. Query & Cite Pipeline

### Search Modes

| Mode | Best For | Example |
|------|----------|---------|
| `smart` (default) | Most searches - handles typos, acronyms | `search("ALD thin films")` |
| `keyword` | Exact phrase matching | `search("hafnium oxide", mode="keyword")` |
| `semantic` | Conceptual search | `search("how atoms deposit", mode="semantic")` |
| `hybrid` | Balanced keyword + semantic | `search(query, mode="hybrid", alpha=0.65)` |

### Finding Papers

```python
# Search library
search(query="topic", mode="smart", limit=20)
search_by_author(author_name="Smith")
search_by_tag(tag="methods")

# Expand from good results
find_similar_papers(paper_id, limit=10)
find_papers_like_text(text="paragraph describing need")

# Search external databases
search_external_papers(query="topic", sources=["crossref", "semantic_scholar"])
```

### Citation Network

```python
# Who cited this paper?
get_paper_citations(paper_id)

# What does it cite?
get_paper_references(paper_id)

# Papers citing same sources
find_common_references(paper_id)

# Build network visualization
build_citation_graph(paper_ids=[...], depth=1)
```

### Citation Suggestions

```python
# Get suggestions for a paragraph
suggest_citations_for_text(
    text="Your paragraph needing citations",
    limit=5,
    include_bibtex=True
)
```

### Manuscript Citation Health

```python
# Setup project
set_project_config(
    project_path="/path/to/thesis",
    bib_files=["thesis.bib"],
    tex_paths=["chapters/"]
)

# Full health check
citation_health_check(bib_path="thesis.bib", tex_path="chapters/")
# Returns: missing citations, orphan entries, incomplete entries, duplicates

# Individual checks
find_missing_citations(bib_path, tex_path)      # Keys in \cite{} but not in .bib
find_orphan_citations(bib_path, tex_path)       # Entries never cited
find_incomplete_bib_entries(bib_path)           # Missing required fields
find_duplicate_bib_entries(bib_path)            # Duplicate entries

# Sync database to bib
sync_bib_from_database(bib_path, dry_run=True)  # Preview changes
sync_bib_from_database(bib_path, dry_run=False) # Apply changes
```

### Bibliography Generation

```python
# Export by IDs
export_papers(paper_ids=[1,2,3], format='bibtex')

# Export by tag
export_papers(tag='thesis-ch3', format='bibtex')

# Export collection
export_collection(collection_id=5, format='bibtex', include_subcollections=True)

# Generate formatted bibliography
format_bibliography(papers, style='apa')  # or 'mla', 'chicago', 'bibtex'

# Generate citation key
suggest_citation_key(title="...", authors="Smith, John")
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
get_paper_notes(paper_id)
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

**PDF not accessible**: Try `find_open_access_pdf()`, then `queue_pdf_download()` for browser

**Search returns wrong results**: Try different mode, use more specific terms, search by author
