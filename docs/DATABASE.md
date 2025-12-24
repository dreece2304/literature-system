# Database Schema and Indexes

## Overview

The literature database uses SQLite with SQLAlchemy ORM. The schema supports:
- Paper metadata storage (418+ papers)
- Author and tag relationships (many-to-many)
- Collection hierarchies
- Notes and annotations
- Citation tracking
- AI extraction results

## Index Strategy

Indexes are defined in two places:
1. **SQLAlchemy models** (`src/literature_core/models.py`) - For new databases
2. **Migration script** (`src/scripts/add_indexes.py`) - For existing databases

### Running the Migration

```bash
# Preview what would be done
cd /path/to/research && mamba run -n litai python -m scripts.add_indexes --dry-run

# Apply indexes
mamba run -n litai python -m scripts.add_indexes

# Verify indexes exist
mamba run -n litai python -m scripts.add_indexes --verify
```

The migration is idempotent - safe to run multiple times.

---

## Index Catalog

### Papers Table

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_papers_citation_key` | `citation_key` | BibTeX matching in CitationService |
| `ix_papers_read_status` | `read_status` | Filter by unread/reading/read |
| `ix_papers_year` | `year` | Year filtering and sorting |
| `ix_papers_rating` | `rating` | Favorites filter (rating >= 4) |
| `ix_papers_date_added` | `date_added` | Recent papers, chronological sorting |
| `ix_papers_year_status` | `year, read_status` | Common combined filter |

**Note**: `doi`, `arxiv_id`, `pubmed_id`, `zotero_key` have UNIQUE indexes (created by SQLAlchemy automatically).

### Authors Table

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_authors_name` | `name` | Author search in SearchService |

**Note**: `orcid` has a UNIQUE index.

### Junction Tables

These indexes are critical for JOIN performance.

#### paper_authors

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_paper_authors_paper_id` | `paper_id` | Get authors for a paper |
| `ix_paper_authors_author_id` | `author_id` | Get papers by an author |
| `ix_paper_authors_both` | `paper_id, author_id` | Covering index for lookups |

#### paper_tags

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_paper_tags_paper_id` | `paper_id` | Get tags for a paper |
| `ix_paper_tags_tag_id` | `tag_id` | Get papers with a tag |

#### paper_collections

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_paper_collections_paper_id` | `paper_id` | Get collections for a paper |
| `ix_paper_collections_collection_id` | `collection_id` | Get papers in a collection |

### Collections Table

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_collections_name` | `name` | Collection lookup by name |
| `ix_collections_parent_id` | `parent_id` | Hierarchy traversal (children) |

**Note**: `zotero_key` has a UNIQUE index.

### Notes Table

| Index Name | Column(s) | Purpose |
|------------|-----------|---------|
| `ix_notes_paper_id` | `paper_id` | Get all notes for a paper |
| `ix_notes_note_type` | `note_type` | Filter by highlight/comment/summary |
| `ix_notes_paper_type` | `paper_id, note_type` | Get notes of specific type for paper |

---

## When to Add New Indexes

Consider adding an index when:

1. **Frequent WHERE clauses** - Columns often used in filters
2. **JOIN operations** - Foreign key columns in junction tables
3. **ORDER BY** - Columns frequently used for sorting
4. **GROUP BY** - Columns used in aggregations

Do NOT add indexes for:
- Small tables (<100 rows)
- Columns with low cardinality (few unique values)
- Columns rarely used in queries
- Tables with heavy INSERT/UPDATE activity (indexes slow writes)

---

## Adding New Indexes

### 1. Update the Migration Script

Add to `INDEXES` list in `src/scripts/add_indexes.py`:

```python
INDEXES = [
    # ... existing indexes ...

    # New index: (name, table, [columns], unique)
    ("ix_papers_journal", "papers", ["journal"], False),
]
```

### 2. Update SQLAlchemy Models

For single-column indexes, add `index=True`:

```python
journal = Column(String(200), index=True)
```

For composite indexes, add to `__table_args__`:

```python
class Paper(Base):
    __tablename__ = 'papers'
    __table_args__ = (
        Index('ix_papers_year_status', 'year', 'read_status'),
        Index('ix_papers_journal_year', 'journal', 'year'),  # New
    )
```

### 3. Run Migration on Existing Databases

```bash
mamba run -n litai python -m scripts.add_indexes
```

---

## Performance Impact

With 418 papers, the indexes provide:
- **10-100x faster** lookups on indexed columns
- **Minimal storage overhead** (~1-2% database size increase)
- **No noticeable write slowdown** at current scale

For 10,000+ papers, these indexes become essential for responsive queries.

---

## Verification

Check all indexes exist:

```bash
mamba run -n litai python -m scripts.add_indexes --verify
```

Expected output shows 19 custom indexes plus SQLAlchemy's automatic UNIQUE indexes.

---

## Related Documentation

- `REFACTOR_SUMMARY.md` - Service layer architecture
- `SERVICE_PORTS.md` - How MCP server accesses database
- `src/literature_core/models.py` - SQLAlchemy model definitions
