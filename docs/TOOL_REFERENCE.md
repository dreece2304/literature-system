# Literature MCP - Tool Reference

Quick reference for all MCP tools with exact parameter signatures.

Generated from the actual tool definitions in `src/mcp_server/tools/` (66 tools across 13 modules).
To regenerate the raw list, iterate `TOOL_MODULES` in `src/mcp_server/server.py` and call each
module's `list_tools()`.

Note: `browser_pdf.py` exposes no tools — it holds internal helpers used by `pdf.py`.

---

## Papers (`papers.py`)

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
```

### get_paper
Get detailed information about a specific paper.

```
Parameters:
  paper_id: int  # Required
```

### add_paper
Add a new paper to the database.

```
Parameters:
  title: str               # Required
  abstract: str | None
  year: int | None
  doi: str | None
  arxiv_id: str | None
  authors: list[str]       # List of author names
  tags: list[str]          # Tags to apply
  journal: str | None
```

### update_paper
Update an existing paper's metadata (can also attach a local PDF).

```
Parameters:
  paper_id: int            # Required
  title: str | None
  abstract: str | None
  year: int | None
  doi: str | None
  rating: int | None       # 1-5
  read_status: str | None  # "unread", "reading", "read"
  tags: list[str] | None   # Replace all tags
  file_path: str | None    # Local path to PDF file to attach
```

### get_paper_content
Get paper content + LLM extraction. Set `include_full_text=true` only if extraction missing.

```
Parameters:
  paper_id: int                    # Required
  include_full_text: bool = false  # Default false for token efficiency
  max_chars: int = 50000           # Max chars for full text (0 = unlimited)
  offset: int = 0                  # Start position in full text for pagination
  include_verification: bool = false  # Include verification score for the extraction
```

### store_extraction
Store AI-extracted content (type, topics, summary, findings, methodology, etc.).

```
Parameters:
  paper_id: int                        # Required
  paper_type: str | None               # "research_article", "review", etc.
  topics: list[str] | None
  one_sentence_summary: str | None
  key_findings: list[str] | None
  methodology_summary: str | None
  discussion_summary: str | None
  future_directions: list[str] | None
  quantitative_results: list[dict] | None   # [{metric, value, unit, conditions}]
  citable_claims: list[str] | None
  techniques_used: list[dict] | None        # [{technique, purpose, specifics}]
  experimental_conditions: dict | None      # {materials, temperature_range, ...}
  prior_work_comparison: list[dict] | None  # [{reference_claim, this_work, improvement}]
  research_context: dict | None             # {problem_addressed, novelty, limitations, significance}
  citation_contexts: dict | None            # {introduction, methods, results, discussion}
  project_relevance: dict | None            # {project_name: {relevance, reason, primary_use}}
```

### batch_update_papers
Bulk update tags, read_status, or rating for multiple papers.

```
Parameters:
  paper_ids: list[int]     # Required
  tags_to_add: list[str]
  tags_to_remove: list[str]
  read_status: str | None
  rating: int | None
```

### batch_delete_papers
Bulk delete papers (requires confirmation).

```
Parameters:
  paper_ids: list[int]  # Required
  confirm: bool         # Required - must be true
```

### get_papers_summary
Batch fetch summaries (one_sentence_summary, paper_type, topics) for paper IDs.

```
Parameters:
  paper_ids: list[int]           # Required
  include_abstract: bool = false
```

---

## Search (`search.py`)

### search
Search papers. Modes: smart (default), keyword (FTS5), semantic, hybrid, exact.

```
Parameters:
  query: str                     # Required
  limit: int = 20
  mode: str = "smart"            # "smart", "keyword", "semantic", "hybrid", "exact"
  correct_spelling: bool = true  # Smart mode: auto-correct typos
  expand_acronyms: bool = true   # Smart mode: expand ALD, EUV, etc.
  add_synonyms: bool = false     # Smart mode: add synonyms (can increase noise)
  alpha: float = 0.65            # Semantic weight for hybrid mode (0-1)
  search_level: str = "chunk"    # "chunk" (full-text) or "paper" (title+abstract)
  min_similarity: float = 0.35   # Minimum similarity score (0-1)
  rerank: bool | None            # Cross-encoder re-ranking (default: RERANKER_ENABLED setting)
  year_min: int | None
  year_max: int | None
  include_summary: bool = false  # Include one_sentence_summary and paper_type
