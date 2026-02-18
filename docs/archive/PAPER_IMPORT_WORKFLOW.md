# Paper Import & Processing Workflow

## Overview

This document guides Claude agents through the complete paper import and processing pipeline. Use this when helping users add papers to their literature database.

## Quick Reference: Completeness Tiers

| Tier | Fields | How to Advance |
|------|--------|----------------|
| **Minimal** | Title only | `add_paper(title)` |
| **Basic** | + authors, year | `enrich_paper` or manual |
| **Standard** | + DOI/arXiv + abstract | `enrich_paper`, `import_from_external` |
| **Indexed** | + embeddings + FTS | `embed_paper` (auto after text) |
| **Complete** | + full text + validated | `acquire_paper_pdf`, `validate_paper` |

---

## Entry Point Decision Tree

```mermaid
flowchart TD
    START[Import Request] --> Q1{What data is available?}

    Q1 -->|PDF file| PDF[PDF Import Path]
    Q1 -->|DOI| DOI[DOI Import Path]
    Q1 -->|arXiv ID| ARXIV[arXiv Import Path]
    Q1 -->|Title only| TITLE[Title Search Path]
    Q1 -->|BibTeX file| BIBTEX[BibTeX Batch Import]
    Q1 -->|Zotero library| ZOTERO[Zotero Sync]

    PDF --> SEC3.1[See Section 3.1]
    DOI --> SEC3.2[See Section 3.2]
    ARXIV --> SEC3.3[See Section 3.3]
    TITLE --> SEC3.4[See Section 3.4]
    BIBTEX --> SEC3.5[See Section 3.5]
    ZOTERO --> SEC3.6[See Section 3.6]
```

---

## 3. Import Scenarios

### 3.1 PDF File Import

**When to use**: User has a PDF file (downloaded or uploaded)

**Tool sequence**:
```
1. find_duplicates(method="hash")     # Check if PDF already exists
2. add_paper(title="[from PDF]")      # Create paper entry
3. process_downloaded_pdfs()          # Extract text, link PDF
4. enrich_paper(paper_id)             # Fetch metadata by title/DOI
5. embed_paper(paper_id)              # Generate embeddings
```

```mermaid
flowchart TD
    PDF[PDF File] --> HASH[Compute SHA256 hash]
    HASH --> CHECK{Hash exists in DB?}
    CHECK -->|Yes| DUP[Return existing paper_id]
    CHECK -->|No| EXTRACT[Extract text: pdfplumber]

    EXTRACT --> WORDS{Words extracted > 100?}
    WORDS -->|Yes| ANALYZE[Analyze for metadata]
    WORDS -->|No| OCR[Try OCR: Tesseract]
    OCR --> ANALYZE

    ANALYZE --> DOI_CHECK{DOI found in PDF?}
    DOI_CHECK -->|Yes| ENRICH_DOI[enrich_paper by DOI]
    DOI_CHECK -->|No| SEARCH[search_external_papers by title]

    ENRICH_DOI --> EMBED[embed_paper]
    SEARCH --> MATCH{Good match found?}
    MATCH -->|Yes| IMPORT[Add DOI from match]
    MATCH -->|No| MANUAL[Keep minimal entry]
    IMPORT --> EMBED
    MANUAL --> EMBED
    EMBED --> DONE[Paper complete]
```

**Example session**:
```
User: I have a PDF at ~/Downloads/paper.pdf

Claude: Let me process this PDF for you.

[calls find_duplicates(method="hash")]
No duplicates found.

[calls add_paper(title="Pending extraction")]
Created paper ID 456.

[calls process_downloaded_pdfs()]
Extracted 8,500 words from PDF.
Found DOI: 10.1021/acs.chemmater.2c01234

[calls enrich_paper(paper_id=456)]
Added metadata: authors, year, abstract, journal.

[calls embed_paper(paper_id=456)]
Generated embeddings.

Paper 456 is now complete with full text and metadata.
```

---

### 3.2 DOI Import

**When to use**: User provides a DOI (e.g., `10.1021/...`)

