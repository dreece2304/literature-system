"""Collection Management Tools for MCP Server.

These tools provide CRUD operations and paper associations for collections.
This module is a thin wrapper over CollectionService.

Architecture:
    MCP Tool (this file) -> CollectionService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# collections.py is at src/mcp_server/tools/collections.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    success,
    error,
    created,
    deleted,
    CollectionNotFoundError,
    ValidationError,
    LiteratureError,
)
from services import CollectionService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List collection management tools."""
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


# ============================================================================
# Tool Implementations - Thin wrappers over CollectionService
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _list_collections(arguments: dict[str, Any]) -> list[TextContent]:
    """List collections with optional hierarchy filtering."""
    result = CollectionService.list(
        parent_id=arguments.get("parent_id"),
        list_all=arguments.get("all", False),
    )
    return _to_response(
        success({
            "count": result.count,
            "collections": result.collections,
        })
    )


def _get_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Get a collection by ID."""
    collection = CollectionService.get(arguments["collection_id"])
    return _to_response(success(collection))


def _create_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a new collection."""
    collection = CollectionService.create(
        name=arguments["name"],
        description=arguments.get("description"),
        parent_id=arguments.get("parent_id"),
    )
    return _to_response(
        created(collection, message=f"Collection '{collection['name']}' created")
    )


def _update_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing collection."""
    collection_id = arguments["collection_id"]
    collection = CollectionService.update(
        collection_id=collection_id,
        name=arguments.get("name"),
        description=arguments.get("description"),
        parent_id=arguments.get("parent_id"),
    )
    return _to_response(
        success(collection, message=f"Collection {collection_id} updated")
    )


def _delete_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete a collection."""
    result = CollectionService.delete(arguments["collection_id"])
    return _to_response(
        deleted("collection", result["id"], message=f"Collection '{result['name']}' deleted")
    )


def _add_papers_to_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Add papers to a collection."""
    result = CollectionService.add_papers(
        collection_id=arguments["collection_id"],
        paper_ids=arguments["paper_ids"],
    )
    return _to_response(
        success({
            "added": result.processed,
            "already_in_collection": result.skipped,
        }, message=f"Added {len(result.processed)} papers")
    )


def _remove_papers_from_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Remove papers from a collection."""
    result = CollectionService.remove_papers(
        collection_id=arguments["collection_id"],
        paper_ids=arguments["paper_ids"],
    )
    return _to_response(
        success({
            "removed": result.processed,
            "not_in_collection": result.skipped,
        }, message=f"Removed {len(result.processed)} papers")
    )


def _get_collection_children(arguments: dict[str, Any]) -> list[TextContent]:
    """Get child collections."""
    collection_id = arguments["collection_id"]
    result = CollectionService.get_children(collection_id)
    return _to_response(
        success({
            "parent_id": collection_id,
            "count": result.count,
            "children": result.collections,
        })
    )


# ============================================================================
# Main entry point
# ============================================================================

async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a collection tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "list_collections": _list_collections,
        "get_collection": _get_collection,
        "create_collection": _create_collection,
        "update_collection": _update_collection,
        "delete_collection": _delete_collection,
        "add_papers_to_collection": _add_papers_to_collection,
        "remove_papers_from_collection": _remove_papers_from_collection,
        "get_collection_children": _get_collection_children,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown collection tool: {name}", code="UNKNOWN_TOOL"))

    try:
        return tool_map[name](arguments)

    except CollectionNotFoundError as e:
        logger.warning(f"Collection not found: {e.collection_id}")
        return _to_response(
            error(str(e), code=e.code, details={"collection_id": e.collection_id})
        )

    except ValidationError as e:
        logger.warning(f"Validation error: {e.message}")
        return _to_response(
            error(str(e), code=e.code, details={"field": e.field})
        )

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
