"""Shared API contract types for the research monorepo."""
from datetime import datetime
from typing import List, Optional, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar('T')

# Health check types
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    timestamp: datetime
    database: Optional[Dict[str, Any]] = None
    search_index: Optional[Dict[str, Any]] = None

# Pagination types
class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    items: List[T]
    total: int
    skip: int
    limit: int
    has_next: bool

# Author types
class Author(BaseModel):
    """Author representation."""
    id: int
    name: str
    orcid: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None

class AuthorCreate(BaseModel):
    """Author creation payload."""
    name: str
    orcid: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None

# Tag types
class Tag(BaseModel):
    """Tag representation."""
    id: int
    name: str
    category: Optional[str] = None
    color: Optional[str] = None

class TagCreate(BaseModel):
    """Tag creation payload."""
    name: str
    category: Optional[str] = None
    color: Optional[str] = None

# Collection types
class Collection(BaseModel):
    """Collection representation."""
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    zotero_key: Optional[str] = None
    paper_count: Optional[int] = 0

class CollectionCreate(BaseModel):
    """Collection creation payload."""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None

# Paper types
class Paper(BaseModel):
    """Paper representation."""
    id: int
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    rating: Optional[int] = None
    read_status: Optional[str] = "unread"
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    zotero_key: Optional[str] = None
    zotero_version: Optional[int] = None
    date_added: datetime
    date_modified: Optional[datetime] = None
    date_read: Optional[datetime] = None
    word_count: Optional[int] = None
    authors: List[Author] = []
    tags: List[Tag] = []
    collections: List[Collection] = []

class PaperCreate(BaseModel):
    """Paper creation payload."""
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    read_status: Optional[str] = "unread"
    file_path: Optional[str] = None
    authors: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    collections: Optional[List[str]] = []

class PaperUpdate(BaseModel):
    """Paper update payload."""
    title: Optional[str] = None
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    read_status: Optional[str] = None
    date_read: Optional[datetime] = None
    authors: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    collections: Optional[List[str]] = None

# Search types
class SearchRequest(BaseModel):
    """Search request payload."""
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(20, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None

class SearchResult(BaseModel):
    """Single search result."""
    paper: Paper
    score: float
    highlights: Optional[List[str]] = []

class SearchResponse(BaseModel):
    """Search response."""
    query: str
    total_results: int
    papers: List[SearchResult]
    facets: Optional[Dict[str, Dict[str, int]]] = None
    suggestions: Optional[List[str]] = []
    query_time_ms: Optional[int] = None

# Sync types
class ZoteroSyncRequest(BaseModel):
    """Zotero sync request payload."""
    force_full_sync: bool = False
    sync_attachments: bool = True
    collection_keys: Optional[List[str]] = None

class ZoteroSyncResponse(BaseModel):
    """Zotero sync response."""
    sync_id: str
    status: str
    message: str
    estimated_duration_minutes: Optional[int] = None

class ZoteroSyncStatus(BaseModel):
    """Zotero sync status."""
    sync_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    results: Optional[Dict[str, Any]] = None
    log_messages: Optional[List[str]] = []

# Statistics types
class DatabaseStats(BaseModel):
    """Database statistics."""
    papers: int
    authors: int
    tags: int
    collections: int
    notes: int
    citations: int

class ContentStats(BaseModel):
    """Content statistics."""
    papers_with_pdfs: int
    pdf_coverage_percent: float
    total_word_count: int
    average_words_per_paper: int

class ActivityStats(BaseModel):
    """Activity statistics."""
    papers_added_last_week: int
    papers_read_last_week: int
    last_sync: Optional[datetime] = None
    most_active_collections: Optional[List[Dict[str, Any]]] = []

class SearchIndexStats(BaseModel):
    """Search index statistics."""
    status: str
    documents_indexed: int
    index_size_mb: Optional[int] = None
    last_updated: Optional[datetime] = None

class ServiceStats(BaseModel):
    """Complete service statistics."""
    database: DatabaseStats
    content: ContentStats
    activity: ActivityStats
    search_index: SearchIndexStats

# Event types
class BaseEvent(BaseModel):
    """Base event structure."""
    event_type: str
    timestamp: datetime
    service: str
    event_id: str

class PaperEvent(BaseEvent):
    """Paper-related events."""
    paper_id: int
    paper_title: Optional[str] = None
    user_id: Optional[str] = None
    changes: Optional[List[str]] = None  # List of changed fields for updates
    metadata: Optional[Dict[str, Any]] = None

class SyncEvent(BaseEvent):
    """Sync-related events."""
    sync_id: str
    sync_type: str  # "zotero", "manual", etc.
    results: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[int] = None
    papers_processed: Optional[int] = None