# Literature MCP - Tool Reference

Quick reference for all MCP tools with exact parameter signatures.

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
  paper_id: int  # Required - Paper ID

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

### batch_update_papers
Bulk update tags, read_status, or rating for multiple papers.

```
Parameters:
  paper_ids: list[int]     # Required - Paper IDs to update
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
  confirm: bool         # Required - Must be true to execute

Returns: {success, data: {deleted_count}}
```

## Search

### keyword_search
Full-text keyword search using Whoosh index.

```
Parameters:
  query: str           # Required - Search query
  limit: int = 10      # Max results
  year_min: int | None # Minimum publication year
  year_max: int | None # Maximum publication year

Returns: {success, data: [{id, title, year, score}], count}
```

### semantic_search
Semantic similarity search using embeddings.

```
Parameters:
  query: str                   # Required - Natural language query
  limit: int = 10              # Max results
  min_similarity: float = 0.5  # 0-1 similarity threshold
  search_level: str = "chunk"  # "chunk" or "paper"

Returns: {success, data: [{id, title, score, chunk_text?}], count}
```

### search_by_author
Find all papers by a specific author.

```
Parameters:
  author_name: str   # Required - Author name (partial match)
  limit: int = 20

Returns: {success, data: papers[]}
```

### search_by_tag
Find all papers with a specific tag.

```
Parameters:
  tag: str         # Required - Tag name
  limit: int = 20

Returns: {success, data: papers[]}
```

### find_duplicates
Find duplicate papers by file hash or title similarity.

```
Parameters:
  method: str = "title"         # "hash" or "title"
  threshold: float = 0.85       # Title similarity threshold (0-1)

Returns: {success, data: duplicate_groups[]}
```

## Content & Extraction

### get_paper_content
Get full paper content for AI analysis.

```
Parameters:
  paper_id: int  # Required

Returns: {success, data: {title, abstract, full_text, summary?, key_findings?}}
```

### store_extraction
Store AI-extracted content for a paper.

```
Parameters:
  paper_id: int                      # Required
  one_sentence_summary: str | None
  key_findings: list[str] | None
  methodology_summary: str | None
  paper_type: str | None             # "research_article", "review", etc.
  topics: list[str] | None

Returns: {success, data: extraction}
```

### get_extraction_queue
Get papers needing AI extraction.

```
Parameters:
  limit: int = 20

Returns: {success, data: papers[]}
```

## Collections

### list_collections
List all collections with optional hierarchy filtering.

```
Parameters:
  parent_id: int | None  # Filter to children of this collection
  all: bool = false      # List all ignoring hierarchy

Returns: {success, data: {count, collections: [{id, name, description, paper_count}]}}
```

### get_collection
Get collection details with paper IDs.

```
Parameters:
  collection_id: int  # Required

Returns: {success, data: {id, name, description, paper_count, paper_ids}}
```

### create_collection
Create a new collection.

```
Parameters:
  name: str                  # Required
  description: str | None
  parent_id: int | None      # Parent collection for nesting

Returns: {success, data: collection}
```

### update_collection
Update collection name, description, or parent.

```
Parameters:
  collection_id: int  # Required
  name: str | None
  description: str | None
  parent_id: int | None

Returns: {success, data: collection}
```

### delete_collection
Delete a collection (papers are NOT deleted).

```
Parameters:
  collection_id: int  # Required

Returns: {success}
```

### add_papers_to_collection
Add papers to a collection.

```
Parameters:
  collection_id: int    # Required
  paper_ids: list[int]  # Required

Returns: {success, data: {added_count}}
```

### remove_papers_from_collection
Remove papers from a collection.

```
Parameters:
  collection_id: int    # Required
  paper_ids: list[int]  # Required

Returns: {success, data: {removed_count}}
```

## Notes

### list_notes
List notes with optional filtering.

```
Parameters:
  paper_id: int | None       # Filter by paper
  note_type: str | None      # "highlight", "comment", "summary"
  limit: int = 50
  offset: int = 0

Returns: {success, data: notes[]}
```

### create_note
Create a new note on a paper.

```
Parameters:
  paper_id: int              # Required
  content: str               # Required
  note_type: str = "comment" # "highlight", "comment", "summary"
  page_number: int | None
  position: str | None       # JSON position coordinates

Returns: {success, data: note}
```

### update_note
Update a note's content.

```
Parameters:
  note_id: int       # Required
  content: str | None
  note_type: str | None
  page_number: int | None

Returns: {success, data: note}
```

### delete_note
Delete a note.

```
Parameters:
  note_id: int  # Required

Returns: {success}
```

### get_paper_notes
Get all notes for a specific paper.

```
Parameters:
  paper_id: int            # Required
  note_type: str | None    # Filter by type

Returns: {success, data: notes[]}
```

