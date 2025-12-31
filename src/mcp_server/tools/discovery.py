"""Discovery Tools for MCP Server.

Provides paper discovery and similarity search capabilities.
Helps users find related papers, suggest citations, and explore the library.

Architecture:
    MCP Tool (this file) -> SearchService -> ChromaDB/SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (  # noqa: E402
    get_logger,
    search_result,
    error,
    success,
    SearchError,
    PaperNotFoundError,
    LiteratureError,
)
from services import SearchService, PaperService  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List discovery tools."""
    return [
        Tool(
            name="find_similar_papers",
            description=(
                "Find papers similar to a given paper based on semantic similarity. "
                "Uses embeddings to find papers with related content, topics, or methods."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to find similar papers for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar papers to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity score (0-1)",
                        "default": 0.5,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="find_papers_like_text",
            description=(
                "Find papers matching a free-form text description. "
                "Useful for finding papers relevant to a research question, concept, "
                "or paragraph of text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Text description to match against papers. Can be a "
                            "research question, concept description, or paragraph."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of papers to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity score (0-1)",
                        "default": 0.5,
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="suggest_citations_for_text",
            description=(
                "Suggest papers to cite for a given text snippet. "
                "Searches the library for papers relevant to the text that could "
                "serve as supporting citations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text snippet that needs citations",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of citation suggestions",
                        "default": 5,
                    },
                    "include_bibtex": {
                        "type": "boolean",
                        "description": "Include BibTeX entry for each suggestion",
                        "default": False,
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="get_reading_queue",
            description=(
                "Get reading queue of unread papers. "
                "Returns papers sorted by rating (highest first) and date added."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 20,
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag",
                    },
                    "min_rating": {
                        "type": "integer",
                        "description": "Minimum rating (1-5) to include",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
            },
        ),
        Tool(
            name="suggest_paper_tags",
            description=(
                "Suggest tags for a paper based on similar papers' tags. "
                "Analyzes related papers to recommend relevant tags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to suggest tags for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tag suggestions",
                        "default": 5,
                    },
                },
                "required": ["paper_id"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


async def _find_similar_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Find papers similar to a given paper."""
    paper_id = arguments["paper_id"]
    limit = arguments.get("limit", 10)
    min_similarity = arguments.get("min_similarity", 0.5)

    result = await SearchService.find_similar_papers(
        paper_id=paper_id,
        limit=limit,
        min_similarity=min_similarity,
    )

    return _to_response(
        search_result(
            results=result.results,
            query=result.query,
            search_type=result.search_type,
        )
    )


async def _find_papers_like_text(arguments: dict[str, Any]) -> list[TextContent]:
    """Find papers matching free-form text."""
    text = arguments["text"]
    limit = arguments.get("limit", 10)
    min_similarity = arguments.get("min_similarity", 0.5)

    result = await SearchService.find_papers_like_text(
        text=text,
        limit=limit,
        min_similarity=min_similarity,
    )

    return _to_response(
        search_result(
            results=result.results,
            query=text[:100] + "..." if len(text) > 100 else text,
            search_type=result.search_type,
        )
    )


async def _suggest_citations_for_text(arguments: dict[str, Any]) -> list[TextContent]:
    """Suggest papers to cite for text."""
    from services.citation_service import CitationService

    text = arguments["text"]
    limit = arguments.get("limit", 5)
    include_bibtex = arguments.get("include_bibtex", False)

    result = await SearchService.suggest_citations_for_text(
        text=text,
        limit=limit,
    )

    suggestions = result.results

    # Add BibTeX if requested
    if include_bibtex and suggestions:
        paper_ids = [s["id"] for s in suggestions]
        papers_data = [PaperService.get(pid) for pid in paper_ids if pid]
        valid_papers = [p for p in papers_data if p]

        if valid_papers:
            bibtex_entries = CitationService.generate_bibtex(valid_papers)
            # Parse and attach to each suggestion
            for suggestion in suggestions:
                for entry in bibtex_entries:
                    if entry.get("paper_id") == suggestion["id"]:
                        suggestion["bibtex"] = entry.get("bibtex", "")
                        suggestion["citation_key"] = entry.get("key", "")
                        break

    return _to_response(
        search_result(
            results=suggestions,
            query=text[:100] + "..." if len(text) > 100 else text,
            search_type="citation_suggestion",
        )
    )


def _get_reading_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get reading queue of unread papers."""
    from literature_core import get_session, Paper, Tag
    from sqlalchemy.orm import joinedload
    from sqlalchemy import desc, nullslast

    limit = arguments.get("limit", 20)
    tag_filter = arguments.get("tag")
    min_rating = arguments.get("min_rating")

    with get_session() as session:
        query = (
            session.query(Paper)
            .options(joinedload(Paper.authors), joinedload(Paper.tags))
            .filter(Paper.read_status == "unread")
        )

        # Filter by minimum rating
        if min_rating:
            query = query.filter(Paper.rating >= min_rating)

        # Filter by tag
        if tag_filter:
            query = query.join(Paper.tags).filter(Tag.name == tag_filter)

        # Order by rating (highest first, nulls last), then by date added
        query = query.order_by(
            nullslast(desc(Paper.rating)),
            desc(Paper.date_added)
        )

        papers = query.limit(limit).all()

        results = []
        for paper in papers:
            result = SearchService.paper_to_result(paper)
            result["rating"] = paper.rating
            results.append(result)

    return _to_response(
        success({
            "count": len(results),
            "papers": results,
            "filters": {
                "tag": tag_filter,
                "min_rating": min_rating,
            },
        })
    )


async def _suggest_paper_tags(arguments: dict[str, Any]) -> list[TextContent]:
    """Suggest tags for a paper based on similar papers."""
    paper_id = arguments["paper_id"]
    limit = arguments.get("limit", 5)

    # Get similar papers
    similar = await SearchService.find_similar_papers(
        paper_id=paper_id,
        limit=20,  # Get more papers for tag analysis
        min_similarity=0.4,
    )

    if not similar.results:
        return _to_response(
            success({
                "paper_id": paper_id,
                "suggestions": [],
                "message": "No similar papers found for tag suggestions",
            })
        )

    # Count tags from similar papers
    tag_counts: dict[str, int] = {}
    for paper in similar.results:
        for tag in paper.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Get current paper's tags to exclude
    current_paper = PaperService.get(paper_id)
    current_tags = set(current_paper.get("tags", [])) if current_paper else set()

    # Sort by frequency and exclude current tags
    sorted_tags = sorted(
        [(tag, count) for tag, count in tag_counts.items() if tag not in current_tags],
        key=lambda x: x[1],
        reverse=True,
    )[:limit]

    return _to_response(
        success({
            "paper_id": paper_id,
            "suggestions": [
                {"tag": tag, "frequency": count, "source_papers": count}
                for tag, count in sorted_tags
            ],
            "based_on_papers": len(similar.results),
        })
    )


# ============================================================================
# Main entry point
# ============================================================================

async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a discovery tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    # Sync tools
    sync_tools = {
        "get_reading_queue": _get_reading_queue,
    }

    # Async tools
    async_tools = {
        "find_similar_papers": _find_similar_papers,
        "find_papers_like_text": _find_papers_like_text,
        "suggest_citations_for_text": _suggest_citations_for_text,
        "suggest_paper_tags": _suggest_paper_tags,
    }

    if name not in sync_tools and name not in async_tools:
        return _to_response(error(f"Unknown discovery tool: {name}", code="UNKNOWN_TOOL"))

    try:
        if name in async_tools:
            return await async_tools[name](arguments)
        return sync_tools[name](arguments)

    except PaperNotFoundError as e:
        logger.error(f"Paper not found: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except SearchError as e:
        logger.error(f"Search error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