**Tool sequence**:
```
1. search(query="doi:10.xxx")         # Check if already in DB
2. import_from_external(doi="10.xxx") # Import with metadata
3. find_open_access_pdf(doi="10.xxx") # Try to find PDF
4. acquire_paper_pdf(paper_id)        # Download PDF if found
5. embed_paper(paper_id)              # Generate embeddings
```

```mermaid
flowchart TD
    DOI[DOI provided] --> LOCAL{In local DB?}
    LOCAL -->|Yes| RETURN[Return existing paper]
    LOCAL -->|No| LOOKUP[import_from_external]

    LOOKUP --> FOUND{Metadata found?}
    FOUND -->|Yes| CREATE[Paper created with full metadata]
    FOUND -->|No| FAIL[Error: DOI not found in CrossRef]

    CREATE --> PDF_SEARCH[find_open_access_pdf]
    PDF_SEARCH --> PDF_RESULT{PDF available?}

    PDF_RESULT -->|Open Access| ACQUIRE[acquire_paper_pdf]
    PDF_RESULT -->|arXiv version| ACQUIRE
    PDF_RESULT -->|Paywall| VPN{VPN available?}
    PDF_RESULT -->|Not found| SKIP[Continue without PDF]

    VPN -->|Yes| VPN_DL[acquire_paper_pdf use_vpn=true]
    VPN -->|No| QUEUE[queue_pdf_download for browser]

    ACQUIRE --> EMBED[embed_paper]
    VPN_DL --> EMBED
    QUEUE --> LATER[PDF acquired later via browser]
    SKIP --> EMBED_PARTIAL[embed_paper - abstract only]
```

**Example session**:
```
User: Add this paper: 10.1021/acs.chemmater.2c01234

Claude: I'll import this DOI.

[calls search(query="doi:10.1021/acs.chemmater.2c01234")]
Not in library yet.

[calls import_from_external(doi="10.1021/acs.chemmater.2c01234")]
Imported: "Atomic Layer Deposition of..." by Smith et al. (2022)
Paper ID: 457

[calls find_open_access_pdf(doi="10.1021/acs.chemmater.2c01234")]
Found open access version via Unpaywall.

[calls acquire_paper_pdf(paper_id=457)]
Downloaded PDF, extracted 12,000 words.

[calls embed_paper(paper_id=457)]
Paper 457 is now fully indexed and searchable.
```

---

### 3.3 arXiv ID Import

**When to use**: User provides arXiv ID (e.g., `2301.12345`)

**Tool sequence**:
```
1. import_from_external(arxiv_id="2301.xxxxx")  # Import + auto PDF
2. embed_paper(paper_id)                         # Index
```

**Special notes**:
- arXiv PDFs are always open access - no acquisition issues
- Check for published version with DOI (preprints often get published)
- Handle version numbers (v1, v2, etc.)

```mermaid
flowchart TD
    ARXIV[arXiv ID] --> IMPORT[import_from_external arxiv_id]
    IMPORT --> SUCCESS{Import successful?}
    SUCCESS -->|Yes| PDF[PDF auto-downloaded from arXiv]
    SUCCESS -->|No| ERROR[Error: arXiv ID not found]

    PDF --> EXTRACT[Text extraction]
    EXTRACT --> DOI_CHECK{Published version exists?}
    DOI_CHECK -->|Yes - has DOI| UPDATE[update_paper with DOI]
    DOI_CHECK -->|No - preprint only| KEEP[Keep arXiv as primary]

    UPDATE --> EMBED[embed_paper]
    KEEP --> EMBED
```

---

### 3.4 Title-Only Import

**When to use**: User only has a paper title

**Tool sequence**:
```
1. find_duplicates(method="title", threshold=0.85)  # Check existing
2. search_external_papers(query="title text")       # Find in external DBs
3. [User selects best match]
4. import_from_external(doi="...")                  # Import selected
5. acquire_paper_pdf(paper_id)                      # Try to get PDF
6. embed_paper(paper_id)                            # Index
```

