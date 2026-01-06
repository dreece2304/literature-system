"""Search Tools for MCP Server.

Provides unified search capabilities with multiple modes.

Architecture:
    MCP Tool (this file) -> UnifiedSearchService -> Various Search Services -> Database

Tools:
    - search: Unified search with modes (smart, keyword, semantic, hybrid)
    - search_by_author: Find papers by author name
    - search_by_tag: Find papers by tag
    - get_search_status: Search system diagnostics

Deprecated (still work but redirect to 'search' internally):
    - smart_search, hybrid_search, keyword_search, semantic_search
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
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
from services.unified_search_service import UnifiedSearchService
from services.search_diagnostics_service import SearchDiagnosticsService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List search tools."""
    return [
        # =================================================================
        # PRIMARY TOOL: Unified Search
        # =================================================================
        Tool(
            name="search",
            description=(
                "Unified search for finding papers in the library. Supports multiple modes:\n"
                "- 'smart' (default): Typo correction, acronym expansion, hybrid search\n"
                "- 'keyword': FTS5 full-text search with BM25 ranking\n"
                "- 'semantic': Embedding-based similarity search\n"
                "- 'hybrid': Balanced keyword + semantic with RRF fusion\n\n"
                "Examples:\n"
                "- search('ALD thin films') - smart search with acronym expansion\n"
                "- search('photoresist', mode='keyword') - exact keyword matching\n"
                "- search('how atoms deposit', mode='semantic') - conceptual search"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language, keywords, or acronyms)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 20,
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["smart", "keyword", "semantic", "hybrid"],
                        "description": (
                            "Search mode: 'smart' (default, recommended), 'keyword' (FTS5), "
                            "'semantic' (embeddings), 'hybrid' (balanced)"
                        ),
                        "default": "smart",
                    },
                    # Smart mode options
                    "correct_spelling": {
                        "type": "boolean",
                        "description": "Auto-correct typos (smart mode)",
                        "default": True,
                    },
                    "expand_acronyms": {
                        "type": "boolean",
                        "description": "Expand acronyms like ALD, EUV (smart mode)",
                        "default": True,
                    },
                    "add_synonyms": {
                        "type": "boolean",
                        "description": "Add synonyms (can increase noise)",
                        "default": False,
                    },
                    # Hybrid options
                    "alpha": {
                        "type": "number",
                        "description": (
                            "Semantic weight for hybrid mode (0-1). "
                            "0=keyword only, 1=semantic only, 0.65=balanced"
                        ),
                        "default": 0.65,
                    },
                    # Semantic options
                    "search_level": {
                        "type": "string",
                        "enum": ["chunk", "paper"],
                        "description": (
                            "Semantic search level: 'chunk' (full-text), 'paper' (title+abstract)"
                        ),
                        "default": "chunk",
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity score (0-1)",
                        "default": 0.35,
                    },
                    # Filters
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
        # =================================================================
        # ENTITY SEARCH TOOLS (kept separate - different input types)
        # =================================================================
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
            description=(
                "Find all papers with a specific tag. By default uses partial matching "
                "(e.g., 'ML' matches 'machine-learning', 'ML-theory'). "
                "Set exact_match=true for exact tag name matching."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Tag name to search for (partial match by default)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 20,
                    },
                    "exact_match": {
                        "type": "boolean",
                        "description": "If true, require exact tag match",
                        "default": False,
                    },
                },
                "required": ["tag"],
            },
        ),
        # =================================================================
        # DIAGNOSTICS
        # =================================================================
        Tool(
            name="get_search_status",
            description=(
                "Get search system health status and diagnostics. Shows FTS5 index status, "
                "ChromaDB vector store status, embedding coverage, and recommendations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "detailed": {
                        "type": "boolean",
                        "description": "If true, return full diagnostics",
                        "default": False,
                    },
                },
            },
        ),
    ]


# ============================================================================
# Tool Implementations
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


async def _search(arguments: dict[str, Any]) -> list[TextContent]:
    """Unified search tool."""
    result = await UnifiedSearchService.search(
        query=arguments["query"],
        limit=arguments.get("limit", 20),
        mode=arguments.get("mode", "smart"),
        correct_spelling=arguments.get("correct_spelling", True),
        expand_acronyms=arguments.get("expand_acronyms", True),
        add_synonyms=arguments.get("add_synonyms", False),
        alpha=arguments.get("alpha", 0.65),
        search_level=arguments.get("search_level", "chunk"),
        min_similarity=arguments.get("min_similarity", 0.35),
        year_min=arguments.get("year_min"),
        year_max=arguments.get("year_max"),
    )

    response_data = search_result(
        results=result.results,
        query=result.query,
        search_type=f"{result.mode}",
    )

    # Add mode-specific metadata
    response_data["mode"] = result.mode
    response_data["strategies_used"] = result.strategies_used

    if result.mode == "smart":
        response_data["query_expansion"] = {
            "spell_corrected": result.spell_corrected,
            "acronyms_expanded": result.acronyms_expanded,
            "final_query": result.final_query,
        }
    elif result.mode == "hybrid":
        response_data["hybrid_info"] = {
            "alpha": result.alpha,
            "keyword_results_count": result.keyword_results_count,
            "semantic_results_count": result.semantic_results_count,
        }
    elif result.mode == "semantic":
        response_data["semantic_info"] = {
            "search_level": result.search_level,
        }

    if result.fallback_used:
        response_data["fallback_used"] = True
        response_data["fallback_reason"] = result.fallback_reason

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
        exact_match=arguments.get("exact_match", False),
    )
    return _to_response(
        search_result(
            results=result.results,
            query=result.query,
            search_type=result.search_type,
        )
    )


def _get_search_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get search system health status and diagnostics."""
    detailed = arguments.get("detailed", False)

    if detailed:
        diagnostics = SearchDiagnosticsService.get_diagnostics()
        return _to_response({
            "success": True,
            "status": "healthy" if not diagnostics.errors else "unhealthy",
            "fts5": {
                "available": diagnostics.fts_available,
                "indexed_count": diagnostics.fts_indexed_count,
                "needs_rebuild": diagnostics.fts_needs_rebuild,
            },
            "vector_store": {
                "available": diagnostics.chromadb_available,
                "paper_count": diagnostics.chromadb_paper_count,
                "chunk_count": diagnostics.chromadb_chunk_count,
            },
            "database": {
                "total_papers": diagnostics.total_papers,
                "papers_with_full_text": diagnostics.papers_with_full_text,
                "papers_with_abstract": diagnostics.papers_with_abstract,
            },
            "embeddings": {
                "papers_with_embeddings": diagnostics.papers_with_embeddings,
                "papers_needing_embeddings": diagnostics.papers_needing_embeddings,
                "coverage_percent": diagnostics.embedding_coverage_percent,
                "model_loaded": diagnostics.embedding_model_loaded,
                "model_name": diagnostics.embedding_model_name,
            },
            "warnings": diagnostics.warnings,
            "errors": diagnostics.errors,
            "recommendations": diagnostics.recommendations,
            "check_time": diagnostics.check_time.isoformat(),
        })
    else:
        return _to_response(SearchDiagnosticsService.get_search_health())


# ============================================================================
# Main entry point
# ============================================================================


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a search tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    sync_tool_map = {
        "search_by_author": _search_by_author,
        "search_by_tag": _search_by_tag,
        "get_search_status": _get_search_status,
    }

    async_tool_map = {
        "search": _search,
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