```

**Search Modes:**
- `smart` (default): Handles typos, expands acronyms, combines keyword + semantic
- `keyword`: FTS5 full-text search with BM25 ranking
- `semantic`: Embedding-based similarity search
- `hybrid`: Balanced keyword + semantic with RRF fusion
- `exact`: Fast known-paper lookup

### get_search_status
Search system health (FTS5, ChromaDB, embedding coverage).

```
Parameters:
  detailed: bool = false  # If true, return full diagnostics
```

---

## External APIs (`external.py`)

### lookup_paper_metadata
Lookup metadata from CrossRef/OpenAlex/Semantic Scholar/arXiv.

```
Parameters:
  title: str | None
  doi: str | None      # Most reliable
  authors: str | None
  year: int | None
```

### find_open_access_pdf
Find open access PDF via Unpaywall/arXiv/publishers.

```
Parameters:
  doi: str | None       # Required for best results
  title: str | None     # Fallback if no DOI
  arxiv_id: str | None
```

### enrich_paper
Enrich paper with missing metadata (abstract, DOI, citations, PDF).

```
Parameters:
  paper_id: int | None  # Paper ID in the local database
  title: str | None     # If not using paper_id
  doi: str | None
```

### search_external_papers
Search CrossRef/OpenAlex/Semantic Scholar/arXiv for new papers.

```
Parameters:
  query: str            # Required
  limit: int = 5        # Max results per source
  sources: list[str]    # Default: all
```

### get_citation_count
Get citation count for a paper from Semantic Scholar.

```
Parameters:
  doi: str | None
  title: str | None  # Fallback
```

---

## Citations (`citations.py`)

### manuscript_tools
Manuscript analysis. Actions: scan (parse structure), check (citations vs library).

```
Parameters:
  action: str = "scan"           # "scan" or "check"
  file_path: str | None          # For scan: path to .tex/.md file
  content: str | None            # For scan: manuscript content (if no file_path)
  format: str = "latex"          # For scan: "latex" or "markdown"
  manuscript_citations: list | None  # For check: citation keys from manuscript
  library_papers: list | None        # For check: papers from library
```

### format_citation
Citation formatting. Actions: bibtex, suggest_key, validate, bibliography.

```
Parameters:
  action: str = "bibtex"      # "bibtex", "suggest_key", "validate", "bibliography"
  papers: list | None         # For bibtex/validate/bibliography
  title: str | None           # For suggest_key
  authors: str | None         # For suggest_key
  year: int | None            # For suggest_key
  entry_type: str = "article" # For bibtex: "article", "inproceedings", "book", "misc"
  style: str = "apa"          # For bibliography: "apa", "mla", "chicago", "bibtex"
  sort: bool = true           # For bibliography: sort by author
```

---

## PDF (`pdf.py`)

### acquire_pdf
Get PDF. method: open_access (try download), browser_queue (queue for Windows).

```
Parameters:
  paper_id: int                # Required
  paper_ids: list[int] | None  # For browser_queue: batch paper IDs
  method: str = "open_access"  # "open_access" or "browser_queue"
  use_vpn: bool = false        # open_access: try direct publisher URLs (UW VPN)
  use_openurl: bool = false    # open_access: use UW Primo OpenURL resolver
  use_proxy: bool = false      # open_access: use UW EZProxy URLs
```

### manage_pdf
PDF management. action: status (papers with/without PDFs), queue_status, process, clear.

```
Parameters:
  action: str = "status"   # "status", "queue_status", "process", "clear"
  filter: str = "all"      # For status: "all", "has_pdf", "needs_pdf"
  limit: int = 50
  paper_id: int | None     # For queue_status: check specific paper
  auto_match: bool = true  # For process: match PDFs by DOI in filename
  clear_all: bool = false  # For clear: remove all including pending
```

### find_duplicates
Find duplicate papers by file hash or title similarity.

```
Parameters:
  method: str = "title"    # "hash" (exact file match) or "title" (similar)
  threshold: float = 0.85  # Title similarity threshold (0.0-1.0)
```

---

## Collections (`collections.py`)

### list_collections
List all collections (optionally filter by parent_id for hierarchy).

```
Parameters:
  parent_id: int | None  # Filter to children of this collection
  all: bool | None       # If true, list all collections ignoring hierarchy