```mermaid
flowchart TD
    TITLE[Title only] --> DUP[find_duplicates method=title]
    DUP --> MATCH{Similar paper exists?}
    MATCH -->|Yes >85%| CONFIRM{Confirm duplicate?}
    CONFIRM -->|Yes| RETURN[Return existing paper]
    CONFIRM -->|No| CONTINUE[Continue as new]
    MATCH -->|No| CONTINUE

    CONTINUE --> EXTERNAL[search_external_papers]
    EXTERNAL --> RESULTS{Results found?}

    RESULTS -->|Multiple matches| SELECT[Present options to user]
    RESULTS -->|One high-confidence| AUTO[Auto-select if >90%]
    RESULTS -->|None| MANUAL[Create with title only]

    SELECT --> IMPORT[import_from_external selected DOI]
    AUTO --> IMPORT
    MANUAL --> BASIC[add_paper title only - needs enrichment]

    IMPORT --> PDF_TRY[Try PDF acquisition]
    BASIC --> REMIND[Remind: needs manual metadata]
```

**Example session**:
```
User: Add "Atomic layer deposition of aluminum oxide thin films"

Claude: Let me search for this paper.

[calls find_duplicates(method="title", threshold=0.85)]
No duplicates found.

[calls search_external_papers(query="Atomic layer deposition of aluminum oxide thin films")]
Found 3 matches:
1. (95% match) DOI: 10.1063/1.123456 - George et al. 2010, Chemical Reviews
2. (78% match) DOI: 10.1021/... - Similar title, different paper
3. (72% match) DOI: 10.1016/... - Related work

The first result (George et al. 2010) looks like a strong match. Should I import it?

User: Yes, that's the one.

[calls import_from_external(doi="10.1063/1.123456")]
Imported paper ID 458 with full metadata.
```

---

### 3.5 BibTeX Batch Import

**When to use**: User has a .bib file with multiple entries

**Tool sequence**:
```
1. parse_bib_file(file_path)              # Parse and preview
2. import_bibtex(content, tags=["batch"]) # Import all entries
3. enrich_paper(paper_id) for each        # Fill missing metadata
4. queue_batch_pdf_download(paper_ids)    # Queue PDF downloads
```

```mermaid
flowchart TD
    BIB[BibTeX file] --> PARSE[parse_bib_file]
    PARSE --> ENTRIES[List of entries]
    ENTRIES --> PREVIEW[Show preview to user]

    PREVIEW --> CONFIRM{User confirms?}
    CONFIRM -->|No| ABORT[Abort import]
    CONFIRM -->|Yes| LOOP[For each entry]

    LOOP --> DOI_CHK{Has DOI?}
    DOI_CHK -->|Yes| DOI_DUP[Check DOI duplicate]
    DOI_CHK -->|No| TITLE_DUP[Check title duplicate]

    DOI_DUP --> DUP{Duplicate?}
    TITLE_DUP --> DUP

    DUP -->|Yes| SKIP[Skip - log existing ID]
    DUP -->|No| IMPORT[Import entry]

    IMPORT --> NEXT{More entries?}
    SKIP --> NEXT
    NEXT -->|Yes| LOOP
    NEXT -->|No| SUMMARY[Show import summary]

    SUMMARY --> ENRICH[Batch enrich missing data]
    ENRICH --> PDF_QUEUE[queue_batch_pdf_download]
```

**Example session**:
```
User: Import my bibliography from ~/thesis/references.bib

Claude: Let me parse your BibTeX file.

[calls parse_bib_file(file_path="~/thesis/references.bib")]
Found 45 entries:
- 38 have DOIs
- 7 are title-only

[calls import_bibtex(bibtex_content=..., tags=["thesis"])]
Results:
- Imported: 42
- Skipped (duplicates): 3
- Failed: 0

[calls queue_batch_pdf_download(paper_ids=[...])]
Queued 38 papers for PDF download. Use get_download_queue_status() to monitor.
```

---

### 3.6 Zotero Sync

**When to use**: User wants to sync with their Zotero library

**Tool sequence**:
```
1. check_zotero_connection()        # Verify API access
2. sync_from_zotero()               # Pull papers from Zotero
3. enrich_paper() for new papers    # Fill metadata gaps
4. sync_to_zotero()                 # Push enrichments back (optional)
```

