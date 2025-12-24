"""
External API Tools for MCP Server.

These tools provide access to external academic APIs for
looking up paper metadata, finding open access PDFs, etc.
"""

import json
from typing import Any

from mcp.types import Tool, TextContent
from loguru import logger

from services.external_search import ExternalSearchService


async def list_tools() -> list[Tool]:
    """List external API tools."""
    return [
        Tool(
            name="lookup_paper_metadata",
            description=(
                "Look up paper metadata from external sources (CrossRef, OpenAlex, "
                "Semantic Scholar, arXiv). Use this to find missing DOIs, abstracts, "
                "citation counts, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Paper title to search for",
                    },
                    "doi": {
                        "type": "string",
                        "description": "DOI if known (most reliable)",
                    },
                    "authors": {
                        "type": "string",
                        "description": "Author names to help refine search",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Publication year to help refine search",
                    },
                },
            },
        ),
        Tool(
            name="find_open_access_pdf",
            description=(
                "Find open access PDF URLs for a paper using Unpaywall, "
                "arXiv, and publisher APIs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "Paper DOI (required for best results)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (fallback if no DOI)",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID if known",
                    },
                },
            },
        ),
        Tool(
            name="enrich_paper",
            description=(
                "Automatically enrich a paper with missing metadata from external sources. "
                "Fetches abstract, DOI, citation count, and PDF URL if missing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID in the local database",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (if not using paper_id)",
                    },
                    "doi": {
                        "type": "string",
                        "description": "DOI if known",
                    },
                },
            },
        ),
        Tool(
            name="search_external_papers",
            description=(
                "Search external academic databases for papers not in your library. "
                "Useful for literature discovery."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title, topic, keywords)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results per source",
                        "default": 5,
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["crossref", "openalex", "semantic_scholar", "arxiv"],
                        },
                        "description": "Sources to search (default: all)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_citation_count",
            description="Get citation count for a paper from Semantic Scholar",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "Paper DOI",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (fallback)",
                    },
                },
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute an external API tool."""
    service = ExternalSearchService()

    try:
        if name == "lookup_paper_metadata":
            results = {}

            # Try DOI first if provided
            if arguments.get("doi"):
                doi = arguments["doi"]

                # Try CrossRef
                cr_results = await service._search_crossref_multi(f"doi:{doi}", limit=1)
                if cr_results:
                    results["crossref"] = {
                        "title": cr_results[0].title,
                        "authors": cr_results[0].authors,
                        "year": cr_results[0].year,
                        "doi": cr_results[0].doi,
                        "abstract": cr_results[0].abstract,
                        "journal": cr_results[0].journal,
                    }

                # Try Semantic Scholar for citation count
                ss_results = await service._search_semantic_scholar_query(
                    arguments.get("title", doi), limit=1
                )
                if ss_results:
                    results["semantic_scholar"] = {
                        "citation_count": ss_results[0].citation_count,
                        "pdf_url": ss_results[0].pdf_url,
                    }

            # Search by title if no DOI or no results
            elif arguments.get("title"):
                title = arguments["title"]

                # Try multiple sources
                oa_results = await service._search_openalex(title, limit=3)
                if oa_results:
                    best = max(
                        oa_results,
                        key=lambda r: service._title_similarity(title, r.title),
                    )
                    if service._title_similarity(title, best.title) > 0.7:
                        results["openalex"] = {
                            "title": best.title,
                            "authors": best.authors,
                            "year": best.year,
                            "doi": best.doi,
                            "abstract": best.abstract,
                        }

                cr_results = await service._search_crossref_multi(title, limit=3)
                if cr_results:
                    best = max(cr_results, key=lambda r: r.confidence)
                    if best.confidence > 0.7:
                        results["crossref"] = {
                            "title": best.title,
                            "authors": best.authors,
                            "year": best.year,
                            "doi": best.doi,
                            "abstract": best.abstract,
                        }

            if not results:
                return [TextContent(
                    type="text",
                    text="No metadata found. Try providing a DOI for better results.",
                )]

            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "find_open_access_pdf":
            pdf_urls = []

            # Try Unpaywall via DOI
            if arguments.get("doi"):
                try:
                    unpaywall_results = await service._search_unpaywall(arguments["doi"])
                    for r in unpaywall_results:
                        if r.pdf_url:
                            pdf_urls.append({
                                "source": "unpaywall",
                                "url": r.pdf_url,
                                "is_oa": True,
                            })
                except Exception as e:
                    logger.debug(f"Unpaywall lookup failed: {e}")

            # Try arXiv
            if arguments.get("arxiv_id"):
                arxiv_url = f"https://arxiv.org/pdf/{arguments['arxiv_id']}.pdf"
                pdf_urls.append({
                    "source": "arxiv",
                    "url": arxiv_url,
                    "is_oa": True,
                })
            elif arguments.get("title"):
                arxiv_results = await service._search_arxiv(arguments["title"], limit=1)
                for r in arxiv_results:
                    if r.pdf_url:
                        pdf_urls.append({
                            "source": "arxiv",
                            "url": r.pdf_url,
                            "is_oa": True,
                        })

            # Try Semantic Scholar
            if arguments.get("title") or arguments.get("doi"):
                query = arguments.get("doi") or arguments.get("title")
                ss_results = await service._search_semantic_scholar_query(query, limit=1)
                for r in ss_results:
                    if r.pdf_url:
                        pdf_urls.append({
                            "source": "semantic_scholar",
                            "url": r.pdf_url,
                            "is_oa": r.is_open_access,
                        })

            if not pdf_urls:
                return [TextContent(
                    type="text",
                    text="No open access PDF found. The paper may be behind a paywall.",
                )]

            return [TextContent(type="text", text=json.dumps(pdf_urls, indent=2))]

        elif name == "enrich_paper":
            # This would typically update the database
            # For now, just return the enrichment data
            enrichment = {}

            title = arguments.get("title", "")
            doi = arguments.get("doi")

            if doi:
                # Try CrossRef
                results = await service._search_crossref_multi(f"doi:{doi}", limit=1)
                if results and results[0].abstract:
                    enrichment["abstract"] = results[0].abstract
                    enrichment["source"] = "crossref"

            if not enrichment.get("abstract") and title:
                # Try OpenAlex
                results = await service._search_openalex(title, limit=1)
                if results and results[0].abstract:
                    enrichment["abstract"] = results[0].abstract
                    enrichment["source"] = "openalex"
                    if results[0].doi:
                        enrichment["doi"] = results[0].doi

            # Get citation count
            ss_results = await service._search_semantic_scholar_query(
                title or doi, limit=1
            )
            if ss_results and ss_results[0].citation_count is not None:
                enrichment["citation_count"] = ss_results[0].citation_count
                if ss_results[0].pdf_url:
                    enrichment["pdf_url"] = ss_results[0].pdf_url

            if not enrichment:
                return [TextContent(
                    type="text",
                    text="Could not find additional metadata for this paper.",
                )]

            return [TextContent(type="text", text=json.dumps(enrichment, indent=2))]

        elif name == "search_external_papers":
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            sources = arguments.get("sources", ["crossref", "openalex", "semantic_scholar"])

            all_results = {}

            if "crossref" in sources:
                results = await service._search_crossref_multi(query, limit=limit)
                all_results["crossref"] = [
                    {
                        "title": r.title,
                        "authors": r.authors,
                        "year": r.year,
                        "doi": r.doi,
                        "journal": r.journal,
                    }
                    for r in results
                ]

            if "openalex" in sources:
                results = await service._search_openalex(query, limit=limit)
                all_results["openalex"] = [
                    {
                        "title": r.title,
                        "authors": r.authors,
                        "year": r.year,
                        "doi": r.doi,
                        "abstract": r.abstract[:200] + "..." if r.abstract and len(r.abstract) > 200 else r.abstract,
                    }
                    for r in results
                ]

            if "semantic_scholar" in sources:
                results = await service._search_semantic_scholar_query(query, limit=limit)
                all_results["semantic_scholar"] = [
                    {
                        "title": r.title,
                        "authors": r.authors,
                        "year": r.year,
                        "doi": r.doi,
                        "citation_count": r.citation_count,
                    }
                    for r in results
                ]

            if "arxiv" in sources:
                results = await service._search_arxiv(query, limit=limit)
                all_results["arxiv"] = [
                    {
                        "title": r.title,
                        "authors": r.authors,
                        "year": r.year,
                        "arxiv_id": r.arxiv_id,
                        "pdf_url": r.pdf_url,
                    }
                    for r in results
                ]

            return [TextContent(type="text", text=json.dumps(all_results, indent=2))]

        elif name == "get_citation_count":
            query = arguments.get("doi") or arguments.get("title")
            if not query:
                return [TextContent(
                    type="text",
                    text="Please provide either a DOI or title.",
                )]

            results = await service._search_semantic_scholar_query(query, limit=1)
            if results and results[0].citation_count is not None:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "title": results[0].title,
                        "citation_count": results[0].citation_count,
                        "source": "semantic_scholar",
                    }, indent=2),
                )]

            return [TextContent(
                type="text",
                text="Could not find citation count for this paper.",
            )]

        else:
            return [TextContent(type="text", text=f"Unknown external tool: {name}")]

    except Exception as e:
        logger.error(f"External API tool error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
