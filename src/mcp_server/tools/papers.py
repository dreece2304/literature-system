"""Paper Management Tools for MCP Server.

These tools provide CRUD operations and content access for papers.
This module is a thin wrapper over PaperService, handling MCP-specific
serialization and error formatting.

Architecture:
    MCP Tool (this file) -> PaperService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# papers.py is at src/mcp_server/tools/papers.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    success,
    error,
    paginated,
    created,
    batch_result,
    search_result,
    PaperNotFoundError,
    ValidationError,
    LiteratureError,
)
from services import PaperService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List paper management tools."""
    return [
        Tool(
            name="list_papers",
            description="List papers with optional filtering and pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return (default: 20, max: 500)",
                        "default": 20,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of papers to skip for pagination",
                        "default": 0,
                    },
                    "author": {
                        "type": "string",
                        "description": "Filter by author name (partial match)",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Filter by publication year",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag name",
                    },
                    "read_status": {
                        "type": "string",
                        "enum": ["unread", "reading", "read"],
                        "description": "Filter by read status",
                    },
                },
            },
        ),
        Tool(
            name="get_paper",
            description="Get detailed information about a specific paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "The paper's unique ID",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="search_papers",
            description="Search papers by title, abstract, or full text",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (searches title, abstract, full text)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="add_paper",
            description="Add a new paper to the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Paper title (required)",
                    },
                    "abstract": {
                        "type": "string",
                        "description": "Paper abstract",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Publication year",
                    },
                    "doi": {
                        "type": "string",
                        "description": "Digital Object Identifier",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv identifier",
                    },
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of author names",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags",
                    },
                    "journal": {
                        "type": "string",
                        "description": "Journal name",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="update_paper",
            description="Update an existing paper's metadata",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to update",
                    },
                    "title": {"type": "string"},
                    "abstract": {"type": "string"},
                    "year": {"type": "integer"},
                    "doi": {"type": "string"},
                    "rating": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "read_status": {
                        "type": "string",
                        "enum": ["unread", "reading", "read"],
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_paper_content",
            description=(
                "Get paper content for AI analysis (title, abstract, full text). "
                "Use max_chars to limit full text length for long papers. "
                "Use include_full_text=false to get only title and abstract."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to get content for",
                    },
                    "include_full_text": {
                        "type": "boolean",
                        "description": "Include full text content (default: true)",
                        "default": True,
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": (
                            "Maximum characters for full text. "
                            "Use 0 for unlimited. Default: 50000 (~12K tokens)"
                        ),
                        "default": 50000,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Start position in full text for pagination",
                        "default": 0,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="store_extraction",
            description="Store AI-extracted content (summary, findings, etc.) for a paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID",
                    },
                    "paper_type": {
                        "type": "string",
                        "description": "Type: research_article, review, conference, etc.",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Identified topics/themes",
                    },
                    "one_sentence_summary": {
                        "type": "string",
                        "description": "One sentence summary of the paper",
                    },
                    "key_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key findings from the paper",
                    },
                    "methodology_summary": {
                        "type": "string",
                        "description": "Summary of methodology used",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_extraction_queue",
            description="Get papers that need AI extraction (missing summaries/analysis)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="batch_update_papers",
            description="Bulk update tags, read_status, or rating for multiple papers",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to update",
                    },
                    "tags_to_add": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add to all papers",
                    },
                    "tags_to_remove": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to remove from all papers",
                    },
                    "read_status": {
                        "type": "string",
                        "enum": ["unread", "reading", "read"],
                        "description": "Set read status for all papers",
                    },
                    "rating": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Set rating for all papers",
                    },
                },
                "required": ["paper_ids"],
            },
        ),
        Tool(
            name="batch_delete_papers",
            description="Bulk delete papers (requires confirmation)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to delete",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to execute deletion",
                    },
                },
                "required": ["paper_ids", "confirm"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations - Thin wrappers over PaperService
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _list_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """List papers with filtering and pagination."""
    result = PaperService.list(
        limit=arguments.get("limit", 20),
        offset=arguments.get("offset", 0),
        author=arguments.get("author"),
        year=arguments.get("year"),
        tag=arguments.get("tag"),
        read_status=arguments.get("read_status"),
    )
    return _to_response(
        paginated(
            items=result.papers,
            total=result.total,
            limit=result.limit,
            offset=result.offset,
        )
    )


def _get_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Get a paper by ID."""
    paper = PaperService.get(arguments["paper_id"])
    return _to_response(success(paper))


def _search_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Search papers by query."""
    query = arguments["query"]
    limit = arguments.get("limit", 10)
    results = PaperService.search(query, limit=limit)
    return _to_response(
        search_result(
            results=results,
            query=query,
            search_type="keyword",
        )
    )


def _add_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Add a new paper."""
    paper = PaperService.create(
        title=arguments["title"],
        abstract=arguments.get("abstract"),
        year=arguments.get("year"),
        doi=arguments.get("doi"),
        arxiv_id=arguments.get("arxiv_id"),
        journal=arguments.get("journal"),
        authors=arguments.get("authors"),
        tags=arguments.get("tags"),
    )
    return _to_response(
        created(paper, message=f"Paper created with ID: {paper['id']}")
    )


def _update_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing paper."""
    paper_id = arguments.pop("paper_id")
    paper = PaperService.update(
        paper_id=paper_id,
        title=arguments.get("title"),
        abstract=arguments.get("abstract"),
        year=arguments.get("year"),
        doi=arguments.get("doi"),
        rating=arguments.get("rating"),
        read_status=arguments.get("read_status"),
        tags=arguments.get("tags"),
    )
    return _to_response(success(paper, message=f"Paper {paper_id} updated"))


def _get_paper_content(arguments: dict[str, Any]) -> list[TextContent]:
    """Get paper content for AI analysis with optional truncation."""
    paper_id = arguments["paper_id"]
    include_full_text = arguments.get("include_full_text", True)
    max_chars = arguments.get("max_chars", 50000)
    offset = arguments.get("offset", 0)

    content = PaperService.get_content(paper_id)

    # Handle full text truncation/pagination
    full_text = content.get("full_text")
    truncation_info = None

    if not include_full_text:
        content["full_text"] = None
        truncation_info = {"included": False, "reason": "include_full_text=false"}
    elif full_text:
        total_len = len(full_text)

        # Apply offset
        if offset > 0:
            full_text = full_text[offset:]

        # Apply max_chars limit (0 = unlimited)
        if max_chars > 0 and len(full_text) > max_chars:
            content["full_text"] = full_text[:max_chars]
            truncation_info = {
                "truncated": True,
                "total_chars": total_len,
                "returned_chars": max_chars,
                "offset": offset,
                "next_offset": offset + max_chars,
                "remaining_chars": total_len - offset - max_chars,
            }
        elif offset > 0:
            content["full_text"] = full_text
            truncation_info = {
                "truncated": False,
                "total_chars": total_len,
                "returned_chars": len(full_text),
                "offset": offset,
            }

    if truncation_info:
        content["_truncation"] = truncation_info

    return _to_response(success(content))


def _store_extraction(arguments: dict[str, Any]) -> list[TextContent]:
    """Store AI-extracted content for a paper."""
    paper_id = arguments.pop("paper_id")
    PaperService.store_extraction(
        paper_id=paper_id,
        paper_type=arguments.get("paper_type"),
        topics=arguments.get("topics"),
        one_sentence_summary=arguments.get("one_sentence_summary"),
        key_findings=arguments.get("key_findings"),
        methodology_summary=arguments.get("methodology_summary"),
    )
    return _to_response(
        success({"paper_id": paper_id}, message=f"Extraction stored for paper {paper_id}")
    )


def _get_extraction_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers that need AI extraction."""
    limit = arguments.get("limit", 20)
    papers = PaperService.get_extraction_queue(limit=limit)
    return _to_response(
        success({"count": len(papers), "papers": papers})
    )


def _batch_update_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Bulk update multiple papers."""
    result = PaperService.batch_update(
        paper_ids=arguments["paper_ids"],
        tags_to_add=arguments.get("tags_to_add"),
        tags_to_remove=arguments.get("tags_to_remove"),
        read_status=arguments.get("read_status"),
        rating=arguments.get("rating"),
    )
    return _to_response(
        batch_result(
            processed=[{"id": pid} for pid in result.processed],
            failed=result.failed,
            message=f"Updated {len(result.processed)} papers",
        )
    )


def _batch_delete_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Bulk delete papers."""
    paper_ids = arguments["paper_ids"]
    confirm = arguments.get("confirm", False)

    if not confirm:
        return _to_response(
            error(
                "Deletion requires confirm=true",
                code="CONFIRMATION_REQUIRED",
                details={"paper_ids": paper_ids},
            )
        )

    result = PaperService.batch_delete(paper_ids)
    return _to_response(
        batch_result(
            processed=[{"id": pid} for pid in result.processed],
            failed=result.failed,
            message=f"Deleted {len(result.processed)} papers",
        )
    )


# ============================================================================
# Main entry point
# ============================================================================

async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a paper tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "list_papers": _list_papers,
        "get_paper": _get_paper,
        "search_papers": _search_papers,
        "add_paper": _add_paper,
        "update_paper": _update_paper,
        "get_paper_content": _get_paper_content,
        "store_extraction": _store_extraction,
        "get_extraction_queue": _get_extraction_queue,
        "batch_update_papers": _batch_update_papers,
        "batch_delete_papers": _batch_delete_papers,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown paper tool: {name}", code="UNKNOWN_TOOL"))

    try:
        return tool_map[name](arguments)

    except PaperNotFoundError as e:
        logger.warning(f"Paper not found: {e.paper_id}")
        return _to_response(
            error(str(e), code=e.code, details={"paper_id": e.paper_id})
        )

    except ValidationError as e:
        logger.warning(f"Validation error: {e.message}")
        return _to_response(
            error(str(e), code=e.code, details={"field": e.field})
        )

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
