# Consolidated Tools - Real-Life Testing Guide

This document provides step-by-step testing instructions for the consolidated MCP tools.
Each test uses real data from the literature database.

## Prerequisites

Before testing, verify the system is working:

```bash
# Run test suite
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q

# Count tools (should be 59)
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -c "
import asyncio
from mcp_server.tools import *
modules = [papers, search, extraction, discovery, citation_network,
           citations, collections, notes, pdf, browser_pdf,
           import_export, project, validation, zotero]
async def count():
    return sum([len(await m.list_tools()) for m in modules])
print(f'Total: {asyncio.run(count())} tools')
"
```

---

## 1. Import/Export Tools (import_export.py)

### Test 1.1: import_paper (source=wizard) - Smart Import with DOI

**Tool call:**
```json
{
  "name": "import_paper",
  "arguments": {
    "source": "wizard",
    "doi": "10.1021/acs.chemrev.0c00732"
  }
}
```

**Expected behavior:**
1. Fetches metadata from CrossRef/OpenAlex/Semantic Scholar
2. Checks for duplicate papers by DOI and title similarity
3. If new, adds paper to database with metadata provenance tracking
4. Returns paper_id, metadata_source, confidence score

**Verify:**
- Paper appears in `list_papers` with correct title/authors
- `metadata_source` field shows which API provided data

---

### Test 1.2: import_paper (source=wizard) - Duplicate Detection

**Tool call:**
```json
{
  "name": "import_paper",
  "arguments": {
    "source": "wizard",
    "title": "Atomic Layer Deposition: An Overview",
    "authors": "George"
  }
}
```

**Expected behavior:**
1. Searches for existing papers with similar titles
2. If duplicate found, returns status="duplicate" with existing_paper_id
3. Reports match_type (doi, title_exact, title_fuzzy) and similarity score

**Verify:**
- Returns duplicate status if paper exists
- Can override with `skip_duplicate_check: true`

---

### Test 1.3: import_paper (source=bibtex) - BibTeX Import

**Tool call:**
```json
{
  "name": "import_paper",
  "arguments": {
    "source": "bibtex",
    "bibtex_content": "@article{smith2023ald,\n  title={Recent Advances in ALD},\n  author={Smith, John and Doe, Jane},\n  journal={J. Vac. Sci. Technol.},\n  year={2023},\n  volume={41},\n  pages={012401},\n  doi={10.1116/6.0002303}\n}",
    "tags": ["imported", "ald"]
  }
}
```

**Expected behavior:**
1. Parses BibTeX entry
2. Creates paper with extracted fields
3. Applies specified tags

**Verify:**
- Paper created with correct metadata
- Tags applied
- Returns import summary (imported/skipped/failed counts)

---

### Test 1.4: import_paper (source=external) - Simple External Lookup

**Tool call:**
```json
{
  "name": "import_paper",
  "arguments": {
    "source": "external",
    "arxiv_id": "2301.12345",
    "tags": ["arxiv", "ml"]
  }
}
```

**Expected behavior:**
1. Looks up paper via arXiv API
2. Imports without duplicate checking (simpler flow)
3. Returns paper metadata

**Verify:**
- Paper imported from arXiv
- Abstract and metadata populated

---

### Test 1.5: export (source=papers) - Export by Paper IDs

**Tool call:**
```json
{
  "name": "export",
  "arguments": {
    "source": "papers",
    "paper_ids": [1, 2, 3],
    "format": "bibtex",
    "include_abstract": true
  }
}
```

**Expected behavior:**
1. Retrieves specified papers
2. Generates BibTeX entries with abstracts
3. Returns formatted output

**Verify:**
- Valid BibTeX syntax
- All requested papers included
- Abstracts present in output

---

### Test 1.6: export (source=collection) - Export Collection

**Tool call:**
```json
{
  "name": "export",
  "arguments": {
    "source": "collection",
    "collection_id": 1,
    "format": "json",
    "include_subcollections": true
  }
}
```

**Expected behavior:**
1. Gets all papers in collection
2. Optionally includes subcollection papers
3. Returns JSON with full paper metadata

**Verify:**
- All collection papers exported
- Subcollection papers included if flag set
- JSON is valid and complete

