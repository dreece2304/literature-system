# Literature MCP - Tool Reference

Quick reference for all MCP tools with exact parameter signatures.

---

## Papers

### list_papers
List papers with optional filtering and pagination.

```
Parameters:
  limit: int = 20          # Max papers to return (max: 500)
  offset: int = 0          # Papers to skip for pagination
  author: str | None       # Filter by author name (partial match)
  year: int | None         # Filter by publication year
  tag: str | None          # Filter by tag name
  read_status: str | None  # "unread", "reading", "read"

Returns: {success, data: [{id, title, authors, year, read_status, rating}], pagination}
```

### get_paper
Get detailed information about a specific paper.

```
Parameters:
  paper_id: int  # Required

Returns: {success, data: {id, title, abstract, authors, tags, year, doi, ...}}
```

### add_paper
Add a new paper to the database.

```
Parameters:
  title: str               # Required
  authors: list[str]       # List of author names
  year: int | None
  doi: str | None
  arxiv_id: str | None
  abstract: str | None
  journal: str | None
  tags: list[str]          # Tags to apply

Returns: {success, data: paper}
```

### update_paper
Update an existing paper's metadata.

```
Parameters:
  paper_id: int            # Required
  read_status: str | None  # "unread", "reading", "read"
  rating: int | None       # 1-5
  tags: list[str] | None   # Replace all tags

Returns: {success, data: paper}
```

### get_paper_content
Get full paper content for AI analysis.

```
Parameters:
  paper_id: int              # Required
  include_full_text: bool = true
  max_chars: int = 50000     # Limit full text length
  offset: int = 0            # Start position for pagination

Returns: {success, data: {title, abstract, full_text, word_count, has_more}}
```

### store_extraction
Store AI-extracted content for a paper (basic and extended fields).

```
Parameters:
  paper_id: int                        # Required
  paper_type: str | None               # "research_article", "review", etc.
  topics: list[str] | None
  one_sentence_summary: str | None
  key_findings: list[str] | None
  methodology_summary: str | None
  # Extended fields (stored in structured_data):
  research_context: dict | None        # {problem_addressed, novelty, limitations, significance}
  discussion_summary: str | None
  future_directions: list[str] | None
  quantitative_results: list[dict] | None   # [{metric, value, unit, conditions}]
  citable_claims: list[str] | None
  techniques_used: list[dict] | None        # [{technique, purpose, specifics}]
  experimental_conditions: dict | None      # {materials, temperature_range, etc.}
  prior_work_comparison: list[dict] | None  # [{reference_claim, this_work, improvement}]
  citation_contexts: dict | None            # {introduction, methods, results, discussion}

Returns: {success, data: {paper_id, extended_fields_stored?}}
```

### batch_update_papers
Bulk update tags, read_status, or rating for multiple papers.

```
Parameters:
  paper_ids: list[int]     # Required
  read_status: str | None
  rating: int | None
  tags_to_add: list[str]
  tags_to_remove: list[str]

Returns: {success, data: {updated_count}}
```

### batch_delete_papers
Bulk delete papers (requires confirmation).

```
Parameters:
  paper_ids: list[int]  # Required
  confirm: bool         # Required - Must be true

Returns: {success, data: {deleted_count}}
```

---

## Search

### search (Unified)
Primary search tool with multiple modes. Recommended for most searches.

```
Parameters:
  query: str                     # Required
  mode: str = "smart"            # "smart", "keyword", "semantic", "hybrid"
  limit: int = 20
  alpha: float = 0.65            # Semantic weight for hybrid mode (0-1)
  min_similarity: float = 0.35   # Minimum for semantic results
  search_level: str = "chunk"    # "chunk" (full-text) or "paper" (title+abstract)
  year_min: int | None
  year_max: int | None
  correct_spelling: bool = true  # Smart mode: auto-correct typos
  expand_acronyms: bool = true   # Smart mode: expand ALD, EUV, etc.
  add_synonyms: bool = false     # Smart mode: add scientific synonyms

Returns: {
  success,
  data: [{id, title, year, authors, score}],
  count,
  mode,
  diagnostics: {
    query_expanded?,           # For smart mode
    corrections?,              # Spelling corrections applied
    fts_available,
    semantic_available,
    keyword_results_count,
    semantic_results_count
  }
}
```

