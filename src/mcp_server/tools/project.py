"""Project Citation Tools for MCP Server.

These tools provide BibTeX parsing, TeX citation scanning, health checks,
and database synchronization for managing citations in research projects.
This module is a thin wrapper over CitationService.

Architecture:
    MCP Tool (this file) -> CitationService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# project.py is at src/mcp_server/tools/project.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import (
    get_logger,
    error,
    serialize,
    ValidationError,
    LiteratureError,
)
from services import CitationService, ImportExportService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """Return available project management tools."""
    return [
        # BibTeX File Tools
        Tool(
            name="parse_bib_file",
            description="Parse a BibTeX file and return structured entries with keys and fields",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the .bib file",
                    },
                    "content": {
                        "type": "string",
                        "description": "BibTeX content (alternative to file_path)",
                    },
                },
            },
        ),
        Tool(
            name="link_bib_to_database",
            description="Match BibTeX entries to papers in database by DOI, title, or author+year",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the .bib file to link",
                    },
                    "content": {
                        "type": "string",
                        "description": "BibTeX content (alternative to file_path)",
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.8,
                        "description": "Minimum title similarity for matching (0-1)",
                    },
                },
            },
        ),
        # Citation Scanning Tools
        Tool(
            name="scan_tex_citations",
            description="Scan TeX files for all \\cite{} commands and extract keys with locations",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory to scan",
                    },
                    "recursive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Recursively scan directories",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_citation_locations",
            description="Get all locations where a specific citation key is used",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory to scan",
                    },
                    "citation_key": {
                        "type": "string",
                        "description": "The citation key to find",
                    },
                },
                "required": ["file_path", "citation_key"],
            },
        ),
        # Health Check Tools
        Tool(
            name="citation_health_check",
            description="Comprehensive check: orphan bib entries, missing citations, incomplete entries, duplicates",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_orphan_citations",
            description="Find bib entries that are never cited in any .tex file",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_missing_citations",
            description="Find citation keys used in .tex files but not in .bib file",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_incomplete_bib_entries",
            description="Find bib entries missing required fields (author, title, year)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="find_duplicate_bib_entries",
            description="Find duplicate bib entries (same DOI or very similar titles)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "default": 0.9,
                        "description": "Title similarity threshold for duplicates (0-1)",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        # Sync Tools
        Tool(
            name="sync_bib_from_database",
            description="Update bib entries with latest metadata from database (by DOI match)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file to update",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, show changes without writing",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="import_bib_to_database",
            description="Import papers from .bib file into the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "skip_existing": {
                        "type": "boolean",
                        "default": True,
                        "description": "Skip entries already in database (by DOI)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to imported papers",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="export_database_to_bib",
            description="Export papers from database to BibTeX format",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paper IDs to export (omit for all)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path to write .bib file (omit to return content)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Export only papers with this tag",
                    },
                },
            },
        ),
        # Project Config Tools
        Tool(
            name="get_project_config",
            description="Get project citation configuration (bib files, tex paths, settings)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root",
                    },
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="set_project_config",
            description="Set project citation configuration",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root",
                    },
                    "bib_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of .bib file paths (relative to project)",
                    },
                    "tex_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of .tex file/directory paths",
                    },
                },
                "required": ["project_path"],
            },
        ),
    ]


# ============================================================================
# Tool Implementations - Thin wrappers over CitationService
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


def _parse_bib_file(arguments: dict[str, Any]) -> list[TextContent]:
    """Parse a BibTeX file."""
    file_path = arguments.get("file_path")
    content = arguments.get("content")

    if file_path and not content:
        entries = CitationService.parse_bib_file(file_path)
    elif content:
        entries = CitationService.parse_bibtex(content)
    else:
        raise ValidationError("file_path", "Either file_path or content is required")

    return _to_response({
        "total_entries": len(entries),
        "entries": [
            {
                "key": e.key,
                "type": e.type,
                "fields": e.fields,
            }
            for e in entries
        ],
    })


def _link_bib_to_database(arguments: dict[str, Any]) -> list[TextContent]:
    """Match BibTeX entries to papers in database."""
    result = CitationService.link_bib_to_database(
        bib_path=arguments.get("file_path"),
        content=arguments.get("content"),
        min_similarity=arguments.get("min_similarity", 0.8),
    )

    return _to_response({
        "summary": {
            "total": result.total,
            "matched": len(result.matched),
            "unmatched": len(result.unmatched),
        },
        "matched": result.matched,
        "unmatched": result.unmatched,
    })


def _scan_tex_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Scan TeX files for citations."""
    result = CitationService.scan_tex_citations(
        path=arguments["file_path"],
        recursive=arguments.get("recursive", True),
    )

    return _to_response({
        "files_scanned": result.files_scanned,
        "total_citations": result.total_citations,
        "unique_keys": result.unique_keys,
        "citations_by_key": result.citations_by_key,
    })


def _get_citation_locations(arguments: dict[str, Any]) -> list[TextContent]:
    """Get locations of a specific citation key."""
    locations = CitationService.get_citation_locations(
        path=arguments["file_path"],
        citation_key=arguments["citation_key"],
    )

    return _to_response({
        "citation_key": arguments["citation_key"],
        "total_occurrences": len(locations),
        "locations": locations,
    })


def _citation_health_check(arguments: dict[str, Any]) -> list[TextContent]:
    """Comprehensive citation health check."""
    result = CitationService.check_health(
        bib_path=arguments["bib_path"],
        tex_path=arguments["tex_path"],
    )

    return _to_response({
        "summary": {
            "bib_entries": result.bib_entries,
            "unique_citations": result.unique_citations,
            "orphan_entries": len(result.orphan_entries),
            "missing_citations": len(result.missing_citations),
            "incomplete_entries": len(result.incomplete_entries),
            "duplicate_entries": len(result.duplicate_entries),
        },
        "issues": {
            "orphans": result.orphan_entries,
            "missing": result.missing_citations,
            "incomplete": result.incomplete_entries,
            "duplicates": result.duplicate_entries,
        },
        "status": result.status,
    })


