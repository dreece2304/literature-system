"""Discovery Tools for MCP Server.

Consolidated tools:
    - semantic_find: Find similar papers, match text, or suggest citations
    - manage_embeddings: Status, batch process, or embed single paper
    - get_reading_queue: Unread papers by rating
    - suggest_paper_tags: Tag suggestions based on similar papers

Architecture:
    MCP Tool (this file) -> SearchService/EmbeddingService -> ChromaDB/Database
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
    """List consolidated discovery tools (8 → 5)."""
    return [
        # =================================================================
        # CONSOLIDATED: find_similar_papers + find_papers_like_text + suggest_citations_for_text
        # =================================================================
        Tool(
            name="semantic_find",
            description="Semantic search. input: paper (by ID), text (description), citation (suggest refs)",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_type": {
                        "type": "string",
                        "enum": ["paper", "text", "citation"],
                        "description": "paper=similar to paper_id, text=match description, citation=suggest refs for text",
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID (input_type=paper)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to search/cite (input_type=text or citation)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum results",
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.5,
                        "description": "Minimum similarity score (0-1)",
                    },
                    "include_summary": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include extraction summaries",
                    },
                    "include_bibtex": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include BibTeX (citation mode)",
                    },
                    "prefer_type": {
                        "type": "string",
                        "enum": ["any", "review", "primary"],
                        "default": "any",
                        "description": "Citation mode: prefer reviews (background) or primary sources (specific claims)",
                    },
                },
                "required": ["input_type"],
            },
        ),
        # =================================================================
        # CONSOLIDATED: get_embedding_status + process_embedding_queue + embed_paper
        # =================================================================
        Tool(
            name="manage_embeddings",
            description="Embeddings. action: status, process (batch), embed (single paper)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "process", "embed"],
                        "description": "status=coverage, process=batch generate, embed=single paper",
                        "default": "status",
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID (action=embed)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max papers (action=process)",
                    },
                    "include_ids": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include paper IDs needing embeddings (action=status)",
                    },
                    "include_paper_embeddings": {
                        "type": "boolean",
                        "default": True,
                        "description": "Generate paper-level embeddings",
                    },
                    "include_chunk_embeddings": {
                        "type": "boolean",
                        "default": True,
                        "description": "Generate chunk-level embeddings",
                    },
                },
            },
        ),
        # =================================================================
        # KEPT AS-IS
        # =================================================================
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
    ]


# ============================================================================
# Tool Implementations
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


def _enrich_with_summaries(results: list[dict]) -> list[dict]:
    """Batch-enrich search results with extraction summaries."""
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

        summary_map = {}
        for content in contents:
            summary = content.deep_one_sentence_summary or content.one_sentence_summary
            paper_type = content.deep_paper_type or content.paper_type
            summary_map[content.paper_id] = {
                "summary": summary,
                "paper_type": paper_type,
                "topics": content.topics or [],
            }

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


async def _semantic_find(arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated semantic search tool."""
    input_type = arguments.get("input_type")
    limit = arguments.get("limit", 10)
    min_similarity = arguments.get("min_similarity", 0.5)
    include_summary = arguments.get("include_summary", False)

    if input_type == "paper":
        # Find similar papers by paper_id
        paper_id = arguments.get("paper_id")
        if not paper_id:
            return _to_response(error("paper_id required for input_type=paper", code="MISSING_PARAM"))

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

    elif input_type == "text":
        # Find papers matching text description
        text = arguments.get("text")
        if not text:
            return _to_response(error("text required for input_type=text", code="MISSING_PARAM"))

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

    elif input_type == "citation":
        # Suggest citations for text
        from services.citation_service import CitationService
        from literature_core import get_session, Paper
        from literature_core.models import PaperContent
        from sqlalchemy.orm import joinedload

        text = arguments.get("text")
        if not text:
            return _to_response(error("text required for input_type=citation", code="MISSING_PARAM"))

        include_bibtex = arguments.get("include_bibtex", False)
        prefer_type = arguments.get("prefer_type", "any")

        # Fetch more results if filtering by type (to ensure enough results after filtering)
        fetch_limit = limit * 3 if prefer_type != "any" else limit

        result = await SearchService.suggest_citations_for_text(
            text=text,
            limit=fetch_limit,
        )

        suggestions = result.results

        # Always enrich with extraction data for citation suggestions
        if suggestions:
            paper_ids = [s["id"] for s in suggestions if s.get("id")]

            with get_session() as session:
                # Fetch Paper ORM objects with authors
                papers = (
                    session.query(Paper)
                    .options(joinedload(Paper.authors))
                    .filter(Paper.id.in_(paper_ids))
                    .all()
                )
                paper_map = {p.id: p for p in papers}

                # Fetch extraction data
                extractions = (
                    session.query(PaperContent)
                    .filter(PaperContent.paper_id.in_(paper_ids))
                    .all()
                )
                extraction_map = {e.paper_id: e for e in extractions}

                # Enrich suggestions with extraction data
                for suggestion in suggestions:
                    pid = suggestion.get("id")
                    extraction = extraction_map.get(pid)

                    if extraction:
                        # Prefer deep extraction if available
                        suggestion["summary"] = (
                            extraction.deep_one_sentence_summary
                            or extraction.one_sentence_summary
                        )
                        suggestion["paper_type"] = (
                            extraction.deep_paper_type
                            or extraction.paper_type
                        )
                        suggestion["topics"] = (
                            extraction.deep_topics
                            or extraction.topics
                            or []
                        )
                        # Key findings help identify what claims the paper supports
                        suggestion["key_findings"] = extraction.key_findings or []

                        # Flag reviews as good for general/background citations
                        if suggestion["paper_type"] in ("review", "meta-analysis"):
                            suggestion["citation_hint"] = "Good for background/overview citations"
                    else:
                        suggestion["summary"] = None
                        suggestion["paper_type"] = None
                        suggestion["topics"] = []
                        suggestion["key_findings"] = []

                # Apply type preference filtering/sorting
                review_types = {"review", "meta-analysis", "survey"}
                primary_types = {"research_article", "letter", "communication", "conference"}

                if prefer_type == "review":
                    # Filter to reviews first, then fill with others if needed
                    reviews = [s for s in suggestions if s.get("paper_type") in review_types]
                    others = [s for s in suggestions if s.get("paper_type") not in review_types]
                    suggestions = (reviews + others)[:limit]
                    for s in suggestions:
                        if s.get("paper_type") in review_types:
                            s["citation_hint"] = "✓ Review paper (preferred)"
                elif prefer_type == "primary":
                    # Filter to primary sources first, then fill with others
                    primary = [s for s in suggestions if s.get("paper_type") in primary_types]
                    others = [s for s in suggestions if s.get("paper_type") not in primary_types]
                    suggestions = (primary + others)[:limit]
                    for s in suggestions:
                        if s.get("paper_type") in primary_types:
                            s["citation_hint"] = "✓ Primary source (preferred)"
                else:
                    # "any" - just take top results by score
                    suggestions = suggestions[:limit]

                # Add BibTeX if requested
                if include_bibtex and papers:
                    bibtex_entries = CitationService.generate_bibtex(papers)
                    bibtex_map = {e["paper_id"]: e for e in bibtex_entries}

                    for suggestion in suggestions:
                        entry = bibtex_map.get(suggestion["id"])
                        if entry:
                            suggestion["bibtex"] = entry.get("bibtex", "")
                            suggestion["citation_key"] = entry.get("key", "")

        return _to_response(
            search_result(
                results=suggestions,
                query=text[:100] + "..." if len(text) > 100 else text,
                search_type="citation_suggestion",
            )
        )

    else:
        return _to_response(error(f"Invalid input_type: {input_type}", code="INVALID_PARAM"))


