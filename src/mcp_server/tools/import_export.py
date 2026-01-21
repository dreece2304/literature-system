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
# import_export.py is at src/mcp_server/tools/import_export.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    error,
    serialize,
    CollectionNotFoundError,
    ValidationError,
    LiteratureError,
)
from services import ImportExportService, PaperImportService

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
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Maximum papers to return (default: 50, max: 500)",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Number of papers to skip for pagination",
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
        Tool(
            name="import_paper_wizard",
            description="Smart import via DOI/arXiv/title with duplicate detection and metadata fetching",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "DOI to import (most reliable method)",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID to import (e.g., '2301.12345')",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title to search for (use with authors/year for disambiguation)",
                    },
                    "authors": {
                        "type": "string",
                        "description": "Author names for disambiguation when searching by title",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Publication year for disambiguation when searching by title",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to the imported paper",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Collection to add the paper to",
                    },
                    "pdf_path": {
                        "type": "string",
                        "description": "Local path to PDF file to attach",
                    },
                    "skip_duplicate_check": {
                        "type": "boolean",
                        "default": False,
                        "description": "Skip duplicate detection (use with caution)",
                    },
                    "auto_chunk_pdf": {
                        "type": "boolean",
                        "default": True,
                        "description": "Automatically extract and chunk PDF text if provided",
                    },
                },
            },
        ),
        Tool(
            name="get_enrichment_queue",
            description="Papers needing enrichment (missing abstract, PDF, or chunks)",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["needs_abstract", "needs_pdf", "needs_chunks", "pending", "failed"],
                        "description": "Filter by specific enrichment status",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum papers to return",
                    },
                },
            },
        ),
    ]


# ============================================================================
# Tool Implementations - Thin wrappers over ImportExportService
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


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
    # Cap limit at 500 to prevent token overflow
    limit = min(arguments.get("limit", 50), 500)
    offset = arguments.get("offset", 0)

    output = ImportExportService.export_papers(
        paper_ids=arguments.get("paper_ids"),
        format=arguments.get("format", "bibtex"),
        include_abstract=arguments.get("include_abstract", True),
        include_notes=arguments.get("include_notes", False),
        limit=limit,
        offset=offset,
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


async def _import_paper_wizard(arguments: dict[str, Any]) -> list[TextContent]:
    """Import paper using the unified wizard workflow."""
    from dataclasses import asdict

    result = await PaperImportService.import_paper(
        doi=arguments.get("doi"),
        arxiv_id=arguments.get("arxiv_id"),
        title=arguments.get("title"),
        authors=arguments.get("authors"),
        year=arguments.get("year"),
        tags=arguments.get("tags"),
        collection_id=arguments.get("collection_id"),
        pdf_path=arguments.get("pdf_path"),
        skip_duplicate_check=arguments.get("skip_duplicate_check", False),
        auto_chunk_pdf=arguments.get("auto_chunk_pdf", True),
    )

    response = {
        "status": result.status,
        "sources_checked": result.sources_checked,
    }

    if result.status == "success":
        response["paper"] = result.paper
        response["provenance"] = {
            "metadata_source": result.metadata_source,
            "metadata_confidence": result.metadata_confidence,
            "sources_used": result.sources_used,
        }
        response["enrichment"] = {
            "status": result.enrichment_status,
            "missing_fields": result.missing_fields,
        }
        if result.warnings:
            response["warnings"] = result.warnings

    elif result.status == "duplicate":
        if result.duplicate_info:
            response["duplicate"] = {
                "match_type": result.duplicate_info.match_type,
                "existing_paper_id": result.duplicate_info.existing_paper_id,
                "existing_paper_title": result.duplicate_info.existing_paper_title,
                "similarity": result.duplicate_info.similarity,
            }

    if result.message:
        response["message"] = result.message

    return _to_response(response)


def _get_enrichment_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers needing enrichment."""
    papers = PaperImportService.get_enrichment_queue(
        status=arguments.get("status"),
        limit=arguments.get("limit", 20),
    )

    return _to_response({
        "count": len(papers),
        "papers": papers,
    })


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
    # Sync tools
    sync_tool_map = {
        "import_bibtex": _import_bibtex,
        "export_papers": _export_papers,
        "export_collection": _export_collection,
        "get_enrichment_queue": _get_enrichment_queue,
    }

    # Async tools
    async_tools = {"import_from_external", "import_paper_wizard"}

    all_tools = set(sync_tool_map.keys()) | async_tools
    if name not in all_tools:
        return _to_response(error(f"Unknown import/export tool: {name}", code="UNKNOWN_TOOL"))

    try:
        if name == "import_from_external":
            return await _import_from_external(arguments)
        if name == "import_paper_wizard":
            return await _import_paper_wizard(arguments)
        return sync_tool_map[name](arguments)

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