def _find_orphan_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Find bib entries never cited."""
    orphans = CitationService.find_orphan_entries(
        bib_path=arguments["bib_path"],
        tex_path=arguments["tex_path"],
    )

    return _to_response({
        "total_orphans": len(orphans),
        "orphans": orphans,
    })


def _find_missing_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Find citation keys used but not in bib."""
    missing = CitationService.find_missing_citations(
        bib_path=arguments["bib_path"],
        tex_path=arguments["tex_path"],
    )

    return _to_response({
        "total_missing": len(missing),
        "missing_citations": missing,
    })


def _find_incomplete_bib_entries(arguments: dict[str, Any]) -> list[TextContent]:
    """Find bib entries missing required fields."""
    entries = CitationService.parse_bib_file(arguments["bib_path"])
    incomplete = CitationService.find_incomplete_entries(arguments["bib_path"])

    return _to_response({
        "total_entries": len(entries),
        "incomplete_count": len(incomplete),
        "incomplete_entries": incomplete,
    })


def _find_duplicate_bib_entries(arguments: dict[str, Any]) -> list[TextContent]:
    """Find duplicate bib entries."""
    entries = CitationService.parse_bib_file(arguments["bib_path"])
    duplicates = CitationService.find_duplicate_entries(
        bib_path=arguments["bib_path"],
        similarity_threshold=arguments.get("similarity_threshold", 0.9),
    )

    return _to_response({
        "total_entries": len(entries),
        "duplicates_found": len(duplicates),
        "duplicates": duplicates,
    })


def _sync_bib_from_database(arguments: dict[str, Any]) -> list[TextContent]:
    """Sync bib entries with database metadata."""
    entries = CitationService.parse_bib_file(arguments["bib_path"])
    dry_run = arguments.get("dry_run", True)

    updates = CitationService.sync_from_database(
        bib_path=arguments["bib_path"],
        dry_run=dry_run,
    )

    result = {
        "dry_run": dry_run,
        "entries_checked": len(entries),
        "updates_available": len(updates),
        "updates": updates,
    }

    if not dry_run and updates:
        result["note"] = "Writing updates not yet implemented - use dry_run=true"

    return _to_response(result)


def _import_bib_to_database(arguments: dict[str, Any]) -> list[TextContent]:
    """Import papers from bib file to database."""
    path = Path(arguments["bib_path"]).expanduser()
    content = path.read_text()

    result = ImportExportService.import_bibtex(
        bibtex_content=content,
        tags=arguments.get("tags"),
    )

    return _to_response({
        "summary": {
            "total": result.total_entries,
            "imported": len(result.imported),
            "skipped": len(result.skipped),
            "failed": len(result.failed),
        },
        "imported": [asdict(p) for p in result.imported],
        "skipped": [asdict(p) for p in result.skipped],
        "failed": [asdict(p) for p in result.failed],
    })


def _export_database_to_bib(arguments: dict[str, Any]) -> list[TextContent]:
    """Export papers from database to BibTeX."""
    output_path = arguments.get("output_path")

    bibtex_content = CitationService.export_to_bib(
        paper_ids=arguments.get("paper_ids"),
        tag=arguments.get("tag"),
        output_path=output_path,
    )

    if output_path:
        return _to_response({
            "status": "written",
            "output_path": output_path,
            "entries_exported": bibtex_content.count("@article{"),
        })
    else:
        return [TextContent(type="text", text=bibtex_content)]


def _get_project_config(arguments: dict[str, Any]) -> list[TextContent]:
    """Get project citation configuration."""
    config = CitationService.get_project_config(arguments["project_path"])

    result: dict[str, Any] = {"configured": config.configured}
    if config.configured:
        result["bib_files"] = config.bib_files
        result["tex_paths"] = config.tex_paths
    if config.detected:
        result["detected"] = config.detected

    return _to_response(result)


def _set_project_config(arguments: dict[str, Any]) -> list[TextContent]:
    """Set project citation configuration."""
    config = CitationService.set_project_config(
        project_path=arguments["project_path"],
        bib_files=arguments.get("bib_files"),
        tex_paths=arguments.get("tex_paths"),
    )

    return _to_response({
        "status": "saved",
        "config": {
            "configured": config.configured,
            "bib_files": config.bib_files,
            "tex_paths": config.tex_paths,
        },
    })


# ============================================================================
# Main entry point
# ============================================================================


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a project management tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "parse_bib_file": _parse_bib_file,
        "link_bib_to_database": _link_bib_to_database,
        "scan_tex_citations": _scan_tex_citations,
        "get_citation_locations": _get_citation_locations,
        "citation_health_check": _citation_health_check,
        "find_orphan_citations": _find_orphan_citations,
        "find_missing_citations": _find_missing_citations,
        "find_incomplete_bib_entries": _find_incomplete_bib_entries,
        "find_duplicate_bib_entries": _find_duplicate_bib_entries,
        "sync_bib_from_database": _sync_bib_from_database,
        "import_bib_to_database": _import_bib_to_database,
        "export_database_to_bib": _export_database_to_bib,
        "get_project_config": _get_project_config,
        "set_project_config": _set_project_config,
    }

    if name not in tool_map:
        return _to_response(error(f"Unknown project tool: {name}", code="UNKNOWN_TOOL"))

    try:
        return tool_map[name](arguments)

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
