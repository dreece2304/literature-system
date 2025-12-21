"""
Search API endpoints.
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.api.schemas import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SimilarPapersRequest,
    PaperSummaryRequest,
    PaperSummary,
    GenerateBibliographyRequest,
    GenerateBibliographyResponse,
    InlineCitationRequest,
    InlineCitationResponse,
)
from src.services.search_service import get_search_service
from src.services.citation_service import get_citation_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.post(
    "/",
    response_model=SearchResponse,
    summary="Search papers",
    description="Semantic search across paper collection",
)
async def search_papers(request: SearchRequest):
    """
    Search for papers using semantic similarity.

    The search:
    1. Converts query to embedding
    2. Finds similar paper chunks in vector store
    3. Returns ranked results with relevance scores

    Supports metadata filtering (e.g., by year, author).
    """
    try:
        search_service = get_search_service()

        results = search_service.search(
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            filters=request.filters,
        )

        result_items = [
            SearchResultItem(
                paper_id=r.paper_id,
                chunk_id=r.chunk_id,
                score=r.score,
                text=r.text,
                title=r.title,
                authors=r.authors,
                year=r.year,
            )
            for r in results
        ]

        return SearchResponse(
            query=request.query,
            results=result_items,
            total=len(result_items),
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.post(
    "/similar",
    response_model=SearchResponse,
    summary="Find similar papers",
    description="Find papers similar to a given paper",
)
async def find_similar_papers(request: SimilarPapersRequest):
    """
    Find papers similar to a reference paper.

    Uses the reference paper's content to find semantically similar papers
    in the collection.
    """
    try:
        search_service = get_search_service()

        results = search_service.find_similar_papers(
            paper_id=request.paper_id,
            top_k=request.top_k,
        )

        result_items = [
            SearchResultItem(
                paper_id=r.paper_id,
                chunk_id=r.chunk_id,
                score=r.score,
                text=r.text,
                title=r.title,
                authors=r.authors,
                year=r.year,
            )
            for r in results
        ]

        return SearchResponse(
            query=f"similar_to:{request.paper_id}",
            results=result_items,
            total=len(result_items),
        )

    except Exception as e:
        logger.error(f"Similar papers search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find similar papers: {str(e)}",
        )


@router.post(
    "/paper/summary",
    response_model=PaperSummary,
    summary="Get paper summary",
    description="Get summary information for a specific paper",
)
async def get_paper_summary(request: PaperSummaryRequest):
    """
    Get summary of a paper.

    Returns:
    - Title, authors, year
    - Text preview
    - Number of indexed chunks
    """
    try:
        search_service = get_search_service()

        summary = search_service.get_paper_summary(request.paper_id)

        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper not found: {request.paper_id}",
            )

        return PaperSummary(**summary)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get paper summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get paper summary: {str(e)}",
        )


@router.get(
    "/stats",
    summary="Get search statistics",
    description="Get statistics about the paper collection",
)
async def get_search_stats():
    """
    Get search service statistics.

    Returns:
    - Total papers indexed
    - Total chunks
    - Embedding dimension
    - Distance metric
    """
    try:
        search_service = get_search_service()
        stats = search_service.get_stats()

        return stats

    except Exception as e:
        logger.error(f"Failed to get search stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get search stats: {str(e)}",
        )


# ============================================================================
# Bibliography Endpoints
# ============================================================================

@router.post(
    "/bibliography",
    response_model=GenerateBibliographyResponse,
    summary="Generate bibliography",
    description="Generate formatted bibliography for papers",
)
async def generate_bibliography(request: GenerateBibliographyRequest):
    """
    Generate bibliography in specified format.

    Supports:
    - APA
    - MLA
    - Chicago
    - BibTeX

    Papers are fetched from the literature database API.
    """
    try:
        citation_service = get_citation_service()
        search_service = get_search_service()

        # Fetch paper data
        papers = []
        for paper_id in request.paper_ids:
            summary = search_service.get_paper_summary(paper_id)
            if summary:
                papers.append(summary)

        if not papers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid papers found",
            )

        # Generate bibliography
        bibliography = citation_service.generate_bibliography(
            papers=papers,
            style=request.style,
            sort=request.sort,
        )

        return GenerateBibliographyResponse(
            style=request.style,
            bibliography=bibliography,
            paper_count=len(papers),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate bibliography: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate bibliography: {str(e)}",
        )


@router.post(
    "/inline-citation",
    response_model=InlineCitationResponse,
    summary="Format inline citation",
    description="Get formatted inline citation for a paper",
)
async def format_inline_citation(request: InlineCitationRequest):
    """
    Format inline citation.

    Supports:
    - Author-year format: [Smith et al., 2020]
    - Numeric format: [1]
    - Superscript format: ¹
    """
    try:
        citation_service = get_citation_service()
        search_service = get_search_service()

        # Get paper data
        paper_summary = search_service.get_paper_summary(request.paper_id)

        if not paper_summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper not found: {request.paper_id}",
            )

        # Format citation
        citation = citation_service.format_inline_citation(
            paper_data=paper_summary,
            style=request.style,
        )

        return InlineCitationResponse(
            paper_id=request.paper_id,
            citation=citation,
            style=request.style,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to format inline citation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to format inline citation: {str(e)}",
        )
