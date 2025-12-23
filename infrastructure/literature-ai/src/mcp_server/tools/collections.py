"""MCP Tools for Collection management."""
import json
import os
from typing import Any

import httpx
from mcp.types import Tool, TextContent

API_BASE_URL = os.getenv("LITERATURE_DB_URL", "http://localhost:8001")


async def list_tools() -> list[Tool]:
    """Return available collection tools."""
    return [
        Tool(
            name="list_collections",
            description="List all collections (optionally filter by parent_id for hierarchy)",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {
                        "type": "integer",
                        "description": "Filter to children of this collection (omit for root collections)",
                    },
                    "all": {
                        "type": "boolean",
                        "description": "If true, list all collections ignoring hierarchy",
                    },
                },
            },
        ),
        Tool(
            name="get_collection",
            description="Get a collection by ID with paper count and paper IDs",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The collection ID",
                    },
                },
                "required": ["collection_id"],
            },
        ),
        Tool(
            name="create_collection",
            description="Create a new collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Collection name",
                    },
                    "description": {
                        "type": "string",
                        "description": "Collection description",
                    },
                    "parent_id": {
                        "type": "integer",
                        "description": "Parent collection ID for nesting",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_collection",
            description="Update a collection's name, description, or parent",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The collection ID to update",
                    },
                    "name": {
                        "type": "string",
                        "description": "New collection name",
                    },
                    "description": {
                        "type": "string",
                        "description": "New collection description",
                    },
                    "parent_id": {
                        "type": "integer",
                        "description": "New parent collection ID",
                    },
                },
                "required": ["collection_id"],
            },
        ),
        Tool(
            name="delete_collection",
            description="Delete a collection (papers are NOT deleted, just unlinked)",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The collection ID to delete",
                    },
                },
                "required": ["collection_id"],
            },
        ),
        Tool(
            name="add_papers_to_collection",
            description="Add one or more papers to a collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The collection ID",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to add",
                    },
                },
                "required": ["collection_id", "paper_ids"],
            },
        ),
        Tool(
            name="remove_papers_from_collection",
            description="Remove one or more papers from a collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The collection ID",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to remove",
                    },
                },
                "required": ["collection_id", "paper_ids"],
            },
        ),
        Tool(
            name="get_collection_children",
            description="Get child collections of a collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "The parent collection ID",
                    },
                },
                "required": ["collection_id"],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a collection tool."""
    api_url = f"{API_BASE_URL}/api/v1/collections"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if name == "list_collections":
                if arguments.get("all"):
                    url = f"{api_url}/all"
                    response = await client.get(url)
                else:
                    params = {}
                    if "parent_id" in arguments:
                        params["parent_id"] = arguments["parent_id"]
                    response = await client.get(api_url, params=params)

                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "get_collection":
                collection_id = arguments["collection_id"]
                response = await client.get(f"{api_url}/{collection_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "create_collection":
                payload = {"name": arguments["name"]}
                if "description" in arguments:
                    payload["description"] = arguments["description"]
                if "parent_id" in arguments:
                    payload["parent_id"] = arguments["parent_id"]

                response = await client.post(api_url, json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "update_collection":
                collection_id = arguments["collection_id"]
                payload = {}
                if "name" in arguments:
                    payload["name"] = arguments["name"]
                if "description" in arguments:
                    payload["description"] = arguments["description"]
                if "parent_id" in arguments:
                    payload["parent_id"] = arguments["parent_id"]

                response = await client.put(f"{api_url}/{collection_id}", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "delete_collection":
                collection_id = arguments["collection_id"]
                response = await client.delete(f"{api_url}/{collection_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "add_papers_to_collection":
                collection_id = arguments["collection_id"]
                paper_ids = arguments["paper_ids"]
                response = await client.post(
                    f"{api_url}/{collection_id}/papers",
                    json={"paper_ids": paper_ids}
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "remove_papers_from_collection":
                collection_id = arguments["collection_id"]
                paper_ids = arguments["paper_ids"]
                response = await client.request(
                    "DELETE",
                    f"{api_url}/{collection_id}/papers",
                    json={"paper_ids": paper_ids}
                )
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "get_collection_children":
                collection_id = arguments["collection_id"]
                response = await client.get(f"{api_url}/{collection_id}/children")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown collection tool: {name}")]

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else str(e)
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"HTTP {e.response.status_code}", "detail": error_detail})
            )]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
