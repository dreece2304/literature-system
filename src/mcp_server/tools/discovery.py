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
# discovery.py is at src/mcp_server/tools/discovery.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (  # noqa: E402
    get_logger,
    search_result,
    error,
    success,
    serialize,
    SearchError,
    PaperNotFoundError,
    LiteratureError,
)
from services import SearchService, PaperService, EmbeddingService  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List discovery tools."""
    return [
        Tool(
            name="find_similar_papers",
            description="Find semantically similar papers via embeddings",
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
                    "include_summary": {
                        "type": "boolean",
                        "description": (
                            "Include one_sentence_summary and paper_type from extractions. "
                            "Useful for quickly evaluating relevance without separate calls."
                        ),
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="find_papers_like_text",
            description="Find papers matching a text description or research question",
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
                    "include_summary": {
                        "type": "boolean",
                        "description": (
                            "Include one_sentence_summary and paper_type from extractions. "
                            "Useful for quickly evaluating relevance without separate calls."
                        ),
                        "default": False,
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="suggest_citations_for_text",
            description="Suggest papers to cite for a text snippet",
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
            description="Unread papers sorted by rating and date added",
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
            description="Suggest tags based on similar papers' tags",
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
        Tool(
            name="get_embedding_status",
            description="Embedding coverage status (papers with/without embeddings)",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_ids": {
                        "type": "boolean",
                        "description": "Include lists of paper IDs needing embeddings",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="process_embedding_queue",
            description="Generate embeddings for papers missing them (batch)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to process (default: 50)",
                        "default": 50,
                    },
                    "include_paper_embeddings": {
                        "type": "boolean",
                        "description": "Generate paper-level embeddings (title+abstract)",
                        "default": True,
                    },
                    "include_chunk_embeddings": {
                        "type": "boolean",
                        "description": "Generate chunk-level embeddings (full text)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="embed_paper",
            description="Generate embeddings for a single paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to generate embeddings for",
                    },
                    "include_paper_embedding": {
                        "type": "boolean",
                        "description": "Generate paper-level embedding",
                        "default": True,
                    },
                    "include_chunk_embedding": {
                        "type": "boolean",
                        "description": "Generate chunk embeddings (requires full text)",
                        "default": True,
                    },
                },
                "required": ["paper_id"],
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
        Results with added 'summary', 'paper_type', and 'topics' fields
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


async def _find_similar_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Find papers similar to a given paper."""
    paper_id = arguments["paper_id"]
    limit = arguments.get("limit", 10)
    min_similarity = arguments.get("min_similarity", 0.5)
    include_summary = arguments.get("include_summary", False)

    result = await SearchService.find_similar_papers(
        paper_id=paper_id,
        limit=limit,
        min_similarity=min_similarity,
    )

    results = result.results
    if include_summary:
        results = _enrich_with_summaries(results)

    return _to_response(
        search_result(
            results=results,
            query=result.query,
            search_type=result.search_type,
        )
    )


async def _find_papers_like_text(arguments: dict[str, Any]) -> list[TextContent]:
    """Find papers matching free-form text."""
    text = arguments["text"]
    limit = arguments.get("limit", 10)
    min_similarity = arguments.get("min_similarity", 0.5)
    include_summary = arguments.get("include_summary", False)

    result = await SearchService.find_papers_like_text(
        text=text,
        limit=limit,
        min_similarity=min_similarity,
    )

    results = result.results
    if include_summary:
        results = _enrich_with_summaries(results)

    return _to_response(
        search_result(
            results=results,
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
    # Note: PaperService.get() returns tags as dicts with 'name' key
    current_paper = PaperService.get(paper_id)
    if current_paper:
        raw_tags = current_paper.get("tags", [])
        current_tags = set(
            t["name"] if isinstance(t, dict) else t for t in raw_tags
        )
    else:
        current_tags = set()

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


def _get_embedding_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get embedding coverage status."""
    include_ids = arguments.get("include_ids", False)

    status = EmbeddingService.get_embedding_status(include_ids=include_ids)

    response = {
        "success": True,
        "total_papers": status.total_papers,
        "paper_embeddings": {
            "count": status.paper_embeddings_count,
            "papers_with_abstract": status.papers_with_abstract,
            "needing_embedding": status.papers_needing_paper_embedding,
            "coverage_percent": round(status.paper_coverage_percent, 1),
        },
        "chunk_embeddings": {
            "count": status.chunk_embeddings_count,
            "papers_with_chunks": status.papers_with_chunks,
            "papers_with_full_text": status.papers_with_full_text,
            "needing_embedding": status.papers_needing_chunk_embedding,
            "coverage_percent": round(status.chunk_coverage_percent, 1),
        },
    }

    if include_ids:
        response["paper_ids_needing_paper_embedding"] = (
            status.paper_ids_needing_paper_embedding[:100]  # Limit for response size
        )
        response["paper_ids_needing_chunk_embedding"] = (
            status.paper_ids_needing_chunk_embedding[:100]
        )

    return _to_response(response)


async def _process_embedding_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Process papers needing embeddings."""
    limit = arguments.get("limit", 50)
    include_paper = arguments.get("include_paper_embeddings", True)
    include_chunks = arguments.get("include_chunk_embeddings", True)

    result = await EmbeddingService.process_queue(
        limit=limit,
        include_paper_embeddings=include_paper,
        include_chunk_embeddings=include_chunks,
    )

    return _to_response(
        success({
            "papers_processed": result.papers_processed,
            "paper_embeddings_created": result.paper_embeddings_created,
            "chunks_created": result.chunks_created,
            "errors": result.errors if result.errors else None,
            "success": result.success,
        })
    )


async def _embed_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Generate embeddings for a single paper."""
    paper_id = arguments["paper_id"]
    include_paper = arguments.get("include_paper_embedding", True)
    include_chunks = arguments.get("include_chunk_embedding", True)

    result = await EmbeddingService.embed_paper(
        paper_id=paper_id,
        include_paper_embedding=include_paper,
        include_chunk_embedding=include_chunks,
    )

    return _to_response(
        success({
            "paper_id": paper_id,
            "papers_processed": result.papers_processed,
            "paper_embeddings_created": result.paper_embeddings_created,
            "chunks_created": result.chunks_created,
            "errors": result.errors if result.errors else None,
            "success": result.success,
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
        "get_embedding_status": _get_embedding_status,
    }

    # Async tools
    async_tools = {
        "find_similar_papers": _find_similar_papers,
        "find_papers_like_text": _find_papers_like_text,
        "suggest_citations_for_text": _suggest_citations_for_text,
        "suggest_paper_tags": _suggest_paper_tags,
        "process_embedding_queue": _process_embedding_queue,
        "embed_paper": _embed_paper,
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