async def _manage_embeddings(arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated embedding management tool."""
    action = arguments.get("action", "status")

    if action == "status":
        # Get embedding coverage status
        include_ids = arguments.get("include_ids", False)
        status = EmbeddingService.get_embedding_status(include_ids=include_ids)

        response = {
            "action": "status",
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
                status.paper_ids_needing_paper_embedding[:100]
            )
            response["paper_ids_needing_chunk_embedding"] = (
                status.paper_ids_needing_chunk_embedding[:100]
            )

        return _to_response(response)

    elif action == "process":
        # Batch process embeddings
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
                "action": "process",
                "papers_processed": result.papers_processed,
                "paper_embeddings_created": result.paper_embeddings_created,
                "chunks_created": result.chunks_created,
                "errors": result.errors if result.errors else None,
                "success": result.success,
            })
        )

    elif action == "embed":
        # Embed single paper
        paper_id = arguments.get("paper_id")
        if not paper_id:
            return _to_response(error("paper_id required for action=embed", code="MISSING_PARAM"))

        include_paper = arguments.get("include_paper_embeddings", True)
        include_chunks = arguments.get("include_chunk_embeddings", True)

        result = await EmbeddingService.embed_paper(
            paper_id=paper_id,
            include_paper_embedding=include_paper,
            include_chunk_embedding=include_chunks,
        )

        return _to_response(
            success({
                "action": "embed",
                "paper_id": paper_id,
                "papers_processed": result.papers_processed,
                "paper_embeddings_created": result.paper_embeddings_created,
                "chunks_created": result.chunks_created,
                "errors": result.errors if result.errors else None,
                "success": result.success,
            })
        )

    else:
        return _to_response(error(f"Unknown action: {action}", code="UNKNOWN_ACTION"))


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

        if min_rating:
            query = query.filter(Paper.rating >= min_rating)

        if tag_filter:
            query = query.join(Paper.tags).filter(Tag.name == tag_filter)

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

    similar = await SearchService.find_similar_papers(
        paper_id=paper_id,
        limit=20,
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

    tag_counts: dict[str, int] = {}
    for paper in similar.results:
        for tag in paper.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    current_paper = PaperService.get(paper_id)
    if current_paper:
        raw_tags = current_paper.get("tags", [])
        current_tags = set(
            t["name"] if isinstance(t, dict) else t for t in raw_tags
        )
    else:
        current_tags = set()

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
    """Execute a discovery tool."""
    try:
        if name == "semantic_find":
            return await _semantic_find(arguments)

        if name == "manage_embeddings":
            return await _manage_embeddings(arguments)

        if name == "get_reading_queue":
            return _get_reading_queue(arguments)

        if name == "suggest_paper_tags":
            return await _suggest_paper_tags(arguments)

        return _to_response(error(f"Unknown discovery tool: {name}", code="UNKNOWN_TOOL"))

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