---

## 2. Discovery Tools (discovery.py)

### Test 2.1: semantic_find (input_type=paper) - Find Similar Papers

**First, get a paper ID:**
```json
{
  "name": "list_papers",
  "arguments": {"limit": 1}
}
```

**Then find similar:**
```json
{
  "name": "semantic_find",
  "arguments": {
    "input_type": "paper",
    "paper_id": 42,
    "limit": 5,
    "include_summary": true
  }
}
```

**Expected behavior:**
1. Gets embeddings for paper 42
2. Finds semantically similar papers via ChromaDB
3. Returns ranked list with similarity scores
4. Includes one_sentence_summary if available

**Verify:**
- Results are topically related to source paper
- Similarity scores decrease down the list
- Summaries included when requested

---

### Test 2.2: semantic_find (input_type=text) - Match Description

**Tool call:**
```json
{
  "name": "semantic_find",
  "arguments": {
    "input_type": "text",
    "text": "plasma enhanced atomic layer deposition of silicon nitride for semiconductor applications",
    "limit": 5,
    "min_similarity": 0.4
  }
}
```

**Expected behavior:**
1. Generates embedding for query text
2. Searches vector store for matching papers
3. Returns papers relevant to the description

**Verify:**
- Results match the topic (PEALD, SiN, semiconductors)
- All results above min_similarity threshold

---

### Test 2.3: semantic_find (input_type=citation) - Suggest Citations

**Tool call:**
```json
{
  "name": "semantic_find",
  "arguments": {
    "input_type": "citation",
    "text": "ALD enables conformal coatings with atomic-level precision, making it ideal for high-aspect-ratio structures",
    "limit": 3,
    "include_bibtex": true,
    "prefer_type": "review"
  }
}
```

**Expected behavior:**
1. Finds papers relevant to the claim
2. Enriches results with extraction data (summary, paper_type, key_findings)
3. Prioritizes reviews when `prefer_type="review"` (good for background citations)
4. Includes BibTeX for easy insertion

**Response fields:**
- `summary`: One-sentence summary explaining paper relevance
- `paper_type`: review, research_article, conference, etc.
- `topics`: Key topics covered
- `key_findings`: Specific findings that support the claim
- `citation_hint`: Flags like "Good for background/overview citations"
- `bibtex`, `citation_key`: When include_bibtex=true

**Verify:**
- Papers support the claim being made
- Reviews appear first when prefer_type="review"
- BibTeX entries are valid and complete
- Summaries help understand why each paper is suggested

**Type preference options:**
- `"any"` (default): Best semantic matches regardless of type
- `"review"`: Prioritize reviews/meta-analyses (good for background/intro)
- `"primary"`: Prioritize research articles (good for specific claims)

---

### Test 2.4: manage_embeddings (action=status) - Check Coverage

**Tool call:**
```json
{
  "name": "manage_embeddings",
  "arguments": {
    "action": "status",
    "include_ids": true
  }
}
```

**Expected behavior:**
1. Reports embedding coverage statistics
2. Shows papers with/without embeddings
3. Lists paper IDs needing embeddings if requested

**Verify:**
- Coverage percentage is reasonable
- paper_ids list is accurate
- Model name is correct

---

### Test 2.5: manage_embeddings (action=process) - Batch Generate

**Tool call:**
```json
{
  "name": "manage_embeddings",
  "arguments": {
    "action": "process",
    "limit": 5,
    "include_paper_embeddings": true,
    "include_chunk_embeddings": true
  }
}
```

**Expected behavior:**
1. Processes up to 5 papers without embeddings
2. Generates paper-level and chunk-level embeddings
3. Stores in ChromaDB

**Verify:**
- Processing count matches request
- No errors in output
- Running `action=status` shows increased coverage

---

### Test 2.6: manage_embeddings (action=embed) - Single Paper

**Tool call:**
```json
{
  "name": "manage_embeddings",
  "arguments": {
    "action": "embed",
    "paper_id": 42
  }
}
```

**Expected behavior:**
1. Generates embeddings for specific paper
2. Works immediately (no queue)

**Verify:**
- Paper now searchable via semantic search
- Embedding appears in ChromaDB

---

