"""
Search Tools for MCP Server.

These tools provide keyword and semantic search capabilities
for finding papers in the literature database.
"""

import json
from typing import Any

import httpx
from mcp.types import Tool, TextContent
from loguru import logger

from config.settings import settings


def get_api_url() -> str:
    """Get the literature-database API URL."""
    base = settings.litdb.api_url.rstrip('/')
    if not base.endswith('/api/v1'):
        base = f"{base}/api/v1"
    return base


async def list_tools() -> list[Tool]:
    """List search tools."""
    return [
        Tool(
            name="keyword_search",
            description=(
                "Full-text keyword search across papers. "
                "Searches title, abstract, and full text using Whoosh index."
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
                "Semantic similarity search using embeddings. "
                "Finds papers with similar meaning/concepts to your query, "
                "even if exact keywords don't match."
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


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a search tool."""
    api_url = get_api_url()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if name == "keyword_search":
                # Use the search endpoint
                search_params = {
                    "query": arguments["query"],
                    "limit": arguments.get("limit", 10),
                }

                response = await client.post(f"{api_url}/search", json=search_params)
                response.raise_for_status()
                data = response.json()

                # Format results - API returns {"paper": {...}, "score": ...} structure
                papers = data.get("papers", [])
                formatted_papers = []
                for p in papers:
                    paper_data = p.get("paper", {})
                    abstract = paper_data.get("abstract", "")
                    formatted_papers.append({
                        "id": paper_data.get("id"),
                        "title": paper_data.get("title"),
                        "year": paper_data.get("year"),
                        "authors": [
                            a.get("name", a) if isinstance(a, dict) else a
                            for a in paper_data.get("authors", [])
                        ],
                        "score": p.get("score", 0),
                        "abstract_preview": (
                            abstract[:200] + "..." if abstract and len(abstract) > 200
                            else abstract
                        ),
                    })
                result = {
                    "query": arguments["query"],
                    "total_results": len(papers),
                    "papers": formatted_papers,
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "semantic_search":
                # For semantic search, we need to use the literature-ai embedding service
                # For now, fall back to keyword search if vector store isn't available
                try:
                    # Try to import and use the search service
                    from src.services.search_service import SearchService

                    search_service = SearchService()
                    results = search_service.search(
                        query=arguments["query"],
                        top_k=arguments.get("limit", 10),
                        score_threshold=arguments.get("min_similarity", 0.5),
                    )

                    formatted = {
                        "query": arguments["query"],
                        "search_type": "semantic",
                        "total_results": len(results),
                        "papers": [
                            {
                                "id": r.paper_id,
                                "title": r.title,
                                "similarity": round(r.score, 3),
                                "preview": r.text[:200] + "..." if len(r.text) > 200 else r.text,
                            }
                            for r in results
                        ],
                    }
                    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]

                except ImportError:
                    # Fall back to keyword search
                    logger.warning("SearchService not available, falling back to keyword search")
                    return await call_tool("keyword_search", arguments)

            elif name == "search_by_author":
                params = {
                    "author": arguments["author_name"],
                    "limit": arguments.get("limit", 20),
                }
                response = await client.get(f"{api_url}/papers", params=params)
                response.raise_for_status()
                data = response.json()

                papers = data.get("items", data) if isinstance(data, dict) else data
                result = {
                    "author_query": arguments["author_name"],
                    "total_results": len(papers),
                    "papers": [
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "year": p.get("year"),
                            "authors": [
                                a.get("name", a) if isinstance(a, dict) else a
                                for a in p.get("authors", [])
                            ],
                        }
                        for p in papers
                    ],
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "search_by_tag":
                params = {
                    "tag": arguments["tag"],
                    "limit": arguments.get("limit", 20),
                }
                response = await client.get(f"{api_url}/papers", params=params)
                response.raise_for_status()
                data = response.json()

                papers = data.get("items", data) if isinstance(data, dict) else data
                result = {
                    "tag": arguments["tag"],
                    "total_results": len(papers),
                    "papers": [
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "year": p.get("year"),
                            "tags": [
                                t.get("name", t) if isinstance(t, dict) else t
                                for t in p.get("tags", [])
                            ],
                        }
                        for p in papers
                    ],
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown search tool: {name}")]

        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code} - {e.response.text}")
            return [TextContent(
                type="text",
                text=f"API Error: {e.response.status_code} - {e.response.text[:500]}",
            )]
        except Exception as e:
            logger.error(f"Search tool error: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]
