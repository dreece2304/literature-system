"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class AuthorBase(BaseModel):
    name: str
    orcid: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None


class AuthorResponse(AuthorBase):
    id: int
    
    class Config:
        from_attributes = True


class TagBase(BaseModel):
    name: str
    category: Optional[str] = None
    color: Optional[str] = None


class TagResponse(TagBase):
    id: int
    
    class Config:
        from_attributes = True


class CollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CollectionResponse(CollectionBase):
    id: int
    zotero_key: Optional[str] = None
    
    class Config:
        from_attributes = True


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
    
    class Config:
        from_attributes = True


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
    
    class Config:
        from_attributes = True


class CitationResponse(BaseModel):
    id: int
    citing_paper_id: int
    cited_paper_id: int
    context: Optional[str] = None
    
    class Config:
        from_attributes = True