"""Notes Management Tools for MCP Server.

These tools provide CRUD operations for paper notes/annotations.
This module is a thin wrapper over NoteService.

Architecture:
    MCP Tool (this file) -> NoteService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# notes.py is at src/mcp_server/tools/notes.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    success,
    error,
    paginated,
    created,
    deleted,
    serialize,
    NoteNotFoundError,
    PaperNotFoundError,
    ValidationError,
    LiteratureError,
)
from services import NoteService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List notes management tools."""
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
                        "description": "Maximum notes to return",
                        "default": 50,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Skip first N notes",
                        "default": 0,
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
                        "description": "Type of note",
                        "default": "comment",
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


# ============================================================================
# Tool Implementations - Thin wrappers over NoteService
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


def _list_notes(arguments: dict[str, Any]) -> list[TextContent]:
    """List notes with optional filtering."""
    limit = arguments.get("limit", 50)
    offset = arguments.get("offset", 0)

    result = NoteService.list(
        paper_id=arguments.get("paper_id"),
        note_type=arguments.get("note_type"),
        limit=limit,
        offset=offset,
    )
    return _to_response(
        paginated(
            items=result.notes,
            total=result.total,
            limit=limit,
            offset=offset,
        )
    )


def _get_note(arguments: dict[str, Any]) -> list[TextContent]:
    """Get a note by ID."""
    note = NoteService.get(arguments["note_id"])
    return _to_response(success(note))


def _create_note(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a new note."""
    note = NoteService.create(
        paper_id=arguments["paper_id"],
        content=arguments["content"],
        note_type=arguments.get("note_type", "comment"),
        page_number=arguments.get("page_number"),
        position=arguments.get("position"),
    )
    return _to_response(
        created(note, message=f"Note created with ID: {note['id']}")
    )


def _update_note(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing note."""
    note_id = arguments["note_id"]
    note = NoteService.update(
        note_id=note_id,
        content=arguments.get("content"),
        note_type=arguments.get("note_type"),
        page_number=arguments.get("page_number"),
        position=arguments.get("position"),
    )
    return _to_response(success(note, message=f"Note {note_id} updated"))


def _delete_note(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete a note."""
    result = NoteService.delete(arguments["note_id"])
    return _to_response(
        deleted("note", result["id"], message="Note deleted")
    )


def _get_paper_notes(arguments: dict[str, Any]) -> list[TextContent]:
    """Get all notes for a paper."""
    paper_id = arguments["paper_id"]
    notes = NoteService.get_for_paper(
        paper_id=paper_id,
        note_type=arguments.get("note_type"),
    )
    return _to_response(
        success({
            "paper_id": paper_id,
            "count": len(notes),
            "notes": notes,
        })
    )


def _delete_paper_notes(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete all notes for a paper."""
    paper_id = arguments["paper_id"]
    note_type = arguments.get("note_type")

    count = NoteService.delete_for_paper(
        paper_id=paper_id,
        note_type=note_type,
    )
    return _to_response(
        success({
            "paper_id": paper_id,
            "deleted_count": count,
            "filter": note_type or "all",
        }, message=f"Deleted {count} notes")
    )


# ============================================================================
# Main entry point
# ============================================================================

async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a notes tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "list_notes": _list_notes,
        "get_note": _get_note,
        "create_note": _create_note,
        "update_note": _update_note,
        "delete_note": _delete_note,
        "get_paper_notes": _get_paper_notes,
        "delete_paper_notes": _delete_paper_notes,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown notes tool: {name}", code="UNKNOWN_TOOL"))

    try:
        return tool_map[name](arguments)

    except NoteNotFoundError as e:
        logger.warning(f"Note not found: {e.note_id}")
        return _to_response(
            error(str(e), code=e.code, details={"note_id": e.note_id})
        )

    except PaperNotFoundError as e:
        logger.warning(f"Paper not found: {e.paper_id}")
        return _to_response(
            error(str(e), code=e.code, details={"paper_id": e.paper_id})
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