```

### get_collection
Get a collection by ID with paper count and paper IDs.

```
Parameters:
  collection_id: int  # Required
```

### create_collection
Create a new collection.

```
Parameters:
  name: str               # Required
  description: str | None
  parent_id: int | None   # Parent collection ID for nesting
```

### update_collection
Update a collection's name, description, or parent.

```
Parameters:
  collection_id: int      # Required
  name: str | None
  description: str | None
  parent_id: int | None
```

### delete_collection
Delete a collection (papers are NOT deleted, just unlinked).

```
Parameters:
  collection_id: int  # Required
```

### add_papers_to_collection
Add one or more papers to a collection.

```
Parameters:
  collection_id: int    # Required
  paper_ids: list[int]  # Required
```

### remove_papers_from_collection
Remove one or more papers from a collection.

```
Parameters:
  collection_id: int    # Required
  paper_ids: list[int]  # Required
```

### get_collection_children
Get child collections of a collection.

```
Parameters:
  collection_id: int  # Required (the parent collection)
```

---

## Notes (`notes.py`)

### list_notes
List notes with optional filtering by paper_id or note_type.

```
Parameters:
  paper_id: int | None
  note_type: str | None  # "highlight", "comment", "summary"
  limit: int = 50
  offset: int = 0
```

### get_note
Get a note by ID.

```
Parameters:
  note_id: int  # Required
```

### create_note
Create a new note on a paper.

```
Parameters:
  paper_id: int              # Required
  content: str               # Required
  note_type: str = "comment" # "highlight", "comment", "summary"
  page_number: int | None
  position: str | None       # Position coordinates (JSON string)
```

### update_note
Update a note's content or metadata.

```
Parameters:
  note_id: int           # Required
  content: str | None
  note_type: str | None
  page_number: int | None
  position: str | None
```

### delete_note
Delete a note.

```
Parameters:
  note_id: int  # Required
```

### delete_paper_notes
Delete all notes for a paper (optionally filtered by type).

```
Parameters:
  paper_id: int          # Required
  note_type: str | None  # Only delete notes of this type
```

---

## Import/Export (`import_export.py`)

### import_paper
Import papers. source: wizard (smart, default), bibtex, external.

```
Parameters:
  source: str = "wizard"       # "wizard" (duplicate check), "bibtex", "external" (DOI/arXiv)
  doi: str | None              # Most reliable
  arxiv_id: str | None         # e.g. "2301.12345"
  title: str | None            # Paper title for lookup
  authors: str | None          # For disambiguation (wizard)
  year: int | None             # For disambiguation (wizard)
  bibtex_content: str | None   # Raw BibTeX content (source=bibtex)
  tags: list[str] | None
  collection_id: int | None
  pdf_path: str | None         # Local PDF path (wizard)
  skip_duplicate_check: bool = false  # (wizard)
  auto_chunk_pdf: bool = true  # Auto-chunk PDF text (wizard)
```

### export
Export papers. source: papers (by IDs, default), collection.

```
Parameters:
  source: str = "papers"       # "papers" (by paper_ids) or "collection"
  paper_ids: list[int] | None  # source=papers, omit for all
  limit: int = 50              # source=papers, max 500
  offset: int = 0
  collection_id: int | None    # source=collection
  include_subcollections: bool = false
  format: str = "bibtex"       # "bibtex", "json", "csv"
  include_abstract: bool = true
  include_notes: bool = false  # JSON only
```

### get_enrichment_queue
Papers needing enrichment (missing abstract, PDF, or chunks).

```
Parameters:
  status: str | None  # "needs_abstract", "needs_pdf", "needs_chunks", "pending", "failed"
  limit: int = 20
```

---

## Project (`project.py`)

### manage_bibtex
BibTeX operations. Actions: parse, link, import, export, sync.

```
Parameters:
  action: str = "parse"        # "parse" (.bib), "link" (match to DB), "import", "export", "sync"
  file_path: str | None        # Path to .bib file (parse/link/import/sync)
  content: str | None          # BibTeX content (alternative to file_path)
  min_similarity: float = 0.8  # For link: minimum title similarity
  skip_existing: bool = true   # For import: skip entries already in DB
  tags: list[str] | None       # For import
  paper_ids: list[int] | None  # For export (omit for all)
  output_path: str | None      # For export: output .bib path
  tag: str | None              # For export: filter by tag
  dry_run: bool = true         # For sync: preview changes without writing
