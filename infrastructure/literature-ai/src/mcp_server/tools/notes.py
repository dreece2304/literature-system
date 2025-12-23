"""MCP Tools for Note management."""
import json
import os
from typing import Any

import httpx
from mcp.types import Tool, TextContent

API_BASE_URL = os.getenv("LITERATURE_DB_URL", "http://localhost:8001")


async def list_tools() -> list[Tool]:
    """Return available note tools."""
    return [
        Tool(
            name="list_notes",
            description="List notes with optional filtering by paper_id or note_type",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Filter by paper ID",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["highlight", "comment", "summary"],
                        "description": "Filter by note type",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Maximum notes to return",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Skip first N notes",
                    },
                },
            },
        ),
        Tool(
            name="get_note",
            description="Get a note by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "The note ID",
                    },
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="create_note",
            description="Create a new note on a paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "The paper ID to attach note to",
                    },
                    "content": {
                        "type": "string",
                        "description": "Note content",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["highlight", "comment", "summary"],
                        "default": "comment",
                        "description": "Type of note",
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Page number in PDF",
                    },
                    "position": {
                        "type": "string",
                        "description": "Position coordinates (JSON string)",
                    },
                },
                "required": ["paper_id", "content"],
            },
        ),
        Tool(
            name="update_note",
            description="Update a note's content or metadata",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "The note ID to update",
                    },
                    "content": {
                        "type": "string",
                        "description": "New note content",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["highlight", "comment", "summary"],
                        "description": "New note type",
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "New page number",
                    },
                    "position": {
                        "type": "string",
                        "description": "New position coordinates",
                    },
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="delete_note",
            description="Delete a note",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "The note ID to delete",
                    },
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="get_paper_notes",
            description="Get all notes for a specific paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "The paper ID",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["highlight", "comment", "summary"],
                        "description": "Filter by note type",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="delete_paper_notes",
            description="Delete all notes for a paper (optionally filtered by type)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "The paper ID",
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["highlight", "comment", "summary"],
                        "description": "Only delete notes of this type",
                    },
                },
                "required": ["paper_id"],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a note tool."""
    api_url = f"{API_BASE_URL}/api/v1/notes"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if name == "list_notes":
                params = {}
                if "paper_id" in arguments:
                    params["paper_id"] = arguments["paper_id"]
                if "note_type" in arguments:
                    params["note_type"] = arguments["note_type"]
                if "limit" in arguments:
                    params["limit"] = arguments["limit"]
                if "offset" in arguments:
                    params["offset"] = arguments["offset"]

                response = await client.get(api_url, params=params)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "get_note":
                note_id = arguments["note_id"]
                response = await client.get(f"{api_url}/{note_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "create_note":
                payload = {
                    "paper_id": arguments["paper_id"],
                    "content": arguments["content"],
                }
                if "note_type" in arguments:
                    payload["note_type"] = arguments["note_type"]
                if "page_number" in arguments:
                    payload["page_number"] = arguments["page_number"]
                if "position" in arguments:
                    payload["position"] = arguments["position"]

                response = await client.post(api_url, json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "update_note":
                note_id = arguments["note_id"]
                payload = {}
                if "content" in arguments:
                    payload["content"] = arguments["content"]
                if "note_type" in arguments:
                    payload["note_type"] = arguments["note_type"]
                if "page_number" in arguments:
                    payload["page_number"] = arguments["page_number"]
                if "position" in arguments:
                    payload["position"] = arguments["position"]

                response = await client.put(f"{api_url}/{note_id}", json=payload)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "delete_note":
                note_id = arguments["note_id"]
                response = await client.delete(f"{api_url}/{note_id}")
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "get_paper_notes":
                paper_id = arguments["paper_id"]
                params = {}
                if "note_type" in arguments:
                    params["note_type"] = arguments["note_type"]

                response = await client.get(f"{api_url}/paper/{paper_id}", params=params)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            elif name == "delete_paper_notes":
                paper_id = arguments["paper_id"]
                params = {}
                if "note_type" in arguments:
                    params["note_type"] = arguments["note_type"]

                response = await client.delete(f"{api_url}/paper/{paper_id}", params=params)
                response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown note tool: {name}")]

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else str(e)
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"HTTP {e.response.status_code}", "detail": error_detail})
            )]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
