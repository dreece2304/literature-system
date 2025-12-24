"""
Pydantic schemas for API request/response validation.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Writer Agent Schemas
# ============================================================================

class CitationSuggestionRequest(BaseModel):
    """Request for citation suggestions."""

    text: str = Field(..., description="Text needing citations", min_length=10)
    claim: Optional[str] = Field(None, description="Specific claim to support")
    n: int = Field(5, description="Number of suggestions", ge=1, le=20)
    use_context: bool = Field(True, description="Use manuscript context if available")


class CitationSuggestionItem(BaseModel):
    """Single citation suggestion."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    relevance_score: float
    contribution: str
    integration_suggestion: str
    quote_suggestion: Optional[str] = None


class CitationSuggestionResponse(BaseModel):
    """Response with citation suggestions."""

    action: str = "suggest_citations"
    suggestions: List[CitationSuggestionItem]


class OutlineExpansionRequest(BaseModel):
    """Request for outline expansion."""

    section: str = Field(..., description="Section name")
    outline: str = Field(..., description="Outline/bullet points to expand")
    target_length: int = Field(500, description="Target word count", ge=100, le=2000)
    min_citations: int = Field(3, description="Minimum citations", ge=1, le=10)


class ParagraphItem(BaseModel):
    """Single paragraph in expanded section."""

    topic: str
    content: str
    citations: List[str]


class OutlineExpansionResponse(BaseModel):
    """Response with expanded outline."""

    action: str = "expand_outline"
    section: str
    paragraphs: List[ParagraphItem]
    word_count: int
    citation_count: int


class MissingCitationsRequest(BaseModel):
    """Request to detect missing citations."""

    text: str = Field(..., description="Text to analyze", min_length=100)


class UncitedClaim(BaseModel):
    """Uncited claim with suggestions."""

    text: str
    reason: str
    suggested_papers: List[Dict[str, Any]]
    suggested_revision: str


class MissingCitationsResponse(BaseModel):
    """Response with uncited claims."""

    action: str = "detect_missing_citations"
    uncited_claims: List[UncitedClaim]


class EnhanceCitationRequest(BaseModel):
    """Request to enhance a citation."""

    current_text: str = Field(..., description="Current text with citation")
    paper_id: str = Field(..., description="ID of cited paper")


class EnhanceCitationResponse(BaseModel):
    """Response with citation enhancement."""

    action: str = "enhance_citation"
    current: str
    improved: str
    specific_findings_added: List[str]
    explanation: str


# ============================================================================
# Context Management Schemas
# ============================================================================

class LoadManuscriptRequest(BaseModel):
    """Request to load a manuscript."""

    manuscript_path: str = Field(..., description="Path to manuscript file")
    set_active: bool = Field(True, description="Set as active manuscript")


class ManuscriptInfo(BaseModel):
    """Manuscript information."""

    manuscript_path: str
    title: str
    active_section: Optional[str]
    total_sections: int
    total_words: int
    total_citations: int
    last_updated: str


class LoadManuscriptResponse(BaseModel):
    """Response after loading manuscript."""

    success: bool
    manuscript: Optional[ManuscriptInfo]
    error: Optional[str] = None


class UpdateContextRequest(BaseModel):
    """Request to update writing context."""

    active_section: Optional[str] = None
    cursor_line: Optional[int] = None
    recent_text: Optional[str] = None
    writing_goal: Optional[str] = None
    research_topics: Optional[List[str]] = None


class ContextResponse(BaseModel):
    """Current writing context."""

    manuscript_title: Optional[str]
    active_section: Optional[str]
    section_content: str
    recent_text: str
    existing_citations: List[str]
    section_citations: List[str]
    writing_goal: Optional[str]
    research_topics: List[str]


# ============================================================================
# Search Schemas
# ============================================================================

class SearchRequest(BaseModel):
    """Request for semantic search."""

    query: str = Field(..., description="Search query", min_length=3)
    top_k: int = Field(10, description="Number of results", ge=1, le=50)
    score_threshold: Optional[float] = Field(None, description="Minimum similarity score", ge=0.0, le=1.0)
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")


class SearchResultItem(BaseModel):
    """Single search result."""

    paper_id: str
    chunk_id: str
    score: float
    text: str
    title: str
    authors: str
    year: Optional[int]


class SearchResponse(BaseModel):
    """Search results."""

    query: str
    results: List[SearchResultItem]
    total: int


class SimilarPapersRequest(BaseModel):
    """Request for similar papers."""

    paper_id: str = Field(..., description="Reference paper ID")
    top_k: int = Field(10, description="Number of similar papers", ge=1, le=50)


class PaperSummaryRequest(BaseModel):
    """Request for paper summary."""

    paper_id: str = Field(..., description="Paper ID")


