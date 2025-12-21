"""
Context management API endpoints.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.api.schemas import (
    LoadManuscriptRequest,
    LoadManuscriptResponse,
    ManuscriptInfo,
    UpdateContextRequest,
    ContextResponse,
)
from src.context.detector import get_context_detector

router = APIRouter(prefix="/context", tags=["Context Management"])


@router.post(
    "/load-manuscript",
    response_model=LoadManuscriptResponse,
    summary="Load a manuscript",
    description="Load and parse a manuscript file (LaTeX or Markdown)",
)
async def load_manuscript(request: LoadManuscriptRequest):
    """
    Load a manuscript for context tracking.

    Supports:
    - LaTeX (.tex) files
    - Markdown (.md, .markdown) files

    The service will:
    1. Parse the manuscript structure
    2. Extract sections, citations, and metadata
    3. Set as active manuscript if requested
    4. Enable context-aware citation suggestions

    Returns manuscript information and parsing status.
    """
    try:
        detector = get_context_detector()
        manuscript_path = Path(request.manuscript_path)

        # Load manuscript
        context = detector.load_manuscript(
            manuscript_path=manuscript_path,
            set_active=request.set_active,
        )

        if not context:
            return LoadManuscriptResponse(
                success=False,
                manuscript=None,
                error=f"Failed to parse manuscript: {manuscript_path}",
            )

        # Build response
        manuscript_info = ManuscriptInfo(
            manuscript_path=str(manuscript_path),
            title=context.structure.title,
            active_section=context.active_section,
            total_sections=len(context.structure.sections),
            total_words=context.structure.total_words,
            total_citations=len(context.structure.all_citations),
            last_updated=context.last_updated.isoformat(),
        )

        return LoadManuscriptResponse(
            success=True,
            manuscript=manuscript_info,
        )

    except Exception as e:
        logger.error(f"Failed to load manuscript: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load manuscript: {str(e)}",
        )


@router.post(
    "/update",
    summary="Update writing context",
    description="Update the current writing context (section, cursor position, etc.)",
)
async def update_context(request: UpdateContextRequest):
    """
    Update writing context.

    Allows updating:
    - Active section being written
    - Cursor position in manuscript
    - Recent text being edited
    - Writing goals
    - Research topics

    This helps the agent provide more context-aware suggestions.
    """
    try:
        detector = get_context_detector()

        if request.active_section is not None:
            detector.set_active_section(request.active_section)

        if request.cursor_line is not None:
            detector.update_cursor_position(request.cursor_line)

        if request.recent_text is not None:
            detector.update_recent_text(request.recent_text)

        if request.writing_goal is not None:
            detector.set_writing_goal(request.writing_goal)

        if request.research_topics is not None:
            detector.set_research_topics(request.research_topics)

        return {"success": True, "message": "Context updated"}

    except Exception as e:
        logger.error(f"Failed to update context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update context: {str(e)}",
        )


@router.get(
    "/current",
    response_model=ContextResponse,
    summary="Get current context",
    description="Get the current writing context",
)
async def get_current_context():
    """
    Get current writing context.

    Returns information about:
    - Active manuscript and section
    - Recent text being edited
    - Existing citations
    - Writing goals and topics

    Returns null/empty if no manuscript is loaded.
    """
    try:
        detector = get_context_detector()
        context_data = detector.get_context_for_citation()

        if not context_data:
            # No active manuscript
            return ContextResponse(
                manuscript_title=None,
                active_section=None,
                section_content="",
                recent_text="",
                existing_citations=[],
                section_citations=[],
                writing_goal=None,
                research_topics=[],
            )

        return ContextResponse(**context_data)

    except Exception as e:
        logger.error(f"Failed to get context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context: {str(e)}",
        )


@router.get(
    "/outline",
    summary="Get manuscript outline",
    description="Get the outline/structure of the active manuscript",
)
async def get_manuscript_outline():
    """
    Get manuscript outline.

    Returns:
    - Manuscript title
    - Section hierarchy
    - Word counts per section
    - Citation counts per section

    Useful for understanding manuscript structure.
    """
    try:
        detector = get_context_detector()
        outline = detector.get_manuscript_outline()

        if not outline:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active manuscript",
            )

        return outline

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get outline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get outline: {str(e)}",
        )


@router.post(
    "/refresh",
    summary="Refresh manuscript",
    description="Reload the manuscript from disk (if it was edited)",
)
async def refresh_manuscript():
    """
    Refresh manuscript from disk.

    Useful after:
    - Editing the manuscript in external editor
    - Adding new sections
    - Updating citations

    Re-parses the file and updates context.
    """
    try:
        detector = get_context_detector()
        updated_files = detector.check_for_updates()

        return {
            "success": True,
            "updated_files": [str(f) for f in updated_files],
            "count": len(updated_files),
        }

    except Exception as e:
        logger.error(f"Failed to refresh manuscript: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh manuscript: {str(e)}",
        )


@router.get(
    "/stats",
    summary="Get context statistics",
    description="Get statistics about tracked manuscripts",
)
async def get_context_stats():
    """
    Get context tracking statistics.

    Returns:
    - Number of tracked manuscripts
    - Active manuscript name
    - Context details

    Useful for monitoring and debugging.
    """
    try:
        detector = get_context_detector()
        stats = detector.get_stats()

        return stats

    except Exception as e:
        logger.error(f"Failed to get context stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context stats: {str(e)}",
        )
