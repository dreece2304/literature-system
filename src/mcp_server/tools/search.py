"""Search Tools for MCP Server.

Provides keyword and semantic search capabilities.
This module is a thin wrapper over SearchService.

Architecture:
    MCP Tool (this file) -> SearchService -> SQLAlchemy/ChromaDB -> Database
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# search.py is at src/mcp_server/tools/search.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    search_result,
    error,
    SearchError,
    LiteratureError,
)
from services import SearchService
from services.hybrid_search_service import HybridSearchService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List search tools."""
    return [
        Tool(
            name="hybrid_search",
            description=(
                "Advanced search combining keyword (BM25) and semantic search with "
                "Reciprocal Rank Fusion. Best for comprehensive literature discovery. "
                "Falls back gracefully if semantic search unavailable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language or keywords)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 20,
                    },
                    "alpha": {
                        "type": "number",
                        "description": (
                            "Semantic weight (0-1). 0.65=balanced (default), "
                            "0=keyword only, 1=semantic only"
                        ),
                        "default": 0.65,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity for semantic results (0.35 recommended)",
                        "default": 0.35,
                    },
                    "year_min": {
                        "type": "integer",
                        "description": "Minimum publication year",
                    },
                    "year_max": {
                        "type": "integer",
                        "description": "Maximum publication year",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="keyword_search",
            description=(
                "Full-text keyword search across papers. Searches title, abstract, "
                "and full text using SQLite FTS5 with BM25 ranking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keywords, phrases)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10,
                    },
                    "year_min": {
                        "type": "integer",
                        "description": "Minimum publication year",
                    },
                    "year_max": {
                        "type": "integer",
                        "description": "Maximum publication year",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="semantic_search",
            description=(
                "Semantic similarity search using embeddings. Finds papers with "
                "similar meaning/concepts to your query, even if exact keywords "
                "don't match. Supports two search levels:\n"
                "- 'chunk': Searches full-text chunks to find content in paper body\n"
                "- 'paper': Searches title+abstract embeddings only (faster)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language query describing what you're looking for. "
                            "Can be a research question, topic description, or concept."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity score (0-1)",
                        "default": 0.5,
                    },
                    "search_level": {
                        "type": "string",
                        "enum": ["chunk", "paper"],
                        "description": (
                            "'chunk' to search full-text (finds content in paper body), "
                            "'paper' to search title+abstract only. Default: 'chunk'"
                        ),
                        "default": "chunk",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_by_author",
            description="Find all papers by a specific author",
            inputSchema={
                "type": "object",
                "properties": {
                    "author_name": {
                        "type": "string",
                        "description": "Author name (partial match supported)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 20,
                    },
                },
                "required": ["author_name"],
            },
        ),
        Tool(
            name="search_by_tag",
            description="Find all papers with a specific tag",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Tag name to search for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 20,
                    },
                },
                "required": ["tag"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations - Thin wrappers over SearchService
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _keyword_search(arguments: dict[str, Any]) -> list[TextContent]:
    """Full-text keyword search."""
    result = SearchService.keyword_search(
        query=arguments["query"],
        limit=arguments.get("limit", 10),
        year_min=arguments.get("year_min"),
        year_max=arguments.get("year_max"),
    )
    return _to_response(
        search_result(
            results=result.results,
            query=result.query,
            search_type=result.search_type,
        )
    )


async def _semantic_search(arguments: dict[str, Any]) -> list[TextContent]:
    """Semantic similarity search using embeddings."""
    result = await SearchService.semantic_search(
        query=arguments["query"],
        limit=arguments.get("limit", 10),
        min_similarity=arguments.get("min_similarity", 0.5),
        search_level=arguments.get("search_level", "chunk"),
    )

    # Build response with optional chunk information
    response_data = search_result(
        results=result.results,
        query=result.query,
        search_type=result.search_type,
    )

    # Add chunk stats if available
    if result.matching_chunks:
        response_data["chunk_matches"] = len(result.matching_chunks)

    return _to_response(response_data)


def _search_by_author(arguments: dict[str, Any]) -> list[TextContent]:
    """Search papers by author name."""
    result = SearchService.search_by_author(
        author_name=arguments["author_name"],
        limit=arguments.get("limit", 20),
    )
    return _to_response(
        search_result(
            results=result.results,
            query=result.query,
            search_type=result.search_type,
        )
    )


def _search_by_tag(arguments: dict[str, Any]) -> list[TextContent]:
    """Search papers by tag."""
    result = SearchService.search_by_tag(
        tag_name=arguments["tag"],
        limit=arguments.get("limit", 20),
    )
    return _to_response(
        search_result(
            results=result.results,
            query=result.query,
            search_type=result.search_type,
        )
    )


async def _hybrid_search(arguments: dict[str, Any]) -> list[TextContent]:
    """Hybrid search combining keyword and semantic search."""
    result = await HybridSearchService.search(
        query=arguments["query"],
        limit=arguments.get("limit", 20),
        alpha=arguments.get("alpha", 0.65),
        min_similarity=arguments.get("min_similarity", 0.35),
        year_min=arguments.get("year_min"),
        year_max=arguments.get("year_max"),
    )

    # Build response with diagnostics
    response_data = search_result(
        results=result.results,
        query=result.query,
        search_type="hybrid",
    )

    # Add hybrid-specific metadata
    response_data["alpha"] = result.alpha
    response_data["search_modes"] = result.search_modes
    response_data["diagnostics"] = {
        "fts_available": result.diagnostics.fts_available,
        "semantic_available": result.diagnostics.semantic_available,
        "keyword_results_count": result.diagnostics.keyword_results_count,
        "semantic_results_count": result.diagnostics.semantic_results_count,
        "merged_count": result.diagnostics.merged_count,
        "fallback_used": result.diagnostics.fallback_used,
        "warnings": result.diagnostics.warnings,
    }

    if result.diagnostics.fallback_reason:
        response_data["diagnostics"]["fallback_reason"] = result.diagnostics.fallback_reason

    return _to_response(response_data)


# ============================================================================
# Main entry point
# ============================================================================

# Async tool names that require await
ASYNC_TOOLS = {"semantic_search", "hybrid_search"}


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a search tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    sync_tool_map = {
        "keyword_search": _keyword_search,
        "search_by_author": _search_by_author,
        "search_by_tag": _search_by_tag,
    }

    async_tool_map = {
        "semantic_search": _semantic_search,
        "hybrid_search": _hybrid_search,
    }

    all_tools = set(sync_tool_map.keys()) | set(async_tool_map.keys())

    if name not in all_tools:
        return _to_response(error(f"Unknown search tool: {name}", code="UNKNOWN_TOOL"))

    try:
        if name in async_tool_map:
            return await async_tool_map[name](arguments)
        return sync_tool_map[name](arguments)

    except SearchError as e:
        logger.error(f"Search error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