```mermaid
flowchart TD
    ZOTERO[Zotero Sync] --> CHECK[check_zotero_connection]
    CHECK --> CONNECTED{API available?}
    CONNECTED -->|No| CONFIG[Configure Zotero API key]
    CONNECTED -->|Yes| PULL[sync_from_zotero]

    PULL --> NEW{New papers found?}
    NEW -->|Yes| PROCESS[For each new paper]
    NEW -->|No| UPTODATE[Library up to date]

    PROCESS --> ENRICH[enrich_paper]
    ENRICH --> PDF{Needs PDF?}
    PDF -->|Yes| ACQUIRE[acquire_paper_pdf]
    PDF -->|No| NEXT[Next paper]
    ACQUIRE --> NEXT

    NEXT --> MORE{More papers?}
    MORE -->|Yes| PROCESS
    MORE -->|No| PUSH{Push enrichments back?}

    PUSH -->|Yes| SYNC_BACK[sync_to_zotero]
    PUSH -->|No| DONE[Sync complete]
```

---

## 4. Metadata Enrichment Pipeline

Use `enrich_paper(paper_id)` to automatically fill missing metadata.

```mermaid
flowchart TD
    PAPER[Paper needs enrichment] --> CHECK{What's missing?}

    CHECK -->|DOI| FIND_DOI[search_external_papers]
    CHECK -->|Abstract| FETCH_ABS[lookup_paper_metadata]
    CHECK -->|Citation count| CITE[get_citation_count]
    CHECK -->|PDF| PDF_FIND[find_open_access_pdf]

    FIND_DOI --> SOURCES
    FETCH_ABS --> SOURCES

    SOURCES[Try external sources in order]
    SOURCES --> CR[1. CrossRef - DOI lookup]
    CR --> OA[2. OpenAlex - abstracts]
    OA --> SS[3. Semantic Scholar - citations]
    SS --> ARXIV[4. arXiv - preprints]

    CR --> MERGE[Merge best data from each]
    OA --> MERGE
    SS --> MERGE
    ARXIV --> MERGE

    MERGE --> UPDATE[update_paper with enriched data]
```

**Source priority**:
| Source | Best for |
|--------|----------|
| CrossRef | DOI validation, core metadata |
| OpenAlex | Abstracts, open access status |
| Semantic Scholar | Citation counts, PDF URLs |
| arXiv | Preprint metadata, always-available PDFs |

---

## 5. Validation & Verification

Use validation to confirm papers exist in external databases.

**Tool sequence**:
```
1. get_validation_status()                    # Check coverage
2. get_validation_queue(prioritize_with_doi=True)  # Get papers to validate
3. validate_paper(paper_id)                   # Verify single paper
4. validate_papers_batch(paper_ids)           # Batch validation
```

```mermaid
flowchart TD
    START[Validation needed] --> STATUS[get_validation_status]
    STATUS --> QUEUE[get_validation_queue]
    QUEUE --> PAPERS[Papers to validate]

    PAPERS --> LOOP[For each paper]
    LOOP --> HAS_DOI{Has DOI?}

    HAS_DOI -->|Yes| DOI_VAL[validate_paper - DOI lookup]
    HAS_DOI -->|No| TITLE_VAL[validate_paper - title search]

    DOI_VAL --> RESULT{Result}
    TITLE_VAL --> RESULT

    RESULT -->|verified| DONE[Mark validated]
    RESULT -->|not_found| FLAG[Flag for review]
    RESULT -->|error| RETRY[Log, retry later]

    DONE --> NEXT{More papers?}
    FLAG --> NEXT
    RETRY --> NEXT
    NEXT -->|Yes| LOOP
    NEXT -->|No| REPORT[Validation report]
```

**Confidence thresholds**:
- `>= 0.85`: Verified - high confidence match
- `0.5 - 0.85`: Possible match - manual review
- `< 0.5`: Not found - may be incorrect metadata

---

## 6. PDF Acquisition Strategies