## Citations

### generate_bibtex
Generate BibTeX entries for papers.

```
Parameters:
  papers: list[{title, authors, year, doi?, journal?}]  # Required
  entry_type: str = "article"  # "article", "inproceedings", "book", "misc"

Returns: {success, data: bibtex_string}
```

### format_bibliography
Generate formatted bibliography in various styles.

```
Parameters:
  papers: list[object]      # Required
  style: str = "apa"        # "apa", "mla", "chicago", "bibtex"
  sort: bool = true         # Sort alphabetically by author

Returns: {success, data: formatted_string}
```

### suggest_citation_key
Generate a BibTeX citation key for a paper.

```
Parameters:
  title: str     # Required
  authors: str   # Required - Comma or "and" separated
  year: int | None

Returns: {success, data: key_string}
```

### scan_manuscript
Scan LaTeX/Markdown for citations and document structure.

```
Parameters:
  file_path: str | None   # Path to .tex or .md file
  content: str | None     # Manuscript content
  format: str = "latex"   # "latex" or "markdown"

Returns: {success, data: {citations: [keys], sections, stats}}
```

### check_citations
Check citations against library papers.

```
Parameters:
  manuscript_citations: list[str]  # Required - Citation keys from manuscript
  library_papers: list[object]     # Papers from library (optional)

Returns: {success, data: {found, orphan, unused}}
```

### citation_health_check
Comprehensive citation check for a project.

```
Parameters:
  bib_path: str  # Required - Path to .bib file
  tex_path: str  # Required - Path to .tex file or directory

Returns: {success, data: {orphans, missing, incomplete, duplicates}}
```

## External APIs

### lookup_paper_metadata
Look up paper metadata from external sources.

```
Parameters:
  doi: str | None
  title: str | None
  authors: str | None
  year: int | None

Returns: {success, data: {source, metadata}}
```

### search_external_papers
Search external databases for papers.

```
Parameters:
  query: str               # Required
  sources: list[str]       # ["crossref", "openalex", "semantic_scholar", "arxiv"]
  limit: int = 5           # Per source

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
  use_openurl: bool = false  # Use library resolver
  use_proxy: bool = false    # Use proxy URLs

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

## Import/Export

### import_bibtex
Import papers from BibTeX content.

```
Parameters:
  bibtex_content: str        # Required - Raw BibTeX
  collection_id: int | None  # Add to collection
  tags: list[str]            # Tags for all imported

Returns: {success, data: {imported, skipped, errors}}
```

### import_from_external
Import a paper by DOI, arXiv ID, or title lookup.

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
Export papers in various formats.

```
Parameters:
  paper_ids: list[int] | None  # None for all papers
  format: str = "bibtex"       # "bibtex", "json", "csv"
  include_abstract: bool = true
  include_notes: bool = false  # JSON only

Returns: {success, data: export_string}
```

### export_collection
Export all papers in a collection.

```
Parameters:
  collection_id: int  # Required
  format: str = "bibtex"
  include_subcollections: bool = false

Returns: {success, data: export_string}
```

## Zotero

### check_zotero_connection
Check Zotero connectivity.

```
Parameters: none

Returns: {success, data: {local_available, web_api_available, library_id?}}
```

### sync_from_zotero
Pull papers from Zotero into database.

```
Parameters: none

Returns: {success, data: {added, updated, total}}
```

### sync_to_zotero
Push enriched metadata to Zotero.

```
Parameters:
  create_new_items: bool = false  # Create new Zotero items for database-only papers

Returns: {success, data: {updated, created?, errors}}
```

### push_paper_to_zotero
Push a single paper to Zotero.

```
Parameters:
  paper_id: int              # Required
  create_if_missing: bool = true

Returns: {success, data: {zotero_key}}
```

### push_pdf_to_zotero
Upload PDF to Zotero as attachment.

```
Parameters:
  paper_id: int  # Required - Paper must exist in Zotero

Returns: {success}
```

## Project Configuration

### get_project_config
Get citation configuration for a project.

```
Parameters:
  project_path: str  # Required - Path to project root

Returns: {success, data: {bib_files, tex_paths}}
```

### set_project_config
Set citation configuration for a project.

```
Parameters:
  project_path: str        # Required
  bib_files: list[str]     # Relative paths to .bib files
  tex_paths: list[str]     # Relative paths to .tex files/directories

Returns: {success}
```

## Response Format

All tools return a consistent response structure:

```json
{
  "success": true,
  "data": { ... },       // Tool-specific result
  "error": null          // Error message if success=false
}
```

For list operations, pagination info is included:

```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "total": 418,
    "limit": 20,
    "offset": 0,
    "count": 20,
    "has_more": true,
    "page": 1,
    "total_pages": 21
  }
}
```