```

### citation_health_check
Check citation health. Checks: all (default), orphans, missing, incomplete, duplicates.

```
Parameters:
  check: str = "all"                 # "all", "orphans", "missing", "incomplete", "duplicates"
  bib_path: str                      # Required
  tex_path: str | None               # For all/orphans/missing
  similarity_threshold: float = 0.9  # For duplicates
```

### scan_citations
Scan TeX files for citations. Mode: scan (all keys), locate (specific key).

```
Parameters:
  mode: str = "scan"        # "scan" (find all \cite{}) or "locate" (find specific key)
  file_path: str            # Required: .tex file or directory
  citation_key: str | None  # For locate
  recursive: bool = true    # For scan
```

### manage_project
Project citation config. Actions: get, set.

```
Parameters:
  action: str = "get"          # "get" (read config) or "set" (update config)
  project_path: str            # Required: path to project root
  bib_files: list[str] | None  # For set
  tex_paths: list[str] | None  # For set
```

---

## Discovery (`discovery.py`)

### semantic_find
Semantic search. input: paper (by ID), text (description), citation (suggest refs).

```
Parameters:
  input_type: str          # Required: "paper", "text", or "citation"
  paper_id: int | None     # input_type=paper
  text: str | None         # input_type=text or citation
  limit: int = 10
  min_similarity: float = 0.5
  include_summary: bool = false  # Include extraction summaries
  include_bibtex: bool = false   # Citation mode
  prefer_type: str = "any"       # Citation mode: "any", "review", "primary"
```

### manage_embeddings
Embeddings. action: status, process (batch), embed (single paper).

```
Parameters:
  action: str = "status"   # "status", "process", "embed"
  paper_id: int | None     # action=embed
  limit: int = 50          # action=process
  include_ids: bool = false           # action=status: include paper IDs needing embeddings
  include_paper_embeddings: bool = true
  include_chunk_embeddings: bool = true
```

### get_reading_queue
Unread papers sorted by rating and date added.

```
Parameters:
  limit: int = 20
  tag: str | None
  min_rating: int | None  # 1-5
```

### suggest_paper_tags
Suggest tags based on similar papers' tags.

```
Parameters:
  paper_id: int   # Required
  limit: int = 5
```

---

## Citation Network (`citation_network.py`)

### get_citations
Get citations. direction: incoming (who cites this), outgoing (what this cites).

```
Parameters:
  direction: str        # Required: "incoming" or "outgoing"
  paper_id: int | None  # Database paper ID (will use DOI/title to lookup)
  doi: str | None       # Preferred for accuracy
  title: str | None     # Fallback
  limit: int = 50
```

### find_common_references
Papers sharing references with a given paper (related work).

```
Parameters:
  paper_id: int        # Required
  min_shared: int = 2  # Minimum number of shared references
  limit: int = 10
```

### build_citation_graph
Build citation graph (nodes/edges) for visualization.

```
Parameters:
  paper_ids: list[int]           # Required
  include_external: bool = false
  depth: int = 1                 # 1-2
```

### import_references_from_paper
Import paper's references into library (from review papers).

```
Parameters:
  paper_id: int          # Required (the citing paper, e.g. a review)
  min_year: int | None   # Only import papers from this year or later
  max_imports: int = 50
  tags: list[str] | None
```

### get_local_citations
Local citation graph query (no API calls).

```
Parameters:
  paper_id: int           # Required
  direction: str = "both" # "citing", "cited", "both"
```

### link_papers_citation
Create citation link between two papers.

```
Parameters:
  citing_paper_id: int  # Required
  cited_paper_id: int   # Required
```

### get_claim_citations
Get claims from a paper with their cited references.

```
Parameters:
  paper_id: int           # Required
  section: str | None     # "introduction", "methods", "results", "discussion", "conclusion"
  claim_type: str | None  # "fact", "method", "comparison", "limitation", "background"
  importance: str | None  # "high", "medium", "low"
  limit: int = 50
```

### find_claims_citing_paper
Find all claims in library that cite a specific paper.

```
Parameters:
  paper_id: int   # Required (the paper being cited)
  limit: int = 50
