"""
Paper Management Tools for MCP Server.

These tools provide CRUD operations and content access for papers
via the literature-database API.
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
                        "description": "Maximum papers to return (default: 20, max: 100)",
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
            description="Get full paper content for AI analysis (title, abstract, full text)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to get content for",
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
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a paper tool."""
    api_url = get_api_url()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if name == "list_papers":
                params = {
                    "limit": min(arguments.get("limit", 20), 100),
                    "offset": arguments.get("offset", 0),
                }
                for key in ["author", "year", "tag", "read_status"]:
                    if key in arguments:
                        params[key] = arguments[key]

                response = await client.get(f"{api_url}/papers", params=params)
                response.raise_for_status()
                data = response.json()

                # Format response
                papers = data.get("items", data) if isinstance(data, dict) else data
                result = {
                    "total": data.get("total", len(papers)) if isinstance(data, dict) else len(papers),
                    "papers": [
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "year": p.get("year"),
                            "authors": [
                                a.get("name", a) if isinstance(a, dict) else a
                                for a in p.get("authors", [])
                            ],
                            "read_status": p.get("read_status"),
                            "rating": p.get("rating"),
                        }
                        for p in papers
                    ],
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "get_paper":
                paper_id = arguments["paper_id"]
                response = await client.get(f"{api_url}/papers/{paper_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "search_papers":
                response = await client.post(
                    f"{api_url}/search",
                    json={
                        "query": arguments["query"],
                        "limit": arguments.get("limit", 10),
                    },
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "add_paper":
                response = await client.post(f"{api_url}/papers", json=arguments)
                response.raise_for_status()
                paper = response.json()
                return [TextContent(
                    type="text",
                    text=f"Paper added successfully with ID: {paper['id']}\n{json.dumps(paper, indent=2)}",
                )]

            elif name == "update_paper":
                paper_id = arguments.pop("paper_id")
                # Get current paper first
                current = await client.get(f"{api_url}/papers/{paper_id}")
                current.raise_for_status()
                paper_data = current.json()

                # Convert authors/tags if they're objects
                if "authors" in paper_data and paper_data["authors"]:
                    if isinstance(paper_data["authors"][0], dict):
                        paper_data["authors"] = [
                            a.get("name", "") for a in paper_data["authors"]
                        ]
                if "tags" in paper_data and paper_data["tags"]:
                    if isinstance(paper_data["tags"][0], dict):
                        paper_data["tags"] = [
                            t.get("name", "") for t in paper_data["tags"]
                        ]
                paper_data.pop("collections", None)

                # Merge updates
                paper_data.update(arguments)

                response = await client.put(f"{api_url}/papers/{paper_id}", json=paper_data)
                response.raise_for_status()
                return [TextContent(
                    type="text",
                    text=f"Paper {paper_id} updated successfully",
                )]

            elif name == "get_paper_content":
                paper_id = arguments["paper_id"]
                response = await client.get(
                    f"{api_url}/integration/papers/{paper_id}/content"
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "store_extraction":
                paper_id = arguments.pop("paper_id")
                content = {
                    "extraction_depth": "COMPREHENSIVE",
                    "extractor_model": "claude-code",
                    **arguments,
                }
                response = await client.post(
                    f"{api_url}/papers/{paper_id}/content",
                    json=content,
                )
                if response.status_code == 409:
                    # Already exists, update instead
                    response = await client.put(
                        f"{api_url}/papers/{paper_id}/content",
                        json=content,
                    )
                response.raise_for_status()
                return [TextContent(
                    type="text",
                    text=f"Extraction stored for paper {paper_id}",
                )]

            elif name == "get_extraction_queue":
                limit = arguments.get("limit", 20)
                response = await client.get(
                    f"{api_url}/extraction/queue",
                    params={"limit": limit},
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown paper tool: {name}")]

        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code} - {e.response.text}")
            return [TextContent(
                type="text",
                text=f"API Error: {e.response.status_code} - {e.response.text[:500]}",
            )]
        except Exception as e:
            logger.error(f"Tool error: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]
