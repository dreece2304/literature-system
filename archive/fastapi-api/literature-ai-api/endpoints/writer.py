"""
Writer agent API endpoints.
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.api.schemas import (
    CitationSuggestionRequest,
    CitationSuggestionResponse,
    OutlineExpansionRequest,
    OutlineExpansionResponse,
    MissingCitationsRequest,
    MissingCitationsResponse,
    EnhanceCitationRequest,
    EnhanceCitationResponse,
)
from src.agents.writer import get_writer_agent

router = APIRouter(prefix="/writer", tags=["Writer Agent"])


@router.post(
    "/suggest-citations",
    response_model=CitationSuggestionResponse,
    summary="Suggest citations for text",
    description="Get AI-powered citation suggestions for a given text passage",
)
async def suggest_citations(request: CitationSuggestionRequest):
    """
    Suggest relevant citations for a text passage.

    The agent will:
    1. Search for relevant papers in the collection
    2. Use LLM to determine which papers best support the text
    3. Provide integration suggestions for each citation

    Returns a list of suggested papers with relevance scores and integration advice.
    """
    try:
        writer_agent = get_writer_agent()

        suggestions = await writer_agent.suggest_citations(
            text=request.text,
            claim=request.claim,
            n=request.n,
            use_context=request.use_context,
        )

        return CitationSuggestionResponse(
            suggestions=[
                {
                    "paper_id": s.paper_id,
                    "title": s.title,
                    "authors": s.authors,
                    "year": s.year,
                    "relevance_score": s.relevance_score,
                    "contribution": s.contribution,
                    "integration_suggestion": s.integration_suggestion,
                    "quote_suggestion": s.quote_suggestion,
                }
                for s in suggestions
            ]
        )

    except Exception as e:
        logger.error(f"Failed to suggest citations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate citation suggestions: {str(e)}",
        )


@router.post(
    "/expand-outline",
    response_model=OutlineExpansionResponse,
    summary="Expand outline with citations",
    description="Turn a section outline into full paragraphs with appropriate citations",
)
async def expand_outline(request: OutlineExpansionRequest):
    """
    Expand a section outline into full text with citations.

    The agent will:
    1. Search for papers relevant to the outline topics
    2. Generate coherent paragraphs from bullet points
    3. Include appropriate citations throughout
    4. Maintain academic tone and structure

    Returns the expanded section with paragraph-level breakdown.
    """
    try:
        writer_agent = get_writer_agent()

        result = await writer_agent.expand_outline(
            section=request.section,
            outline=request.outline,
            target_length=request.target_length,
            min_citations=request.min_citations,
        )

        # Check if error occurred
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )

        return OutlineExpansionResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to expand outline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to expand outline: {str(e)}",
        )


@router.post(
    "/detect-missing-citations",
    response_model=MissingCitationsResponse,
    summary="Detect missing citations",
    description="Identify claims in text that need citations",
)
async def detect_missing_citations(request: MissingCitationsRequest):
    """
    Detect claims that need citations.

    The agent will:
    1. Analyze the text for factual claims
    2. Identify statements that require citations
    3. Suggest appropriate papers for each claim
    4. Provide revised text with citations

    Returns a list of uncited claims with suggested papers.
    """
    try:
        writer_agent = get_writer_agent()

        uncited_claims = await writer_agent.detect_missing_citations(
            text=request.text
        )

        return MissingCitationsResponse(uncited_claims=uncited_claims)

    except Exception as e:
        logger.error(f"Failed to detect missing citations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect missing citations: {str(e)}",
        )


@router.post(
    "/enhance-citation",
    response_model=EnhanceCitationResponse,
    summary="Enhance existing citation",
    description="Improve how a citation is used in text",
)
async def enhance_citation(request: EnhanceCitationRequest):
    """
    Enhance an existing citation.

    The agent will:
    1. Analyze how the paper is currently cited
    2. Extract key findings from the paper
    3. Suggest ways to strengthen the citation
    4. Provide improved text with more specific details

    Returns enhanced text with better citation integration.
    """
    try:
        writer_agent = get_writer_agent()

        result = await writer_agent.enhance_citation(
            current_text=request.current_text,
            paper_id=request.paper_id,
        )

        # Check if error occurred
        if "error" in result:
            if result["error"] == "Paper not found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Paper not found: {request.paper_id}",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result["error"],
                )

        return EnhanceCitationResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enhance citation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enhance citation: {str(e)}",
        )
