"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime


class AuthorBase(BaseModel):
    name: str
    orcid: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None


class AuthorResponse(AuthorBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TagBase(BaseModel):
    name: str
    category: Optional[str] = None
    color: Optional[str] = None


class TagResponse(TagBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CollectionCreate(CollectionBase):
    """Schema for creating a new collection."""
    pass


class CollectionUpdate(BaseModel):
    """Schema for updating a collection."""
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CollectionResponse(CollectionBase):
    id: int
    zotero_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CollectionWithPapersResponse(CollectionResponse):
    """Collection response with paper count and paper list."""
    paper_count: int = 0
    paper_ids: List[int] = []


class CollectionPaperAction(BaseModel):
    """Schema for adding/removing papers from collection."""
    paper_ids: List[int]


class PaperBase(BaseModel):
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


class PaperCreate(PaperBase):
    file_path: Optional[str] = None
    authors: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    collections: Optional[List[str]] = []


class PaperUpdate(BaseModel):
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


class PaperResponse(PaperBase):
    id: int
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    zotero_key: Optional[str] = None
    zotero_version: Optional[int] = None
    date_added: datetime
    date_modified: Optional[datetime] = None
    date_read: Optional[datetime] = None
    word_count: Optional[int] = None
    authors: List[AuthorResponse] = []
    tags: List[TagResponse] = []
    collections: List[CollectionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(20, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    query: str
    total_results: int
    papers: List[PaperResponse]


class NoteBase(BaseModel):
    content: str
    note_type: Optional[str] = "comment"
    page_number: Optional[int] = None
    position: Optional[str] = None


class NoteCreate(NoteBase):
    paper_id: int


class NoteResponse(NoteBase):
    id: int
    paper_id: int
    created_at: datetime
    modified_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CitationResponse(BaseModel):
    id: int
    citing_paper_id: int
    cited_paper_id: int
    context: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Manuscript and Citation Location Schemas ==========

class ManuscriptBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    project_path: str
    tex_directory: str = "paper/tex"
    bib_file: Optional[str] = None
    description: Optional[str] = None


class ManuscriptCreate(ManuscriptBase):
    pass


class ManuscriptUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    project_path: Optional[str] = None
    tex_directory: Optional[str] = None
    bib_file: Optional[str] = None
    description: Optional[str] = None


class ManuscriptResponse(ManuscriptBase):
    id: int
    last_scanned: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CitationLocationBase(BaseModel):
    citation_key: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    context: Optional[str] = None
    section_inferred: Optional[str] = None
    priority: Optional[str] = None


class CitationLocationResponse(CitationLocationBase):
    id: int
    paper_id: Optional[int] = None
    manuscript_id: int
    scan_date: datetime

    model_config = ConfigDict(from_attributes=True)


class CitationScanRequest(BaseModel):
    clear_existing: bool = True


class CitationScanResponse(BaseModel):
    manuscript_id: int
    total_citations: int
    unique_keys: int
    matched_to_papers: int
    unmatched_keys: List[str]
    locations_created: int


class CitationCheckResponse(BaseModel):
    manuscript_id: int
    total_papers_cited: int
    papers_with_citation_key: int
    papers_without_citation_key: int
    orphan_citations: List[str]
    duplicate_locations: int
    issues: List[str]


class SetCitationKeyRequest(BaseModel):
    citation_key: str = Field(..., min_length=1, max_length=100)


class CitationKeySuggestion(BaseModel):
    paper_id: int
    paper_title: str
    suggested_key: str


class CitationReportEntry(BaseModel):
    citation_key: str
    paper_id: Optional[int] = None
    paper_title: Optional[str] = None
    total_citations: int
    locations: List[CitationLocationResponse]


class CitationReportResponse(BaseModel):
    manuscript_id: int
    manuscript_name: str
    last_scanned: Optional[datetime] = None
    total_unique_citations: int
    total_citation_instances: int
    entries: List[CitationReportEntry]


# ========== Integration API Schemas ==========

class PaperContentResponse(BaseModel):
    """Full paper content for AI processing."""
    id: int
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    citation_key: Optional[str] = None
    full_text: Optional[str] = None
    authors: List[str] = []
    tags: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class AIMetadataUpdate(BaseModel):
    """AI-generated metadata to update on a paper."""
    summary: Optional[str] = None
    key_findings: Optional[List[str]] = None
    suggested_tags: Optional[List[str]] = None
    relevance_score: Optional[float] = Field(None, ge=0, le=1)
    categorization: Optional[Dict[str, Any]] = None


class BulkExportRequest(BaseModel):
    format: str = Field("json", pattern="^(json|bibtex|csv)$")
    paper_ids: Optional[List[int]] = None
    include_full_text: bool = False


class HealthResponse(BaseModel):
    status: str
    database: str
    search_index: str
    papers_count: int
    manuscripts_count: int


# ========== Paper Content Extraction Schemas ==========

class KeyFinding(BaseModel):
    """A single key finding from a paper."""
    finding_id: str
    statement: str
    evidence: Optional[str] = None
    topics: List[str] = []
    used_in_manuscript: bool = False


class PaperContentBase(BaseModel):
    """Base schema for extracted paper content."""
    extraction_depth: str = Field(..., pattern="^(CITATION_ONLY|BASIC|COMPREHENSIVE)$")
    extractor_model: Optional[str] = None
    paper_type: Optional[str] = None
    topics: Optional[List[str]] = None
    one_sentence_summary: Optional[str] = None
    key_findings: Optional[List[KeyFinding]] = None
    methodology_summary: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None


class PaperContentCreate(PaperContentBase):
    """Schema for creating new paper content."""
    pass


class PaperContentUpdate(BaseModel):
    """Schema for updating paper content (all fields optional)."""
    extraction_depth: Optional[str] = Field(None, pattern="^(CITATION_ONLY|BASIC|COMPREHENSIVE)$")
    extractor_model: Optional[str] = None
    paper_type: Optional[str] = None
    topics: Optional[List[str]] = None
    one_sentence_summary: Optional[str] = None
    key_findings: Optional[List[KeyFinding]] = None
    methodology_summary: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None


class PaperContentStoredResponse(PaperContentBase):
    """Response schema for stored paper content."""
    id: int
    paper_id: int
    extraction_date: datetime
    schema_version: str
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Project Relevance Schemas ==========

class ProjectRelevanceBase(BaseModel):
    """Base schema for project relevance."""
    project_name: str = Field(..., min_length=1, max_length=200)
    overall_relevance: str = Field(..., pattern="^(CRITICAL|HIGH|MEDIUM|LOW|NONE)$")
    relevance_summary: Optional[str] = None
    primary_use: Optional[str] = None  # introduction, methods, results, discussion


class ProjectRelevanceCreate(ProjectRelevanceBase):
    """Schema for creating new project relevance."""
    pass


class ProjectRelevanceUpdate(BaseModel):
    """Schema for updating project relevance."""
    overall_relevance: Optional[str] = Field(None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW|NONE)$")
    relevance_summary: Optional[str] = None
    primary_use: Optional[str] = None


class ProjectRelevanceResponse(ProjectRelevanceBase):
    """Response schema for project relevance."""
    id: int
    paper_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectPapersResponse(BaseModel):
    """Response schema for papers relevant to a project."""
    project_name: str
    total_papers: int
    papers_by_relevance: Dict[str, int]  # {CRITICAL: 5, HIGH: 10, ...}
    papers: List[Dict[str, Any]]  # [{paper_id, title, overall_relevance, ...}]


# ========== Extraction Queue Schemas ==========

class ExtractionQueueResponse(BaseModel):
    """Response schema for extraction queue."""
    total_papers: int
    unextracted: int
    citation_only: int
    basic: int
    comprehensive: int
    papers_needing_extraction: List[Dict[str, Any]]  # [{paper_id, title, current_depth}]


class ExtractionStatsResponse(BaseModel):
    """Response schema for extraction statistics."""
    total_papers: int
    extraction_counts: Dict[str, int]  # By depth level
    by_model: Dict[str, int]  # By extractor model
    average_findings_per_paper: float
    recent_extractions: int  # Last 7 days