**Search Modes:**
- `smart` (default): Handles typos, expands acronyms, combines keyword + semantic
- `keyword`: FTS5 full-text search with BM25 ranking
- `semantic`: Embedding-based similarity search
- `hybrid`: Balanced keyword + semantic with RRF fusion

### search_by_author
Find all papers by a specific author.

```
Parameters:
  author_name: str   # Required (partial match supported)
  limit: int = 20

Returns: {success, data: papers[]}
```

### search_by_tag
Find all papers with a specific tag.

```
Parameters:
  tag: str              # Required (partial match by default)
  limit: int = 20
  exact_match: bool = false

Returns: {success, data: papers[]}
```

### get_search_status
Get search system health status and diagnostics.

```
Parameters:
  detailed: bool = false

Returns: {
  success,
  healthy: bool,
  keyword_search: "available" | "unavailable",
  semantic_search: "available" | "unavailable",
  papers_indexed: int,
  embedding_coverage: "85%",
  recommendations?: []  # If detailed=true
}
```

---

## Discovery

### semantic_find (Consolidated)
Unified semantic search with three modes: find similar papers, match text descriptions, or suggest citations.

```
Parameters:
  input_type: str          # Required: "paper", "text", or "citation"
  paper_id: int            # Required for input_type=paper
  text: str                # Required for input_type=text or citation
  limit: int = 10
  min_similarity: float = 0.5
  include_summary: bool = false   # Include extraction summaries
  include_bibtex: bool = false    # Include BibTeX (citation mode)
  prefer_type: str = "any"        # Citation mode: "any", "review", "primary"

Returns for input_type=paper|text:
  {success, results: [{id, title, score, summary?, paper_type?, topics?}]}

Returns for input_type=citation:
  {success, results: [{id, title, score, summary, paper_type, topics,
                       key_findings, citation_hint?, bibtex?, citation_key?}]}

Examples:
  # Find similar papers
  semantic_find(input_type="paper", paper_id=42, limit=5)

  # Match text description
  semantic_find(input_type="text", text="plasma ALD of silicon nitride")

  # Suggest citations (prefer reviews for background)
  semantic_find(input_type="citation", text="ALD enables conformal coatings",
                prefer_type="review", include_bibtex=true)
```

### manage_embeddings (Consolidated)
Embedding status, batch processing, or single paper embedding.

```
Parameters:
  action: str = "status"   # "status", "process", or "embed"
  paper_id: int            # Required for action=embed
  limit: int = 50          # Max papers for action=process
  include_ids: bool = false           # Include paper IDs needing embeddings
  include_paper_embeddings: bool = true
  include_chunk_embeddings: bool = true

Returns for action=status:
  {success, total_papers, paper_embeddings: {count, coverage_percent},
   chunk_embeddings: {count, coverage_percent}, paper_ids_needing_*?}

Returns for action=process|embed:
  {success, papers_processed, paper_embeddings_created, chunks_created}
```

### suggest_paper_tags
Suggest tags for a paper based on similar papers' tags.

```
Parameters:
  paper_id: int    # Required
  limit: int = 5

Returns: {success, data: {suggestions: [{tag, frequency}], based_on_papers}}
```

### get_reading_queue
Get reading queue of unread papers sorted by rating and date added.

```
Parameters:
  limit: int = 20
  min_rating: int | None   # Filter by minimum rating (1-5)
  tag: str | None          # Filter by tag

Returns: {success, data: {count, papers: [], filters}}
```

---

## PDF Management

### get_pdf_status
Check PDF status for papers.

```
Parameters:
  filter: str = "all"  # "all", "has_pdf", "needs_pdf"
  limit: int = 50

Returns: {success, data: [{paper_id, has_pdf, path?}]}
```

### acquire_paper_pdf
Attempt to download PDF for a paper.

```
Parameters:
  paper_id: int           # Required
  use_vpn: bool = false   # Try direct publisher URLs
  use_openurl: bool = false
  use_proxy: bool = false

Returns: {success, data: {path?, source?, error?}}
```

### find_open_access_pdf
Find open access PDF URLs.

```
Parameters:
  doi: str | None
  arxiv_id: str | None
  title: str | None

Returns: {success, data: {url?, source?}}
```

