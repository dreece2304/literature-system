"""
Triager agent API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.api.schemas import (
    ScorePaperRequest,
    PaperScoreResponse,
    ScoreBatchRequest,
    ScoreBatchResponse,
    ComparePapersRequest,
    ComparePapersResponse,
    TopPapersResponse,
)
from src.agents.triager import get_triager_agent

router = APIRouter(prefix="/triager", tags=["Triager Agent"])


@router.post(
    "/score-paper",
    response_model=PaperScoreResponse,
    summary="Score a single paper",
    description="Evaluate paper relevance on 0-10 scale with detailed breakdown",
)
async def score_paper(request: ScorePaperRequest):
    """
    Score a single paper for relevance.

    The agent will:
    1. Retrieve paper details (title, abstract, etc.)
    2. Evaluate relevance to research interests
    3. Score on 0-10 scale with dimensional breakdown
    4. Provide actionable recommendation (must_read, should_read, skim, skip)

    Returns detailed score with justification and key takeaways.
    """
    try:
        triager_agent = get_triager_agent()

        score = await triager_agent.score_paper(
            paper_id=request.paper_id,
            research_interests=request.research_interests,
            current_projects=request.current_projects,
            preferred_methods=request.preferred_methods,
            context_id=request.context_id,
        )

        return PaperScoreResponse(**score.to_dict())

    except Exception as e:
        logger.error(f"Failed to score paper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to score paper: {str(e)}",
        )


@router.post(
    "/score-batch",
    response_model=ScoreBatchResponse,
    summary="Score multiple papers",
    description="Batch score papers and rank by relevance",
)
async def score_batch(request: ScoreBatchRequest):
    """
    Score multiple papers in batch.

    The agent will:
    1. Retrieve details for all papers
    2. Evaluate each for relevance
    3. Rank papers by score
    4. Provide summary statistics

    Efficiently processes up to 50 papers at once.
    Returns scores sorted by relevance (highest first).
    """
    try:
        triager_agent = get_triager_agent()

        result = await triager_agent.score_batch(
            paper_ids=request.paper_ids,
            research_interests=request.research_interests,
            current_projects=request.current_projects,
            max_papers=request.max_papers,
        )

        return ScoreBatchResponse(**result.to_dict())

    except Exception as e:
        logger.error(f"Failed to score batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to score batch: {str(e)}",
        )


@router.post(
    "/compare-papers",
    response_model=ComparePapersResponse,
    summary="Compare two papers",
    description="Compare relevance of two papers to a research goal",
)
async def compare_papers(request: ComparePapersRequest):
    """
    Compare two papers for relevance to a research goal.

    The agent will:
    1. Evaluate both papers against the goal
    2. Identify unique contributions of each
    3. Assess complementary value
    4. Recommend reading priority

    Useful for choosing between similar papers.
    """
    try:
        triager_agent = get_triager_agent()

        result = await triager_agent.compare_papers(
            paper_id_a=request.paper_id_a,
            paper_id_b=request.paper_id_b,
            research_goal=request.research_goal,
        )

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"],
            )

        return ComparePapersResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compare papers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare papers: {str(e)}",
        )


@router.get(
    "/top-papers",
    response_model=TopPapersResponse,
    summary="Get top-scored papers",
    description="Retrieve papers with highest relevance scores",
)
async def get_top_papers(
    min_score: int = 7,
    limit: int = 10,
    context_id: str = "default"
):
    """
    Get top-scored papers.

    Note: This feature requires papers to have been scored previously.
    Scores are stored in the database and retrieved here.

    Returns papers sorted by score (highest first).
    """
    try:
        triager_agent = get_triager_agent()

        papers = await triager_agent.get_top_papers(
            min_score=min_score,
            limit=limit,
            context_id=context_id,
        )

        return TopPapersResponse(
            papers=papers,
            total=len(papers),
        )

    except Exception as e:
        logger.error(f"Failed to get top papers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get top papers: {str(e)}",
        )


@router.get(
    "/stats",
    summary="Get triager statistics",
    description="Get statistics about scored papers",
)
async def get_triager_stats(context_id: Optional[str] = None):
    """
    Get triager statistics.

    Returns:
    - Total papers scored
    - Score distribution
    - Most common actions
    - Context information

    Args:
        context_id: Optional research context filter
    """
    try:
        triager_agent = get_triager_agent()

        # Get stats from score storage
        stats = triager_agent.score_storage.get_stats(context_id=context_id)

        # Get available contexts
        contexts = triager_agent.score_storage.get_contexts()

        return {
            **stats,
            "available_contexts": contexts,
        }

    except Exception as e:
        logger.error(f"Failed to get triager stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get triager stats: {str(e)}",
        )