## 3. Citation Network Tools (citation_network.py)

### Test 3.1: get_citations (direction=incoming) - Who Cites This

**Tool call:**
```json
{
  "name": "get_citations",
  "arguments": {
    "direction": "incoming",
    "paper_id": 1,
    "limit": 10
  }
}
```

**Expected behavior:**
1. Looks up paper DOI from database
2. Queries OpenAlex/Semantic Scholar for citing papers
3. Checks if citing papers are in local library
4. Returns list with in_library flags

**Verify:**
- Citation count is reasonable
- `source` field shows API used (openalex/semantic_scholar)
- `in_library` and `library_id` populated correctly

---

### Test 3.2: get_citations (direction=outgoing) - Bibliography

**Tool call:**
```json
{
  "name": "get_citations",
  "arguments": {
    "direction": "outgoing",
    "doi": "10.1021/acs.chemrev.0c00732",
    "limit": 20
  }
}
```

**Expected behavior:**
1. Queries external APIs for paper references
2. Falls back to PDF extraction if available
3. Returns bibliography with in_library status

**Verify:**
- References match actual paper bibliography
- In-library papers correctly identified
- Falls back to pdf_extraction if APIs fail

---

### Test 3.3: get_citations with title lookup

**Tool call:**
```json
{
  "name": "get_citations",
  "arguments": {
    "direction": "incoming",
    "title": "Atomic Layer Deposition: An Overview",
    "limit": 10
  }
}
```

**Expected behavior:**
1. Looks up paper by title via external APIs
2. Returns citations for matched paper

**Verify:**
- Correct paper found by title
- Citations returned as expected

---

## 4. Zotero Tools (zotero.py)

> **Note:** Zotero tests require API key configured in `data/config/credentials.yml`

### Test 4.1: zotero_status - Basic Status

**Tool call:**
```json
{
  "name": "zotero_status",
  "arguments": {}
}
```

**Expected behavior:**
1. Returns sync status overview
2. Shows linked papers count, database-only count

**Verify:**
- Status information is accurate
- No errors if API not configured (graceful degradation)

---

### Test 4.2: zotero_status (check_connection=true) - Connection Check

**Tool call:**
```json
{
  "name": "zotero_status",
  "arguments": {
    "check_connection": true
  }
}
```

**Expected behavior:**
1. Checks if Zotero app is running locally
2. Verifies web API configuration
3. Reports can_sync and can_push capabilities

**Verify:**
- Local app status accurate
- Web API status accurate
- Help message shown if not configured

---

### Test 4.3: zotero_sync (direction=pull) - Pull from Zotero

**Tool call:**
```json
{
  "name": "zotero_sync",
  "arguments": {
    "direction": "pull"
  }
}
```

**Expected behavior:**
1. Fetches new/updated items from Zotero
2. Adds/updates papers in database
3. Reports papers_added and papers_updated counts

**Verify:**
- New Zotero items appear in database
- Existing items updated if changed
- Zotero item keys linked to papers

---

### Test 4.4: zotero_sync (direction=push) - Push to Zotero

**Tool call:**
```json
{
  "name": "zotero_sync",
  "arguments": {
    "direction": "push",
    "create_new_items": false
  }
}
```

**Expected behavior:**
1. Enriches existing Zotero items with database metadata
2. Only fills empty fields (non-destructive)
3. Reports updated/skipped counts

**Verify:**
- Zotero items enriched with abstracts, DOIs
- No data overwritten
- Mode shows "enrich_only"

---

### Test 4.5: zotero_sync (direction=push_paper) - Single Paper

**Tool call:**
```json
{
  "name": "zotero_sync",
  "arguments": {
    "direction": "push_paper",
    "paper_id": 42,
    "create_if_missing": true
  }
}
```

**Expected behavior:**
1. Pushes single paper to Zotero
2. Creates new item if not exists (when flag set)
3. Links paper to Zotero item

**Verify:**
- Paper appears in Zotero library
- Metadata is complete
- Link stored in database

---

### Test 4.6: zotero_sync (direction=push_pdf) - Upload PDF

**Tool call:**
```json
{
  "name": "zotero_sync",
  "arguments": {
    "direction": "push_pdf",
    "paper_id": 42
  }
}
```