```mermaid
flowchart TD
    PAPER[Paper needs PDF] --> DOI{Has DOI?}

    DOI -->|Yes| OA[find_open_access_pdf]
    DOI -->|No| ARXIV{Has arXiv ID?}

    ARXIV -->|Yes| ARXIV_DL[Direct arXiv download]
    ARXIV -->|No| MANUAL[Manual acquisition needed]

    OA --> OA_RESULT{PDF source found?}

    OA_RESULT -->|Unpaywall OA| AUTO[acquire_paper_pdf]
    OA_RESULT -->|arXiv| ARXIV_DL
    OA_RESULT -->|Paywall| ACCESS{Institutional access?}
    OA_RESULT -->|Not found| MANUAL

    ACCESS -->|VPN available| VPN[acquire_paper_pdf use_vpn=true]
    ACCESS -->|Browser needed| QUEUE[queue_pdf_download]
    ACCESS -->|None| MANUAL

    AUTO --> EXTRACT[Extract text]
    ARXIV_DL --> EXTRACT
    VPN --> EXTRACT
    QUEUE --> LATER[Process later with browser]
```

**Acquisition methods**:
| Method | Tool | When to use |
|--------|------|-------------|
| Open Access | `acquire_paper_pdf(paper_id)` | Unpaywall finds OA version |
| arXiv | Auto with `import_from_external(arxiv_id)` | Has arXiv ID |
| VPN | `acquire_paper_pdf(paper_id, use_vpn=True)` | Connected to institutional VPN |
| Browser | `queue_pdf_download(paper_id)` | Need manual browser login |

---

## 7. Text Extraction

### Modern PDFs (Text-based)
- **Tool**: pdfplumber (default)
- **Process**: Page-by-page text extraction
- **Speed**: Fast (~1-2 seconds)

### Scanned PDFs (Image-based)
- **Detection**: Word count < 100 after pdfplumber
- **Tool**: Tesseract OCR (automatic fallback)
- **Process**: Convert to images → OCR each page
- **Speed**: Slow (~30-60 seconds per page)

```mermaid
flowchart TD
    PDF[PDF file] --> PLUMBER[pdfplumber extraction]
    PLUMBER --> COUNT{Word count > 100?}

    COUNT -->|Yes| SUCCESS[Text extraction complete]
    COUNT -->|No| SCANNED{Likely scanned PDF}

    SCANNED --> OCR[Tesseract OCR]
    OCR --> OCR_RESULT{OCR successful?}

    OCR_RESULT -->|Yes| SUCCESS
    OCR_RESULT -->|No - poor quality| WARN[Warn: low quality extraction]

    SUCCESS --> STORE[Store in paper.full_text]
    WARN --> STORE
```

---

## 8. Embedding & Indexing

After text is available, generate embeddings for search.

**Tool**: `embed_paper(paper_id)` or `process_embedding_queue(limit=50)`

```mermaid
flowchart TD
    PAPER[Paper with content] --> CHECK[get_embedding_status]
    CHECK --> NEEDS{Needs embedding?}

    NEEDS -->|Paper-level missing| PAPER_EMB[Generate title+abstract embedding]
    NEEDS -->|Chunk-level missing| CHUNK[Split into 512-token chunks]
    NEEDS -->|Both| BOTH[Generate both]
    NEEDS -->|None| DONE[Already indexed]

    PAPER_EMB --> STORE_P[Store in ChromaDB 'papers']
    CHUNK --> CHUNK_EMB[Generate chunk embeddings]
    CHUNK_EMB --> STORE_C[Store in ChromaDB 'chunks']
    BOTH --> STORE_P
    BOTH --> CHUNK

    STORE_P --> FTS[FTS5 auto-updated via triggers]
    STORE_C --> FTS
    FTS --> SEARCHABLE[Paper fully searchable]
```

**Two embedding levels**:
| Level | Input | Use case |
|-------|-------|----------|
| Paper-level | Title + abstract | Fast paper discovery |
| Chunk-level | Full text chunks | Deep content search |

---

## 9. Duplicate Detection

Three methods available via `find_duplicates()`:

```mermaid
flowchart TD
    NEW[New paper] --> DOI{Has DOI?}

    DOI -->|Yes| DOI_CHECK[find_duplicates check by DOI]
    DOI_CHECK --> DOI_MATCH{Exact match?}
    DOI_MATCH -->|Yes| EXACT[Exact duplicate - return existing]
    DOI_MATCH -->|No| CONTINUE

    DOI -->|No| CONTINUE[Continue other checks]

    CONTINUE --> PDF{Has PDF?}
    PDF -->|Yes| HASH[find_duplicates method=hash]
    HASH --> HASH_MATCH{SHA256 match?}
    HASH_MATCH -->|Yes| EXACT
    HASH_MATCH -->|No| TITLE_CHECK

    PDF -->|No| TITLE_CHECK[find_duplicates method=title threshold=0.85]
    TITLE_CHECK --> TITLE_MATCH{Title similarity > 85%?}
    TITLE_MATCH -->|Yes| LIKELY[Likely duplicate - confirm with user]
    TITLE_MATCH -->|No| NEW_PAPER[Not a duplicate]
```