```

### get_unmatched_claim_references
List unmatched references from claims (potential imports).

```
Parameters:
  paper_id: int | None  # Omit for all papers
  limit: int = 50
```

### get_citation_chain
Trace citation chains: claim -> cited paper -> that paper's claims -> etc.

```
Parameters:
  paper_id: int             # Required: starting paper
  claim_id: int | None      # Trace from specific claim
  depth: int = 2            # 1-3 citation hops
  direction: str = "forward"  # "forward" or "backward"
```

---

## Validation (`validation.py`)

### get_validation_status
Validation coverage stats (verified, not found, errors).

```
Parameters: none
```

### validate_papers
Validate, queue, or reset paper validation. Actions: validate (default), queue, reset.

```
Parameters:
  action: str = "validate"     # "validate", "queue", "reset"
  paper_ids: list[int] | None  # Omit to use queue (validate) or reset ALL (reset)
  limit: int = 20
  prioritize_with_doi: bool = true  # For queue
  confirm: bool | None         # For reset without paper_ids: must be true
```

---

## Extraction (`extraction.py`)

### extract_paper
AI extraction. tier: quick (abstract -> type/topics/summary) or deep (full-text -> findings/methods/claims).

```
Parameters:
  paper_id: int          # Required
  tier: str = "quick"    # "quick" (abstract-only) or "deep" (full-text, requires PDF)
  backend: str = "auto"  # "ollama" or "auto"
  force: bool = false    # Re-extract even if exists
```

### get_extraction_status
Extraction info. view: status (coverage), llm (backend), queue (needs extraction), reextraction.

```
Parameters:
  view: str = "status"          # "status", "llm", "queue", "reextraction"
  limit: int = 50               # For queue/reextraction
  older_than_days: int | None   # For reextraction: filter by age
```

### manage_pdf_processing
PDF text chunking. action: status, queue_status, add, process, retry.

```
Parameters:
  action: str = "queue_status"  # "status", "queue_status", "add", "process", "retry"
  paper_id: int | None          # For status/add/retry
  limit: int = 20               # For queue_status/process/retry
  force: bool = false           # For add/process: re-process even if exists
  status_filter: str | None     # For queue_status: "pending", "processing", "failed",
                                # "needs_processing"
```

### manage_references
PDF-extracted references. action: list, unmatched, match, import.

```
Parameters:
  action: str = "list"        # "list", "unmatched", "match", "import"
  paper_id: int | None        # For list
  reference_id: int | None    # For match/import
  limit: int = 50             # For unmatched
  status_filter: str = "all"  # For list: "all", "unmatched", "matched", "imported"
  with_doi_only: bool = false # For unmatched
  tags: list[str] | None      # For import
  collection_id: int | None   # For import
```

### verify_extraction
Verify extractions. scope: single, batch, report (quality check), queue (review queue).

```
Parameters:
  scope: str = "single"        # "single", "batch", "report", "queue"
  paper_id: int | None         # For single
  paper_ids: list[int] | None  # For batch (omit for all)
  limit: int = 50              # For batch/report/queue (queue default: 20)
```

`scope: "queue"` returns papers with `verification_score` below the accept
threshold (0.85), worst score first:

```json
{
  "success": true,
  "data": {
    "papers": [
      {
        "paper_id": 123,
        "title": "Example Paper Title",
        "verification_score": 0.42,
        "routing": "review",
        "failures": ["unsupported_claim: ...", "number_mismatch: ..."]
      }
    ],
    "count": 1
  }
}
```

### extract_papers_batch
Batch extraction with rate limiting. Uses queue if no paper_ids.

```
Parameters:
  paper_ids: list[int] | None  # Omit to use queue
  limit: int = 10              # Max papers from queue
  delay: float = 1.0           # Seconds between extractions
  force: bool = false
```

### prepare_extraction
Get paper content for Claude extraction. tier: quick or deep.

```
Parameters:
  paper_id: int           # Required
  tier: str = "quick"     # "quick" or "deep"
  max_chars: int = 80000  # Deep tier
```

### flag_for_deep_extraction
Flag paper(s) for deep extraction.

```
Parameters:
  paper_id: int | None         # Single paper
  paper_ids: list[int] | None  # Batch
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
    "total": 601,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```