**Expected behavior:**
1. Uploads PDF attachment to Zotero item
2. Paper must already exist in Zotero

**Verify:**
- PDF appears as attachment in Zotero
- File is accessible in Zotero

---

## 5. End-to-End Workflow Tests

### Workflow A: Import → Extract → Search

1. **Import a paper:**
   ```json
   {"name": "import_paper", "arguments": {"source": "wizard", "doi": "10.1038/s41586-023-06735-9"}}
   ```

2. **Generate embeddings:**
   ```json
   {"name": "manage_embeddings", "arguments": {"action": "embed", "paper_id": <new_id>}}
   ```

3. **Find similar papers:**
   ```json
   {"name": "semantic_find", "arguments": {"input_type": "paper", "paper_id": <new_id>, "limit": 5}}
   ```

**Verify:** New paper is searchable and finds relevant matches.

---

### Workflow B: Citation Discovery

1. **Find highly cited paper:**
   ```json
   {"name": "list_papers", "arguments": {"limit": 10}}
   ```

2. **Get incoming citations:**
   ```json
   {"name": "get_citations", "arguments": {"direction": "incoming", "paper_id": <id>, "limit": 20}}
   ```

3. **Get outgoing references:**
   ```json
   {"name": "get_citations", "arguments": {"direction": "outgoing", "paper_id": <id>, "limit": 20}}
   ```

**Verify:** Citation network is populated; can discover related work.

---

### Workflow C: Export for Manuscript

1. **Search for relevant papers:**
   ```json
   {"name": "search", "arguments": {"query": "atomic layer deposition conformal", "limit": 10}}
   ```

2. **Get summaries:**
   ```json
   {"name": "get_papers_summary", "arguments": {"paper_ids": [1, 2, 3, 4, 5]}}
   ```

3. **Export as BibTeX:**
   ```json
   {"name": "export", "arguments": {"source": "papers", "paper_ids": [1, 2, 3], "format": "bibtex"}}
   ```

**Verify:** Complete workflow from search to citation export.

---

## Troubleshooting

### Common Issues

1. **"Zotero web API not configured"**
   - Add API key to `data/config/credentials.yml`
   - Format: `zotero_api_key: "your_key_here"`

2. **"No embeddings found"**
   - Run `manage_embeddings(action=status)` to check coverage
   - Process queue with `manage_embeddings(action=process, limit=100)`

3. **"Paper not found"**
   - Verify paper_id exists with `list_papers`
   - Check if paper has DOI for external lookups

4. **Duplicate detection too aggressive**
   - Use `skip_duplicate_check: true` for known new papers
   - Check existing papers with `search(query=<title>, mode=exact)`

---

## Test Checklist

| Test | Tool | Status |
|------|------|--------|
| 1.1 | import_paper (wizard/doi) | ☐ |
| 1.2 | import_paper (wizard/duplicate) | ☐ |
| 1.3 | import_paper (bibtex) | ☐ |
| 1.4 | import_paper (external/arxiv) | ☐ |
| 1.5 | export (papers) | ☐ |
| 1.6 | export (collection) | ☐ |
| 2.1 | semantic_find (paper) | ☐ |
| 2.2 | semantic_find (text) | ☐ |
| 2.3 | semantic_find (citation) | ☐ |
| 2.4 | manage_embeddings (status) | ☐ |
| 2.5 | manage_embeddings (process) | ☐ |
| 2.6 | manage_embeddings (embed) | ☐ |
| 3.1 | get_citations (incoming) | ☐ |
| 3.2 | get_citations (outgoing) | ☐ |
| 3.3 | get_citations (title lookup) | ☐ |
| 4.1 | zotero_status | ☐ |
| 4.2 | zotero_status (connection) | ☐ |
| 4.3 | zotero_sync (pull) | ☐ |
| 4.4 | zotero_sync (push) | ☐ |
| 4.5 | zotero_sync (push_paper) | ☐ |
| 4.6 | zotero_sync (push_pdf) | ☐ |
| A | Workflow: Import→Extract→Search | ☐ |
| B | Workflow: Citation Discovery | ☐ |
| C | Workflow: Export for Manuscript | ☐ |
