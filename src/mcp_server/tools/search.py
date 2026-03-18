"""Search Tools for MCP Server.

Provides unified search capabilities with multiple modes.

Architecture:
    MCP Tool (this file) -> UnifiedSearchService -> Various Search Services -> Database

Tools:
    - search: Unified search with modes (smart, keyword, semantic, hybrid)
    - get_search_status: Search system diagnostics

Note: search_by_author and search_by_tag removed - use list_papers(author=X) or list_papers(tag=X)
"""
from __future__ import annotations

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
    serialize,
    SearchError,
    LiteratureError,
)
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
            description="Search papers. Modes: smart (default), keyword (FTS5), semantic, hybrid, exact",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (natural language, keywords, or acronyms)"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum results to return"},
                    "mode": {"type": "string", "enum": ["smart", "keyword", "semantic", "hybrid", "exact"], "default": "smart", "description": "Search mode: 'smart' (default, recommended), 'keyword' (FTS5), 'semantic' (embeddings), 'hybrid' (balanced), 'exact' (fast known-paper lookup)"},
                    "correct_spelling": {"type": "boolean", "default": True, "description": "Auto-correct typos (smart mode)"},
                    "expand_acronyms": {"type": "boolean", "default": True, "description": "Expand acronyms like ALD, EUV (smart mode)"},
                    "add_synonyms": {"type": "boolean", "default": False, "description": "Add synonyms (can increase noise)"},
                    "alpha": {"type": "number", "default": 0.65, "description": "Semantic weight for hybrid mode (0-1). 0=keyword only, 1=semantic only, 0.65=balanced"},
                    "search_level": {"type": "string", "enum": ["chunk", "paper"], "default": "chunk", "description": "Semantic search level: 'chunk' (full-text), 'paper' (title+abstract)"},
                    "min_similarity": {"type": "number", "default": 0.35, "description": "Minimum similarity score (0-1)"},
                    "rerank": {"type": "boolean", "description": "Enable cross-encoder re-ranking for better precision. If not specified, uses the setting default (RERANKER_ENABLED)."},
                    "year_min": {"type": "integer", "description": "Minimum publication year"},
                    "year_max": {"type": "integer", "description": "Maximum publication year"},
                    "include_summary": {"type": "boolean", "default": False, "description": "Include one_sentence_summary and paper_type from extractions. Useful for browsing results without separate get_paper_content calls."},
                },
                "required": ["query"],
            },
        ),
        # =================================================================
        # DIAGNOSTICS
        # =================================================================
        Tool(
            name="get_search_status",
            description="Search system health (FTS5, ChromaDB, embedding coverage)",
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


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


def _enrich_with_summaries(results: list[dict]) -> list[dict]:
    """Batch-enrich search results with extraction summaries.

    Efficiently fetches one_sentence_summary and paper_type for all results
    in a single database query.

    Args:
        results: List of search result dicts with 'id' field

    Returns:
        Results with added 'summary' and 'paper_type' fields
    """
    if not results:
        return results

    from literature_core import get_session
    from literature_core.models import PaperContent

    paper_ids = [r["id"] for r in results if "id" in r]

    with get_session() as session:
        contents = session.query(
            PaperContent.paper_id,
            PaperContent.one_sentence_summary,
            PaperContent.paper_type,
            PaperContent.topics,
            PaperContent.deep_one_sentence_summary,
            PaperContent.deep_paper_type,
        ).filter(PaperContent.paper_id.in_(paper_ids)).all()

        # Build lookup map
        summary_map = {}
        for content in contents:
            # Prefer deep extraction if available, else quick
            summary = content.deep_one_sentence_summary or content.one_sentence_summary
            paper_type = content.deep_paper_type or content.paper_type
            summary_map[content.paper_id] = {
                "summary": summary,
                "paper_type": paper_type,
                "topics": content.topics or [],
            }

    # Enrich results
    enriched = []
    for result in results:
        paper_id = result.get("id")
        enriched_result = result.copy()
        if paper_id in summary_map:
            enriched_result["summary"] = summary_map[paper_id]["summary"]
            enriched_result["paper_type"] = summary_map[paper_id]["paper_type"]
            enriched_result["topics"] = summary_map[paper_id]["topics"]
        else:
            enriched_result["summary"] = None
            enriched_result["paper_type"] = None
            enriched_result["topics"] = []
        enriched.append(enriched_result)

    return enriched


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
        rerank=arguments.get("rerank"),  # None = use settings default
        year_min=arguments.get("year_min"),
        year_max=arguments.get("year_max"),
    )

    # Enrich results with summaries if requested
    results = result.results
    if arguments.get("include_summary", False):
        results = _enrich_with_summaries(results)

    response_data = search_result(
        results=results,
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
    tool_map = {
        "search": _search,
        "get_search_status": _get_search_status,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown search tool: {name}", code="UNKNOWN_TOOL"))

    try:
        handler = tool_map[name]
        if name == "search":
            return await handler(arguments)
        return handler(arguments)

    except SearchError as e:
        logger.error(f"Search error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