### find_duplicates
Find duplicate papers by file hash or title similarity.

```
Parameters:
  method: str = "title"         # "hash" or "title"
  threshold: float = 0.85       # Title similarity threshold

Returns: {success, data: duplicate_groups[]}
```

---

## PDF Processing & Extraction

### get_pdf_processing_status
Get status of PDF processing queue.

```
Parameters: none

Returns: {success, data: {
  total_papers, papers_with_pdf, papers_with_chunks,
  pending_processing, processing_errors
}}
```

### queue_pdf_processing
Queue a paper's PDF for text extraction and chunking.

```
Parameters:
  paper_id: int  # Required

Returns: {success, data: {queued}}
```

### process_pdf_queue
Process queued PDFs (extract text, create chunks).

```
Parameters:
  limit: int = 10

Returns: {success, data: {processed, errors}}
```

### extract_paper
Extract structured content from a paper using AI.

```
Parameters:
  paper_id: int              # Required
  backend: str = "auto"      # "ollama" or "auto"
  force: bool = false        # Re-extract even if exists

Returns: {success, data: {extraction}}
```

### prepare_extraction
Prepare paper content for Claude-powered extraction.

```
Parameters:
  paper_id: int             # Required
  tier: str = "quick"       # "quick" (abstract) or "deep" (full text)
  max_chars: int = 80000    # Deep tier only

Returns: {success, data: {paper_text, project_context, already_cited_in}}
```

### get_extraction_queue
Get papers needing AI extraction.

```
Parameters:
  limit: int = 20

Returns: {success, data: papers[]}
```

---

## Browser PDF Download (Windows)

### queue_pdf_download
Queue a PDF for download via browser automation.

```
Parameters:
  paper_id: int  # Required

Returns: {success, data: {queued}}
```

### queue_batch_pdf_download
Queue multiple papers for PDF download.

```
Parameters:
  paper_ids: list[int]  # Required

Returns: {success, data: {queued_count}}
```

### get_download_queue_status
Get status of the download queue.

```
Parameters:
  paper_id: int | None  # Check specific paper

Returns: {success, data: {pending, completed, failed, items?}}
```

### process_downloaded_pdfs
Process PDFs downloaded by browser fetcher.

```
Parameters:
  auto_match: bool = true  # Match by DOI in filename

Returns: {success, data: {processed, matched, errors}}
```

---

## Collections

### list_collections
```
Parameters:
  parent_id: int | None  # Filter to children
  all: bool = false      # List all ignoring hierarchy

Returns: {success, data: {count, collections: [{id, name, paper_count}]}}
```

### create_collection
```
Parameters:
  name: str               # Required
  description: str | None
  parent_id: int | None

Returns: {success, data: collection}
```

### add_papers_to_collection
```
Parameters:
  collection_id: int    # Required
  paper_ids: list[int]  # Required

Returns: {success, data: {added_count}}
```

### remove_papers_from_collection
```
Parameters:
  collection_id: int
  paper_ids: list[int]

Returns: {success, data: {removed_count}}
```

---

## Notes

### create_note
```
Parameters:
  paper_id: int              # Required
  content: str               # Required
  note_type: str = "comment" # "highlight", "comment", "summary"
  page_number: int | None

Returns: {success, data: note}
```

### get_paper_notes
```
Parameters:
  paper_id: int
  note_type: str | None

Returns: {success, data: notes[]}
```

---

## External APIs

### lookup_paper_metadata
Look up metadata from CrossRef, OpenAlex, Semantic Scholar, arXiv.

```
Parameters:
  doi: str | None
  title: str | None
  authors: str | None
  year: int | None

Returns: {success, data: {source, metadata}}
```

### search_external_papers
Search external databases for papers not in library.

```
Parameters:
  query: str
  sources: list[str]   # ["crossref", "openalex", "semantic_scholar", "arxiv"]
  limit: int = 5

Returns: {success, data: {source: papers[]}}
```

### enrich_paper
Auto-fill missing metadata from external sources.

```
Parameters:
  paper_id: int | None
  doi: str | None
  title: str | None

Returns: {success, data: enriched_paper}
```

### get_citation_count
Get citation count from Semantic Scholar.

