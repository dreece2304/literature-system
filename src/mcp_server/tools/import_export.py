"""Import/Export Tools for MCP Server.

These tools provide BibTeX import/export and external paper import.
This module is a thin wrapper over ImportExportService.

Architecture:
    MCP Tool (this file) -> ImportExportService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    success,
    error,
    CollectionNotFoundError,
    ValidationError,
    LiteratureError,
)
from services import ImportExportService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """Return available import/export tools."""
    return [
        Tool(
            name="import_bibtex",
            description="Import papers from BibTeX content. Parses entries and adds papers to the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bibtex_content": {
                        "type": "string",
                        "description": "Raw BibTeX content to parse and import",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to all imported papers",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Add imported papers to this collection",
                    },
                },
                "required": ["bibtex_content"],
            },
        ),
        Tool(
            name="export_papers",
            description="Export papers from the database in various formats",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to export (omit for all papers)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "json", "csv"],
                        "default": "bibtex",
                        "description": "Export format",
                    },
                    "include_abstract": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include abstracts in export",
                    },
                    "include_notes": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include notes in export (JSON only)",
                    },
                },
            },
        ),
        Tool(
            name="import_from_external",
            description="Import a paper from external search results (using DOI, arXiv ID, or title lookup)",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "DOI of paper to import",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID of paper to import",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title of paper to look up and import",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to imported paper",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Add imported paper to this collection",
                    },
                },
            },
        ),
        Tool(
            name="export_collection",
            description="Export all papers in a collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "Collection ID to export",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "json", "csv"],
                        "default": "bibtex",
                        "description": "Export format",
                    },
                    "include_subcollections": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include papers from child collections",
                    },
                },
                "required": ["collection_id"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations - Thin wrappers over ImportExportService
# ============================================================================


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _import_bibtex(arguments: dict[str, Any]) -> list[TextContent]:
    """Import papers from BibTeX content."""
    result = ImportExportService.import_bibtex(
        bibtex_content=arguments["bibtex_content"],
        tags=arguments.get("tags"),
        collection_id=arguments.get("collection_id"),
    )

    return _to_response({
        "status": result.status,
        "total_entries": result.total_entries,
        "imported": len(result.imported),
        "skipped": len(result.skipped),
        "failed": len(result.failed),
        "details": {
            "imported": [asdict(p) for p in result.imported],
            "skipped": [asdict(p) for p in result.skipped],
            "failed": [asdict(p) for p in result.failed],
        },
    })


def _export_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Export papers in various formats."""
    output = ImportExportService.export_papers(
        paper_ids=arguments.get("paper_ids"),
        format=arguments.get("format", "bibtex"),
        include_abstract=arguments.get("include_abstract", True),
        include_notes=arguments.get("include_notes", False),
    )

    # For bibtex/csv, return raw text; for json it's already formatted
    return [TextContent(type="text", text=output)]


async def _import_from_external(arguments: dict[str, Any]) -> list[TextContent]:
    """Import a paper from external sources."""
    result = await ImportExportService.import_from_external(
        doi=arguments.get("doi"),
        arxiv_id=arguments.get("arxiv_id"),
        title=arguments.get("title"),
        tags=arguments.get("tags"),
        collection_id=arguments.get("collection_id"),
    )

    result_dict = {
        "status": result.status,
        "sources_checked": result.sources_checked,
    }

    if result.paper:
        result_dict["paper"] = result.paper
    if result.paper_id:
        result_dict["paper_id"] = result.paper_id
    if result.title:
        result_dict["title"] = result.title
    if result.message:
        result_dict["message"] = result.message

    return _to_response(result_dict)


def _export_collection(arguments: dict[str, Any]) -> list[TextContent]:
    """Export all papers in a collection."""
    output = ImportExportService.export_collection(
        collection_id=arguments["collection_id"],
        format=arguments.get("format", "bibtex"),
        include_subcollections=arguments.get("include_subcollections", False),
    )

    return [TextContent(type="text", text=output)]


# ============================================================================
# Main entry point
# ============================================================================


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute an import/export tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "import_bibtex": _import_bibtex,
        "export_papers": _export_papers,
        "export_collection": _export_collection,
    }

    if name not in tool_map and name != "import_from_external":
        return _to_response(error(f"Unknown import/export tool: {name}", code="UNKNOWN_TOOL"))

    try:
        if name == "import_from_external":
            return await _import_from_external(arguments)
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
