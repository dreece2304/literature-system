"""Citation Network Tools for MCP Server.

Provides tools to explore citation relationships between papers.
Uses Semantic Scholar API for citation and reference data.

Architecture:
    MCP Tool (this file) -> ExternalSearchService -> Semantic Scholar API
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# citation_network.py is at src/mcp_server/tools/citation_network.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (  # noqa: E402
    get_logger,
    success,
    error,
    LiteratureError,
)
from services import PaperService  # noqa: E402
from services.external_search import ExternalSearchService  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List citation network tools."""
    return [
        Tool(
            name="get_paper_citations",
            description=(
                "Get papers that cite a given paper. Uses Semantic Scholar API. "
                "Can look up by paper ID (from database), DOI, or title."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID (will use DOI/title to lookup)",
                    },
                    "doi": {
                        "type": "string",
                        "description": "Paper DOI (preferred for accuracy)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (fallback if no DOI)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum citations to return",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="get_paper_references",
            description=(
                "Get papers that a given paper references (its bibliography). "
                "Uses Semantic Scholar API."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID (will use DOI/title to lookup)",
                    },
                    "doi": {
                        "type": "string",
                        "description": "Paper DOI (preferred for accuracy)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (fallback if no DOI)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum references to return",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="find_common_references",
            description=(
                "Find papers that share common references with a given paper. "
                "Useful for finding related work in the same research area."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID to find related papers for",
                    },
                    "min_shared": {
                        "type": "integer",
                        "description": "Minimum number of shared references",
                        "default": 2,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 10,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="build_citation_graph",
            description=(
                "Build a citation graph for a set of papers showing citation "
                "relationships. Returns nodes and edges in JSON format suitable "
                "for visualization."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of database paper IDs to include in graph",
                    },
                    "include_external": {
                        "type": "boolean",
                        "description": "Include external citations (not in library)",
                        "default": False,
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Depth of citation chain to follow (1-2)",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 2,
                    },
                },
                "required": ["paper_ids"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _paper_result_to_dict(result) -> dict:
    """Convert PaperResult to dict."""
    return {
        "title": result.title,
        "authors": result.authors,
        "year": result.year,
        "doi": result.doi,
        "journal": result.journal,
        "abstract": result.abstract[:300] + "..." if result.abstract and len(result.abstract) > 300 else result.abstract,
        "citation_count": result.citation_count,
        "arxiv_id": result.arxiv_id,
        "source": result.source,
    }


async def _get_paper_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers that cite a given paper."""
    paper_id = arguments.get("paper_id")
    doi = arguments.get("doi")
    title = arguments.get("title")
    limit = arguments.get("limit", 50)

    # If paper_id provided, get DOI/title from database
    if paper_id and not doi and not title:
        paper = PaperService.get(paper_id)
        if paper:
            doi = paper.get("doi")
            title = paper.get("title")
        else:
            return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    if not doi and not title:
        return _to_response(error("Must provide paper_id, doi, or title", code="INVALID_INPUT"))

    service = ExternalSearchService()
    results = await service.get_paper_citations(doi=doi, title=title, limit=limit)

    # Check which citing papers are in our library
    citing_papers = []
    for result in results:
        paper_dict = _paper_result_to_dict(result)

        # Check if in library by DOI
        if result.doi:
            from literature_core import get_session, Paper
            with get_session() as session:
                local = session.query(Paper).filter(Paper.doi == result.doi).first()
                if local:
                    paper_dict["in_library"] = True
                    paper_dict["library_id"] = local.id

        citing_papers.append(paper_dict)

    return _to_response(success({
        "source_doi": doi,
        "source_title": title,
        "citation_count": len(citing_papers),
        "citations": citing_papers,
    }))


async def _get_paper_references(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers that a given paper references."""
    paper_id = arguments.get("paper_id")
    doi = arguments.get("doi")
    title = arguments.get("title")
    limit = arguments.get("limit", 50)

    # If paper_id provided, get DOI/title from database
    if paper_id and not doi and not title:
        paper = PaperService.get(paper_id)
        if paper:
            doi = paper.get("doi")
            title = paper.get("title")
        else:
            return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    if not doi and not title:
        return _to_response(error("Must provide paper_id, doi, or title", code="INVALID_INPUT"))

    service = ExternalSearchService()
    results = await service.get_paper_references(doi=doi, title=title, limit=limit)

    # Check which referenced papers are in our library
    referenced_papers = []
    for result in results:
        paper_dict = _paper_result_to_dict(result)

        # Check if in library by DOI
        if result.doi:
            from literature_core import get_session, Paper
            with get_session() as session:
                local = session.query(Paper).filter(Paper.doi == result.doi).first()
                if local:
                    paper_dict["in_library"] = True
                    paper_dict["library_id"] = local.id

        referenced_papers.append(paper_dict)

    return _to_response(success({
        "source_doi": doi,
        "source_title": title,
        "reference_count": len(referenced_papers),
        "references": referenced_papers,
    }))


async def _find_common_references(arguments: dict[str, Any]) -> list[TextContent]:
    """Find papers sharing common references."""
    paper_id = arguments["paper_id"]
    min_shared = arguments.get("min_shared", 2)
    limit = arguments.get("limit", 10)

    # Get the source paper
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    doi = paper.get("doi")
    title = paper.get("title")

    if not doi and not title:
        return _to_response(error("Paper has no DOI or title for lookup", code="INVALID_INPUT"))

    # Get references of the source paper
    service = ExternalSearchService()
    source_refs = await service.get_paper_references(doi=doi, title=title, limit=100)

    if not source_refs:
        return _to_response(success({
            "paper_id": paper_id,
            "message": "Could not retrieve references for this paper",
            "related_papers": [],
        }))

    # Get DOIs of source references
    source_ref_dois = {r.doi for r in source_refs if r.doi}

    # Find other papers in library that cite the same references
    from literature_core import get_session, Paper

    related_papers = []
    with get_session() as session:
        # Get all papers with DOIs (excluding the source)
        library_papers = (
            session.query(Paper)
            .filter(Paper.doi.isnot(None), Paper.id != paper_id)
            .limit(50)  # Limit to avoid too many API calls
            .all()
        )

        for lib_paper in library_papers:
            # Get references for this paper
            lib_refs = await service.get_paper_references(doi=lib_paper.doi, limit=100)
            lib_ref_dois = {r.doi for r in lib_refs if r.doi}

            # Count shared references
            shared = source_ref_dois & lib_ref_dois
            if len(shared) >= min_shared:
                related_papers.append({
                    "id": lib_paper.id,
                    "title": lib_paper.title,
                    "year": lib_paper.year,
                    "doi": lib_paper.doi,
                    "shared_references": len(shared),
                    "shared_dois": list(shared)[:5],  # Include up to 5 example DOIs
                })

    # Sort by number of shared references
    related_papers.sort(key=lambda x: x["shared_references"], reverse=True)

    return _to_response(success({
        "paper_id": paper_id,
        "source_reference_count": len(source_refs),
        "related_paper_count": len(related_papers[:limit]),
        "related_papers": related_papers[:limit],
    }))


async def _build_citation_graph(arguments: dict[str, Any]) -> list[TextContent]:
    """Build a citation graph for visualization."""
    paper_ids = arguments["paper_ids"]
    include_external = arguments.get("include_external", False)
    depth = arguments.get("depth", 1)

    nodes = []
    edges = []
    seen_nodes = set()

    service = ExternalSearchService()

    # Add library papers as nodes
    for pid in paper_ids:
        paper = PaperService.get(pid)
        if paper:
            node_id = f"lib_{pid}"
            nodes.append({
                "id": node_id,
                "label": paper.get("title", "")[:50],
                "type": "library",
                "paper_id": pid,
                "doi": paper.get("doi"),
                "year": paper.get("year"),
                "citation_count": paper.get("citation_count", 0),
            })
            seen_nodes.add(node_id)

    # Get citation relationships
    for pid in paper_ids:
        paper = PaperService.get(pid)
        if not paper:
            continue

        doi = paper.get("doi")
        title = paper.get("title")
        source_node = f"lib_{pid}"

        if not doi and not title:
            continue

        # Get citations (papers citing this one)
        citations = await service.get_paper_citations(doi=doi, title=title, limit=20)
        for citing in citations:
            # Check if in library
            from literature_core import get_session, Paper as PaperModel
            target_node = None

            if citing.doi:
                with get_session() as session:
                    local = session.query(PaperModel).filter(PaperModel.doi == citing.doi).first()
                    if local:
                        target_node = f"lib_{local.id}"
                        if target_node not in seen_nodes:
                            nodes.append({
                                "id": target_node,
                                "label": local.title[:50] if local.title else "",
                                "type": "library",
                                "paper_id": local.id,
                                "doi": local.doi,
                                "year": local.year,
                            })
                            seen_nodes.add(target_node)

            if not target_node and include_external:
                target_node = f"ext_{citing.doi or citing.title[:30]}"
                if target_node not in seen_nodes:
                    nodes.append({
                        "id": target_node,
                        "label": citing.title[:50] if citing.title else "",
                        "type": "external",
                        "doi": citing.doi,
                        "year": citing.year,
                    })
                    seen_nodes.add(target_node)

            if target_node:
                edges.append({
                    "source": target_node,
                    "target": source_node,
                    "type": "cites",
                })

        # Get references (papers this one cites)
        references = await service.get_paper_references(doi=doi, title=title, limit=20)
        for ref in references:
            target_node = None

            if ref.doi:
                with get_session() as session:
                    local = session.query(PaperModel).filter(PaperModel.doi == ref.doi).first()
                    if local:
                        target_node = f"lib_{local.id}"
                        if target_node not in seen_nodes:
                            nodes.append({
                                "id": target_node,
                                "label": local.title[:50] if local.title else "",
                                "type": "library",
                                "paper_id": local.id,
                                "doi": local.doi,
                                "year": local.year,
                            })
                            seen_nodes.add(target_node)

            if not target_node and include_external:
                target_node = f"ext_{ref.doi or ref.title[:30]}"
                if target_node not in seen_nodes:
                    nodes.append({
                        "id": target_node,
                        "label": ref.title[:50] if ref.title else "",
                        "type": "external",
                        "doi": ref.doi,
                        "year": ref.year,
                    })
                    seen_nodes.add(target_node)

            if target_node:
                edges.append({
                    "source": source_node,
                    "target": target_node,
                    "type": "cites",
                })

    return _to_response(success({
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }))


# ============================================================================
# Main entry point
# ============================================================================

async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a citation network tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "get_paper_citations": _get_paper_citations,
        "get_paper_references": _get_paper_references,
        "find_common_references": _find_common_references,
        "build_citation_graph": _build_citation_graph,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown citation network tool: {name}", code="UNKNOWN_TOOL"))

    try:
        return await tool_map[name](arguments)

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