| Method | Confidence | Tool call |
|--------|------------|-----------|
| DOI match | 100% | `find_duplicates(method="doi")` |
| File hash | 100% | `find_duplicates(method="hash")` |
| Title similarity | Variable | `find_duplicates(method="title", threshold=0.85)` |

---

## 10. Data Quality Checks

### Required fields by tier:

| Tier | Required fields |
|------|-----------------|
| Minimal | `title` |
| Basic | + `authors`, `year` |
| Standard | + `doi` OR `arxiv_id`, `abstract` |
| Indexed | + embeddings in ChromaDB |
| Complete | + `full_text`, `validation_status="verified"` |

### Quality issues to watch:
- **Missing abstract**: Run `enrich_paper()` to fetch
- **No PDF**: Check `find_open_access_pdf()`, queue if paywall
- **Unvalidated**: Run `validate_paper()` to verify
- **No embeddings**: Run `embed_paper()` after text available

---

## 11. Completeness Definition

A paper is **complete** when:

```mermaid
flowchart TD
    PAPER[Paper] --> META{Core metadata?}
    META -->|Missing| ENRICH[enrich_paper]
    META -->|Complete| VALID{Validated?}

    ENRICH --> META

    VALID -->|No| VALIDATE[validate_paper]
    VALID -->|Yes| PDF{Has PDF?}

    VALIDATE --> VALID_RESULT{Verified?}
    VALID_RESULT -->|Yes| PDF
    VALID_RESULT -->|No| FLAG[Flag for review]

    PDF -->|No| ACQUIRE[acquire_paper_pdf]
    PDF -->|Yes| TEXT{Full text?}

    ACQUIRE --> PDF_RESULT{Acquired?}
    PDF_RESULT -->|Yes| TEXT
    PDF_RESULT -->|No| PARTIAL[Partial - no PDF available]

    TEXT -->|No| EXTRACT[Text extraction needed]
    TEXT -->|Yes| EMB{Embeddings?}

    EXTRACT --> TEXT

    EMB -->|No| EMBED[embed_paper]
    EMB -->|Yes| COMPLETE[PAPER COMPLETE]

    EMBED --> COMPLETE
```

**Completeness checklist**:
- [ ] Title, authors, year present
- [ ] DOI or arXiv ID assigned
- [ ] Abstract available
- [ ] Validated against external DB
- [ ] PDF acquired (if available)
- [ ] Full text extracted
- [ ] Embeddings generated

---

## 12. Error Handling Guide

| Error | Cause | Resolution |
|-------|-------|------------|
| `PAPER_NOT_FOUND` | Invalid paper_id | Verify with `list_papers()` |
| `DUPLICATE_DOI` | Paper already exists | Return existing paper_id |
| `EXTERNAL_API_ERROR` | API rate limit or down | Wait and retry, or try alternative source |
| `PDF_DOWNLOAD_FAILED` | Paywall or network issue | Queue for browser download |
| `TEXT_EXTRACTION_FAILED` | Corrupt PDF or scanned | Try OCR, report if still fails |
| `EMBEDDING_ERROR` | ChromaDB unavailable | Check `get_search_status()` |
| `VALIDATION_ERROR` | Missing required field | Check what's missing, enrich first |

### Recovery workflows:

**API rate limited**:
```
1. Wait 60 seconds
2. Retry with different source (CrossRef → OpenAlex → Semantic Scholar)
3. If all fail, log and continue without that data
```

**PDF not accessible**:
```
1. Check find_open_access_pdf() for alternatives
2. Try queue_pdf_download() for browser acquisition
3. If no options, continue without PDF (abstract-only indexing)
```

**Validation failed**:
```
1. Check if DOI is correct format
2. Try title-based validation
3. If still fails, flag for manual review
```