class PaperSummary(BaseModel):
    """Paper summary."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    preview: str
    num_chunks: int


# ============================================================================
# Bibliography Schemas
# ============================================================================

class GenerateBibliographyRequest(BaseModel):
    """Request to generate bibliography."""

    paper_ids: List[str] = Field(..., description="List of paper IDs")
    style: Literal["apa", "mla", "chicago", "bibtex"] = Field("apa", description="Citation style")
    sort: bool = Field(True, description="Sort alphabetically")


class GenerateBibliographyResponse(BaseModel):
    """Generated bibliography."""

    style: str
    bibliography: str
    paper_count: int


class InlineCitationRequest(BaseModel):
    """Request for inline citation format."""

    paper_id: str = Field(..., description="Paper ID")
    style: Literal["author-year", "numeric", "superscript"] = Field("author-year")


class InlineCitationResponse(BaseModel):
    """Inline citation."""

    paper_id: str
    citation: str
    style: str


# ============================================================================
# System Schemas
# ============================================================================

class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str
    components: Dict[str, Any]


class StatsResponse(BaseModel):
    """System statistics."""

    embedding_stats: Dict[str, Any]
    vectorstore_stats: Dict[str, Any]
    context_stats: Dict[str, Any]
    llm_stats: Dict[str, Any]


# ============================================================================
# Triager Agent Schemas
# ============================================================================

class ScorePaperRequest(BaseModel):
    """Request to score a single paper."""

    paper_id: str = Field(..., description="Paper ID to score")
    research_interests: List[str] = Field(..., description="Research interest keywords")
    current_projects: Optional[List[str]] = Field(None, description="Current project descriptions")
    preferred_methods: Optional[List[str]] = Field(None, description="Preferred research methods")
    context_id: str = Field("default", description="Research context identifier for multi-project support")


class PaperScoreResponse(BaseModel):
    """Paper score response."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    score: int = Field(..., ge=0, le=10, description="Relevance score (0-10)")
    justification: str
    dimensions: Dict[str, float]
    key_takeaways: List[str]
    action: Literal["must_read", "should_read", "skim", "skip"]


class ScoreBatchRequest(BaseModel):
    """Request to score multiple papers."""

    paper_ids: List[str] = Field(..., description="List of paper IDs to score")
    research_interests: List[str] = Field(..., description="Research interest keywords")
    current_projects: Optional[List[str]] = Field(None, description="Current project descriptions")
    max_papers: int = Field(20, description="Maximum papers to score", ge=1, le=50)


class ScoreBatchResponse(BaseModel):
    """Batch scoring response."""

    scores: List[Dict[str, Any]]
    ranked_ids: List[str]
    summary: Dict[str, int]


class ComparePapersRequest(BaseModel):
    """Request to compare two papers."""

    paper_id_a: str = Field(..., description="First paper ID")
    paper_id_b: str = Field(..., description="Second paper ID")
    research_goal: str = Field(..., description="Research goal for comparison")


class ComparePapersResponse(BaseModel):
    """Paper comparison response."""

    more_relevant: str
    score_a: int
    score_b: int
    comparison: Dict[str, Any]
    recommendation: str


class TopPapersRequest(BaseModel):
    """Request for top-scored papers."""

    min_score: int = Field(7, description="Minimum score threshold", ge=0, le=10)
    limit: int = Field(10, description="Maximum papers to return", ge=1, le=50)
    context_id: str = Field("default", description="Research context identifier")


class TopPapersResponse(BaseModel):
    """Top papers response."""

    papers: List[Dict[str, Any]]
    total: int


# ============================================================================
# Reader Agent Schemas
# ============================================================================

class AskQuestionRequest(BaseModel):
    """Request to ask a question about papers."""

    question: str = Field(..., description="Question to answer", min_length=10)
    top_k: int = Field(5, description="Number of papers to retrieve", ge=1, le=20)
    score_threshold: Optional[float] = Field(None, description="Minimum similarity score", ge=0.0, le=1.0)


class CitationItem(BaseModel):
    """Citation in QA response."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    relevant_quote: str


class QAResponse(BaseModel):
    """Q&A response."""

    question: str
    answer: str
    citations: List[CitationItem]
    confidence: Literal["high", "medium", "low"]
    limitations: Optional[str]
    follow_up_questions: List[str]


class SummarizePaperRequest(BaseModel):
    """Request to summarize a paper."""

    paper_id: str = Field(..., description="Paper ID to summarize")


class PaperSummaryResponse(BaseModel):
    """Paper summary response."""

    paper_id: str
    title: str
    research_question: str
    methodology: str
    key_findings: List[str]
    contributions: List[str]
    limitations: List[str]
    future_work: List[str]
    one_sentence_summary: str


class FindRelatedRequest(BaseModel):
    """Request to find related papers."""

    paper_id: str = Field(..., description="Reference paper ID")
    top_k: int = Field(10, description="Number of related papers", ge=1, le=50)


class RelatedPapersResponse(BaseModel):
    """Related papers response."""

    reference_paper_id: str
    total_related: int
    highly_related: List[Dict[str, Any]]
    moderately_related: List[Dict[str, Any]]
    somewhat_related: List[Dict[str, Any]]


# ============================================================================
# Error Response
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: Optional[str] = None
    status_code: int
