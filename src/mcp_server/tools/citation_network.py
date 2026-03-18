"""Citation Network Tools for MCP Server.

Provides tools to explore citation relationships between papers.
Uses Semantic Scholar API for citation and reference data.

Architecture:
    MCP Tool (this file) -> ExternalSearchService -> Semantic Scholar API
"""
from __future__ import annotations

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
    serialize,
    LiteratureError,
    PaperReference,
    ClaimCitation,
)
from services import PaperService  # noqa: E402
from services.external_search import ExternalSearchService  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List consolidated citation network tools (7 → 6)."""
    return [
        # =================================================================
        # CONSOLIDATED: get_paper_citations + get_paper_references
        # =================================================================
        Tool(
            name="get_citations",
            description="Get citations. direction: incoming (who cites this), outgoing (what this cites)",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["incoming", "outgoing"],
                        "description": "incoming=papers citing this, outgoing=papers this cites (bibliography)",
                    },
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
                        "description": "Maximum results to return",
                        "default": 50,
                    },
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="find_common_references",
            description="Papers sharing references with a given paper (related work)",
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
            description="Build citation graph (nodes/edges) for visualization",
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
        Tool(
            name="import_references_from_paper",
            description="Import paper's references into library (from review papers)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID of the citing paper (e.g., a review paper)",
                    },
                    "min_year": {
                        "type": "integer",
                        "description": "Only import papers from this year or later",
                    },
                    "max_imports": {
                        "type": "integer",
                        "description": "Maximum number of new papers to import",
                        "default": 50,
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to imported papers",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_local_citations",
            description="Local citation graph query (no API calls)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID to query",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["citing", "cited", "both"],
                        "description": "'citing' = papers that cite this, 'cited' = papers this cites",
                        "default": "both",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="link_papers_citation",
            description="Create citation link between two papers",
            inputSchema={
                "type": "object",
                "properties": {
                    "citing_paper_id": {
                        "type": "integer",
                        "description": "ID of the paper doing the citing",
                    },
                    "cited_paper_id": {
                        "type": "integer",
                        "description": "ID of the paper being cited",
                    },
                },
                "required": ["citing_paper_id", "cited_paper_id"],
            },
        ),
        # =================================================================
        # CLAIM CITATION TOOLS (new)
        # =================================================================
        Tool(
            name="get_claim_citations",
            description="Get claims from a paper with their cited references",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID",
                    },
                    "section": {
                        "type": "string",
                        "enum": ["introduction", "methods", "results", "discussion", "conclusion"],
                        "description": "Filter by section (optional)",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": ["fact", "method", "comparison", "limitation", "background"],
                        "description": "Filter by claim type (optional)",
                    },
                    "importance": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Filter by importance (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum claims to return",
                        "default": 50,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="find_claims_citing_paper",
            description="Find all claims in library that cite a specific paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID of the paper being cited",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum claims to return",
                        "default": 50,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_unmatched_claim_references",
            description="List unmatched references from claims (potential imports)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID (omit for all papers)",
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
            name="get_citation_chain",
            description="Trace citation chains: claim → cited paper → that paper's claims → etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Starting paper ID",
                    },
                    "claim_id": {
                        "type": "integer",
                        "description": "Starting claim ID (optional, traces from specific claim)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many citation hops to follow (1-3)",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 3,
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "backward"],
                        "description": "forward=follow claims to cited papers, backward=find claims citing this paper",
                        "default": "forward",
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


def _paper_result_to_dict(result) -> dict:
    """Convert PaperResult to dict."""
    return {
        "title": result.title,
        "authors": result.authors,
        "year": result.year,
        "doi": result.doi,
        "journal": result.journal,
        "abstract": (
            result.abstract[:300] + "..."
            if result.abstract and len(result.abstract) > 300
            else result.abstract
        ),
        "citation_count": result.citation_count,
        "arxiv_id": result.arxiv_id,
        "source": result.source,
    }


async def _get_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated citation tool.

    direction=incoming: Papers that cite this paper (was get_paper_citations)
    direction=outgoing: Papers this paper cites (was get_paper_references)
    """
    direction = arguments.get("direction")
    if not direction:
        return _to_response(error("direction is required", code="INVALID_INPUT"))

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

    if not doi and not title and not paper_id:
        return _to_response(error("Must provide paper_id, doi, or title", code="INVALID_INPUT"))

    service = ExternalSearchService()
    results = []
    source_used = None

    if direction == "incoming":
        # Get papers that cite this paper
        # 1. Try OpenAlex first (best rate limits, good coverage)
        results = await service.get_paper_citations_openalex(doi=doi, title=title, limit=limit)
        if results:
            source_used = "openalex"

        # 2. Fall back to Semantic Scholar
        if not results:
            results = await service.get_paper_citations(doi=doi, title=title, limit=limit)
            if results:
                source_used = "semantic_scholar"

        # Check which citing papers are in our library
        papers = []
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

            papers.append(paper_dict)

        return _to_response(success({
            "direction": "incoming",
            "source_doi": doi,
            "source_title": title,
            "count": len(papers),
            "source": source_used or "none",
            "papers": papers,
        }))

    else:  # direction == "outgoing"
        # Get papers this paper cites (bibliography)
        # 1. Try OpenAlex first (best rate limits, good coverage)
        if doi or title:
            results = await service.get_paper_references_openalex(doi=doi, title=title, limit=limit)
            if results:
                source_used = "openalex"

        # 2. Fall back to Semantic Scholar
        if not results and (doi or title):
            results = await service.get_paper_references(doi=doi, title=title, limit=limit)
            if results:
                source_used = "semantic_scholar"

        # 3. Fall back to PDF extraction if we have paper_id
        if not results and paper_id:
            from literature_core import get_session
            with get_session() as session:
                refs = session.query(PaperReference).filter(
                    PaperReference.paper_id == paper_id
                ).order_by(PaperReference.reference_order).limit(limit).all()

                if refs:
                    return _to_response(success({
                        "direction": "outgoing",
                        "source_doi": doi,
                        "source_title": title,
                        "count": len(refs),
                        "source": "pdf_extraction",
                        "papers": [
                            {
                                "raw_text": ref.raw_text,
                                "title": ref.parsed_title,
                                "authors": ref.parsed_authors,
                                "year": ref.parsed_year,
                                "doi": ref.parsed_doi,
                                "match_status": ref.match_status,
                                "matched_paper_id": ref.matched_paper_id,
                                "in_library": ref.matched_paper_id is not None,
                                "library_id": ref.matched_paper_id,
                                "confidence": ref.parse_confidence,
                            }
                            for ref in refs
                        ],
                    }))

        # Check which referenced papers are in our library
        papers = []
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

            papers.append(paper_dict)

        return _to_response(success({
            "direction": "outgoing",
            "source_doi": doi,
            "source_title": title,
            "count": len(papers),
            "source": source_used or "none",
            "papers": papers,
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
    # depth = arguments.get("depth", 1)  # Reserved for future multi-level graph

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


async def _import_references_from_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Import references from a paper and create citation links."""
    from literature_core import get_session, Paper, PaperCitation
    from services.paper_import_service import PaperImportService

    paper_id = arguments["paper_id"]
    min_year = arguments.get("min_year")
    max_imports = arguments.get("max_imports", 50)
    tags = arguments.get("tags", [])

    # Get the source paper
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    doi = paper.get("doi")
    title = paper.get("title")

    if not doi and not title:
        return _to_response(error("Paper has no DOI or title for lookup", code="INVALID_INPUT"))

    # Fetch references via OpenAlex
    service = ExternalSearchService()
    references = await service.get_paper_references_openalex(doi=doi, title=title, limit=200)

    if not references:
        # Fallback to Semantic Scholar
        references = await service.get_paper_references(doi=doi, title=title, limit=200)

    if not references:
        return _to_response(success({
            "source_paper_id": paper_id,
            "references_found": 0,
            "already_in_library": 0,
            "newly_imported": 0,
            "links_created": 0,
            "message": "No references found via external APIs"
        }))

    # Apply year filter
    if min_year:
        references = [r for r in references if r.year and r.year >= min_year]

    # Check which are already in library and import missing ones
    already_in_library = []
    newly_imported = []
    links_created = 0
    import_errors = []

    with get_session() as session:
        for ref in references:
            cited_paper_id = None

            # Check if already in library by DOI
            if ref.doi:
                existing = session.query(Paper).filter(Paper.doi == ref.doi).first()
                if existing:
                    cited_paper_id = existing.id
                    already_in_library.append({
                        "id": existing.id,
                        "title": existing.title,
                        "doi": existing.doi
                    })

            # If not in library and we have room to import
            if cited_paper_id is None and len(newly_imported) < max_imports:
                if ref.doi:
                    try:
                        # Import via DOI
                        result = PaperImportService.import_paper(
                            doi=ref.doi,
                            tags=tags,
                            skip_duplicate_check=False
                        )
                        if result.get("success") and result.get("data", {}).get("id"):
                            cited_paper_id = result["data"]["id"]
                            newly_imported.append({
                                "id": cited_paper_id,
                                "title": ref.title,
                                "doi": ref.doi
                            })
                    except Exception as e:
                        import_errors.append(f"{ref.title[:50]}: {str(e)[:50]}")

            # Create citation link if we have both paper IDs
            if cited_paper_id:
                # Check if link already exists
                existing_link = session.query(PaperCitation).filter(
                    PaperCitation.citing_paper_id == paper_id,
                    PaperCitation.cited_paper_id == cited_paper_id
                ).first()

                if not existing_link:
                    link = PaperCitation(
                        citing_paper_id=paper_id,
                        cited_paper_id=cited_paper_id,
                        source="openalex"
                    )
                    session.add(link)
                    links_created += 1

    return _to_response(success({
        "source_paper_id": paper_id,
        "source_title": title,
        "references_found": len(references),
        "already_in_library": len(already_in_library),
        "newly_imported": len(newly_imported),
        "links_created": links_created,
        "imported_papers": newly_imported[:10],  # Limit output size
        "errors": import_errors[:5] if import_errors else None,
    }))


async def _get_local_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Query the local citation graph."""
    from literature_core import get_session, Paper, PaperCitation

    paper_id = arguments["paper_id"]
    direction = arguments.get("direction", "both")

    # Verify paper exists
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    citing_papers = []
    cited_papers = []

    with get_session() as session:
        if direction in ("citing", "both"):
            # Papers that cite this one (incoming citations)
            incoming = session.query(PaperCitation).filter(
                PaperCitation.cited_paper_id == paper_id
            ).all()

            for link in incoming:
                citing = session.query(Paper).get(link.citing_paper_id)
                if citing:
                    citing_papers.append({
                        "id": citing.id,
                        "title": citing.title,
                        "year": citing.year,
                        "doi": citing.doi,
                        "source": link.source,
                    })

        if direction in ("cited", "both"):
            # Papers that this one cites (outgoing citations)
            outgoing = session.query(PaperCitation).filter(
                PaperCitation.citing_paper_id == paper_id
            ).all()

            for link in outgoing:
                cited = session.query(Paper).get(link.cited_paper_id)
                if cited:
                    cited_papers.append({
                        "id": cited.id,
                        "title": cited.title,
                        "year": cited.year,
                        "doi": cited.doi,
                        "source": link.source,
                    })

    return _to_response(success({
        "paper_id": paper_id,
        "paper_title": paper.get("title"),
        "citing_this": citing_papers if direction in ("citing", "both") else None,
        "cited_by_this": cited_papers if direction in ("cited", "both") else None,
        "citing_count": len(citing_papers) if direction in ("citing", "both") else None,
        "cited_count": len(cited_papers) if direction in ("cited", "both") else None,
    }))


async def _link_papers_citation(arguments: dict[str, Any]) -> list[TextContent]:
    """Manually create a citation link between two papers."""
    from literature_core import get_session, PaperCitation

    citing_paper_id = arguments["citing_paper_id"]
    cited_paper_id = arguments["cited_paper_id"]

    # Verify both papers exist
    citing = PaperService.get(citing_paper_id)
    if not citing:
        return _to_response(error(f"Citing paper {citing_paper_id} not found", code="NOT_FOUND"))

    cited = PaperService.get(cited_paper_id)
    if not cited:
        return _to_response(error(f"Cited paper {cited_paper_id} not found", code="NOT_FOUND"))

    with get_session() as session:
        # Check if link already exists
        existing = session.query(PaperCitation).filter(
            PaperCitation.citing_paper_id == citing_paper_id,
            PaperCitation.cited_paper_id == cited_paper_id
        ).first()

        if existing:
            return _to_response(success({
                "status": "already_exists",
                "message": "Citation link already exists",
                "citing_paper_id": citing_paper_id,
                "cited_paper_id": cited_paper_id,
            }))

        # Create the link
        link = PaperCitation(
            citing_paper_id=citing_paper_id,
            cited_paper_id=cited_paper_id,
            source="manual"
        )
        session.add(link)

    return _to_response(success({
        "status": "created",
        "message": f"Created citation link: '{citing.get('title')[:40]}' cites '{cited.get('title')[:40]}'",
        "citing_paper_id": citing_paper_id,
        "cited_paper_id": cited_paper_id,
    }))


# ============================================================================
# Claim Citation Tools
# ============================================================================


async def _get_claim_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Get claims from a paper with their cited references."""
    from literature_core import get_session, Paper

    paper_id = arguments["paper_id"]
    section_filter = arguments.get("section")
    claim_type_filter = arguments.get("claim_type")
    importance_filter = arguments.get("importance")
    limit = arguments.get("limit", 50)

    # Verify paper exists
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    with get_session() as session:
        query = session.query(ClaimCitation).filter(ClaimCitation.paper_id == paper_id)

        if section_filter:
            query = query.filter(ClaimCitation.section == section_filter)
        if claim_type_filter:
            query = query.filter(ClaimCitation.claim_type == claim_type_filter)
        if importance_filter:
            query = query.filter(ClaimCitation.importance == importance_filter)

        claims = query.limit(limit).all()

        results = []
        for claim in claims:
            # Get matched paper info if available
            matched_papers = []
            if claim.matched_paper_ids:
                for pid, status in zip(claim.matched_paper_ids, claim.match_statuses or []):
                    if pid and status == "matched":
                        matched = session.query(Paper).get(pid)
                        if matched:
                            matched_papers.append({
                                "id": matched.id,
                                "title": matched.title[:80] if matched.title else None,
                                "doi": matched.doi,
                            })

            results.append({
                "id": claim.id,
                "claim_text": claim.claim_text,
                "citation_numbers": claim.citation_numbers,
                "section": claim.section,
                "claim_type": claim.claim_type,
                "importance": claim.importance,
                "reference_ids": claim.reference_ids,
                "matched_paper_ids": claim.matched_paper_ids,
                "match_statuses": claim.match_statuses,
                "matched_papers": matched_papers,
            })

    return _to_response(success({
        "paper_id": paper_id,
        "paper_title": paper.get("title"),
        "total_claims": len(results),
        "claims": results,
    }))


async def _find_claims_citing_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Find all claims in the library that cite a specific paper."""
    from literature_core import get_session, Paper
    from sqlalchemy import text

    paper_id = arguments["paper_id"]
    limit = arguments.get("limit", 50)

    # Verify paper exists
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    with get_session() as session:
        # Find claims where matched_paper_ids contains this paper_id
        # JSON query: matched_paper_ids is a JSON array
        # This is SQLite-specific using json_each
        claims = session.query(ClaimCitation).filter(
            text(f"EXISTS (SELECT 1 FROM json_each(matched_paper_ids) WHERE value = {paper_id})")
        ).limit(limit).all()

        results = []
        for claim in claims:
            citing_paper = session.query(Paper).get(claim.paper_id)
            results.append({
                "claim_id": claim.id,
                "claim_text": claim.claim_text,
                "citing_paper_id": claim.paper_id,
                "citing_paper_title": citing_paper.title[:80] if citing_paper and citing_paper.title else None,
                "section": claim.section,
                "claim_type": claim.claim_type,
                "importance": claim.importance,
            })

    return _to_response(success({
        "cited_paper_id": paper_id,
        "cited_paper_title": paper.get("title"),
        "total_citing_claims": len(results),
        "citing_claims": results,
    }))


async def _get_unmatched_claim_references(arguments: dict[str, Any]) -> list[TextContent]:
    """List unmatched references from claims (potential imports)."""
    from literature_core import get_session, Paper
    from sqlalchemy import text

    paper_id = arguments.get("paper_id")
    limit = arguments.get("limit", 50)

    with get_session() as session:
        query = session.query(ClaimCitation)

        if paper_id:
            query = query.filter(ClaimCitation.paper_id == paper_id)

        # Get claims that have unmatched references
        claims = query.filter(
            text("EXISTS (SELECT 1 FROM json_each(match_statuses) WHERE value IN ('unmatched', 'reference_not_found'))")
        ).limit(limit * 2).all()  # Get more since we'll filter

        # Collect unmatched references
        unmatched_refs = []
        seen = set()

        for claim in claims:
            if not claim.reference_ids or not claim.match_statuses:
                continue

            citing_paper = session.query(Paper).get(claim.paper_id)

            for i, (ref_id, status) in enumerate(zip(claim.reference_ids, claim.match_statuses)):
                if status in ("unmatched", "reference_not_found") and ref_id:
                    if ref_id in seen:
                        continue
                    seen.add(ref_id)

                    # Get reference details
                    ref = session.query(PaperReference).get(ref_id)
                    if ref and len(unmatched_refs) < limit:
                        unmatched_refs.append({
                            "reference_id": ref_id,
                            "raw_text": ref.raw_text[:200] if ref.raw_text else None,
                            "parsed_title": ref.parsed_title,
                            "parsed_authors": ref.parsed_authors,
                            "parsed_year": ref.parsed_year,
                            "parsed_doi": ref.parsed_doi,
                            "citing_paper_id": claim.paper_id,
                            "citing_paper_title": citing_paper.title[:60] if citing_paper and citing_paper.title else None,
                            "claim_text": claim.claim_text[:100] + "..." if len(claim.claim_text) > 100 else claim.claim_text,
                        })

    return _to_response(success({
        "paper_id": paper_id,
        "total_unmatched": len(unmatched_refs),
        "unmatched_references": unmatched_refs,
        "hint": "Use import_paper with DOI to add these to library, then re-run deep extraction",
    }))


async def _get_citation_chain(arguments: dict[str, Any]) -> list[TextContent]:
    """Trace citation chains through claims and references.

    Forward: paper's claims → cited papers → their claims → etc.
    Backward: papers citing this → their claims that cite this → etc.
    """
    from literature_core import get_session, Paper
    from sqlalchemy import text

    paper_id = arguments["paper_id"]
    claim_id = arguments.get("claim_id")
    depth = min(arguments.get("depth", 2), 3)  # Cap at 3
    direction = arguments.get("direction", "forward")

    # Verify paper exists
    paper = PaperService.get(paper_id)
    if not paper:
        return _to_response(error(f"Paper {paper_id} not found", code="NOT_FOUND"))

    chain = {
        "start_paper": {
            "id": paper_id,
            "title": paper.get("title"),
        },
        "direction": direction,
        "depth": depth,
        "levels": [],
    }

    with get_session() as session:
        if direction == "forward":
            # Forward: Start with claims from this paper, follow to cited papers
            current_paper_ids = [paper_id]

            for level in range(depth):
                level_data = {"level": level + 1, "papers": []}

                for pid in current_paper_ids:
                    # Get claims from this paper
                    claims = session.query(ClaimCitation).filter(
                        ClaimCitation.paper_id == pid
                    ).all()

                    if claim_id and level == 0:
                        # Filter to specific claim if provided
                        claims = [c for c in claims if c.id == claim_id]

                    for claim in claims:
                        if not claim.matched_paper_ids:
                            continue

                        for i, (matched_id, status) in enumerate(
                            zip(claim.matched_paper_ids, claim.match_statuses or [])
                        ):
                            if matched_id and status == "matched":
                                cited_paper = session.query(Paper).get(matched_id)
                                if cited_paper:
                                    level_data["papers"].append({
                                        "paper_id": cited_paper.id,
                                        "title": cited_paper.title[:80] if cited_paper.title else None,
                                        "doi": cited_paper.doi,
                                        "citing_claim": claim.claim_text[:150] + "..." if len(claim.claim_text) > 150 else claim.claim_text,
                                        "from_paper_id": pid,
                                        "claim_type": claim.claim_type,
                                        "importance": claim.importance,
                                    })

                # De-duplicate papers at this level
                seen = set()
                unique_papers = []
                for p in level_data["papers"]:
                    if p["paper_id"] not in seen:
                        seen.add(p["paper_id"])
                        unique_papers.append(p)
                level_data["papers"] = unique_papers[:20]  # Limit per level
                level_data["count"] = len(unique_papers)

                if unique_papers:
                    chain["levels"].append(level_data)
                    # Next level starts from cited papers
                    current_paper_ids = [p["paper_id"] for p in unique_papers]
                else:
                    break

        else:
            # Backward: Find claims that cite this paper, then their source papers
            current_paper_ids = [paper_id]

            for level in range(depth):
                level_data = {"level": level + 1, "papers": []}

                for pid in current_paper_ids:
                    # Find claims that cite this paper
                    claims = session.query(ClaimCitation).filter(
                        text(f"EXISTS (SELECT 1 FROM json_each(matched_paper_ids) WHERE value = {pid})")
                    ).all()

                    for claim in claims:
                        citing_paper = session.query(Paper).get(claim.paper_id)
                        if citing_paper and citing_paper.id not in [p["paper_id"] for p in level_data["papers"]]:
                            level_data["papers"].append({
                                "paper_id": citing_paper.id,
                                "title": citing_paper.title[:80] if citing_paper.title else None,
                                "doi": citing_paper.doi,
                                "claim_text": claim.claim_text[:150] + "..." if len(claim.claim_text) > 150 else claim.claim_text,
                                "cites_paper_id": pid,
                                "claim_type": claim.claim_type,
                                "importance": claim.importance,
                            })

                level_data["papers"] = level_data["papers"][:20]  # Limit per level
                level_data["count"] = len(level_data["papers"])

                if level_data["papers"]:
                    chain["levels"].append(level_data)
                    # Next level: find papers citing these papers
                    current_paper_ids = [p["paper_id"] for p in level_data["papers"]]
                else:
                    break

    # Summary stats
    total_papers = sum(level["count"] for level in chain["levels"])
    chain["summary"] = {
        "total_papers_in_chain": total_papers,
        "levels_traced": len(chain["levels"]),
    }

    return _to_response(success(chain))


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
        # Consolidated tool
        "get_citations": _get_citations,
        # Kept as-is
        "find_common_references": _find_common_references,
        "build_citation_graph": _build_citation_graph,
        "import_references_from_paper": _import_references_from_paper,
        "get_local_citations": _get_local_citations,
        "link_papers_citation": _link_papers_citation,
        # Claim citation tools
        "get_claim_citations": _get_claim_citations,
        "find_claims_citing_paper": _find_claims_citing_paper,
        "get_unmatched_claim_references": _get_unmatched_claim_references,
        "get_citation_chain": _get_citation_chain,
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
