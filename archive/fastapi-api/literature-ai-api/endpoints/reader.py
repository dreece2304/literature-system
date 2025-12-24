"""
Reader agent API endpoints (RAG-powered Q&A).
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.api.schemas import (
    AskQuestionRequest,
    QAResponse,
    SummarizePaperRequest,
    PaperSummaryResponse,
    FindRelatedRequest,
    RelatedPapersResponse,
)
from src.agents.reader import get_reader_agent

router = APIRouter(prefix="/reader", tags=["Reader Agent"])


@router.post(
    "/ask",
    response_model=QAResponse,
    summary="Ask a question about papers",
    description="Get AI-powered answer using RAG over your paper collection",
)
async def ask_question(request: AskQuestionRequest):
    """
    Answer a question using RAG.

    The agent will:
    1. Retrieve relevant paper chunks using semantic search
    2. Use LLM to synthesize answer from retrieved context
    3. Cite specific papers that support the answer
    4. Provide confidence level and limitations

    Only uses information from papers in your collection.
    Never hallucinates or makes up information.
    """
    try:
        reader_agent = get_reader_agent()

        response = await reader_agent.ask(
            question=request.question,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )

        return QAResponse(**response.to_dict())

    except Exception as e:
        logger.error(f"Failed to answer question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to answer question: {str(e)}",
        )


@router.post(
    "/summarize",
    response_model=PaperSummaryResponse,
    summary="Summarize a paper",
    description="Get comprehensive AI-generated summary of a paper",
)
async def summarize_paper(request: SummarizePaperRequest):
    """
    Summarize a paper comprehensively.

    The agent will:
    1. Retrieve all chunks for the paper
    2. Analyze the full content
    3. Extract key information:
       - Research question/problem
       - Methodology
       - Key findings
       - Contributions
       - Limitations
       - Future work

    Returns structured summary with one-sentence overview.
    """
    try:
        reader_agent = get_reader_agent()

        summary = await reader_agent.summarize_paper(
            paper_id=request.paper_id
        )

        return PaperSummaryResponse(**summary.to_dict())

    except ValueError as e:
        logger.warning(f"Paper not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to summarize paper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to summarize paper: {str(e)}",
        )


@router.post(
    "/related",
    response_model=RelatedPapersResponse,
    summary="Find related papers",
    description="Find papers related to a given paper",
)
async def find_related(request: FindRelatedRequest):
    """
    Find papers related to a reference paper.

    The agent will:
    1. Use semantic similarity to find related papers
    2. Group by relationship strength:
       - Highly related (similarity >= 0.8)
       - Moderately related (0.6 <= similarity < 0.8)
       - Somewhat related (similarity < 0.6)
    3. Return papers with similarity scores and excerpts

    Useful for literature review and finding connected research.
    """
    try:
        reader_agent = get_reader_agent()

        result = await reader_agent.find_related_papers(
            paper_id=request.paper_id,
            top_k=request.top_k,
        )

        return RelatedPapersResponse(**result)

    except Exception as e:
        logger.error(f"Failed to find related papers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find related papers: {str(e)}",
        )


@router.get(
    "/stats",
    summary="Get reader statistics",
    description="Get statistics about Q&A usage",
)
async def get_reader_stats():
    """
    Get reader agent statistics.

    Returns:
    - Total questions answered
    - Average confidence
    - Most common topics

    Note: Requires usage tracking to be implemented.
    """
    # TODO: Implement when usage tracking is added
    return {
        "total_questions": 0,
        "average_confidence": 0.0,
        "common_topics": [],
        "note": "Usage tracking not yet implemented",
    }