```
Parameters:
  doi: str | None
  title: str | None

Returns: {success, data: {citation_count, source}}
```

---

## Citation Network

### get_paper_citations
Get papers that cite a given paper (via Semantic Scholar).

```
Parameters:
  paper_id: int | None
  doi: str | None
  title: str | None
  limit: int = 50

Returns: {success, data: {citations: [], total_count}}
```

### get_paper_references
Get papers that a given paper references.

```
Parameters:
  paper_id: int | None
  doi: str | None
  title: str | None
  limit: int = 50

Returns: {success, data: {references: [], total_count}}
```

### find_common_references
Find papers that share common references.

```
Parameters:
  paper_id: int         # Required
  limit: int = 10
  min_shared: int = 2   # Minimum shared references

Returns: {success, data: [{paper, shared_count, shared_refs}]}
```

### build_citation_graph
Build citation graph for visualization.

```
Parameters:
  paper_ids: list[int]      # Required
  depth: int = 1            # 1-2
  include_external: bool = false

Returns: {success, data: {nodes: [], edges: []}}
```

---

## Import/Export

### import_bibtex
```
Parameters:
  bibtex_content: str        # Required
  collection_id: int | None
  tags: list[str]

Returns: {success, data: {imported, skipped, errors}}
```

### import_from_external
```
Parameters:
  doi: str | None
  arxiv_id: str | None
  title: str | None
  collection_id: int | None
  tags: list[str]

Returns: {success, data: paper}
```

### export_papers
```
Parameters:
  paper_ids: list[int] | None
  format: str = "bibtex"      # "bibtex", "json", "csv"
  include_abstract: bool = true
  include_notes: bool = false
  limit: int = 50
  offset: int = 0

Returns: {success, data: export_string, pagination}
```

### export_collection
```
Parameters:
  collection_id: int
  format: str = "bibtex"
  include_subcollections: bool = false

Returns: {success, data: export_string}
```

---

## Project & Citations

### citation_health_check
Comprehensive check: orphans, missing, incomplete, duplicates.

```
Parameters:
  bib_path: str  # Required
  tex_path: str  # Required

Returns: {success, data: {orphans, missing, incomplete, duplicates}}
```

### scan_tex_citations
Scan TeX files for all \cite{} commands.

```
Parameters:
  file_path: str         # Required
  recursive: bool = true

Returns: {success, data: {citations: [{key, file, line}]}}
```

### sync_bib_from_database
Update bib entries with database metadata.

```
Parameters:
  bib_path: str
  dry_run: bool = true

Returns: {success, data: {updates: [], would_update?}}
```

---

## Validation

### validate_paper
Validate paper against external databases.

```
Parameters:
  paper_id: int  # Required

Returns: {success, data: {verified, confidence, issues?}}
```

### validate_papers_batch
```
Parameters:
  paper_ids: list[int] | None  # None = use queue
  limit: int = 20

Returns: {success, data: {verified, failed, errors}}
```

### get_validation_queue
Get papers needing validation.

```
Parameters:
  limit: int = 20
  prioritize_with_doi: bool = true

Returns: {success, data: papers[]}
```

---

## Zotero

### check_zotero_connection
```
Returns: {success, data: {local_available, web_api_available}}
```

### sync_from_zotero
```
Returns: {success, data: {added, updated, total}}
```

### sync_to_zotero
```
Parameters:
  create_new_items: bool = false

Returns: {success, data: {updated, created?, errors}}
```

---

## Embeddings

### get_embedding_status
Get embedding coverage status.

```
Parameters:
  include_ids: bool = false

Returns: {success, data: {
  total_papers, papers_with_embeddings,
  papers_needing_embeddings, coverage_percent
}}
```

### process_embedding_queue
Generate embeddings for papers missing them.

```
Parameters:
  limit: int = 50
  include_paper_embeddings: bool = true
  include_chunk_embeddings: bool = true

Returns: {success, data: {processed, errors}}
```

### embed_paper
Generate embeddings for a single paper.

```
Parameters:
  paper_id: int
  include_paper_embedding: bool = true
  include_chunk_embedding: bool = true

Returns: {success}
```

---

## Response Format

All tools return:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

List operations include pagination:

```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "total": 418,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```
