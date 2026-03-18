"""Project Citation Tools for MCP Server.

These tools provide BibTeX parsing, TeX citation scanning, health checks,
and database synchronization for managing citations in research projects.
This module is a thin wrapper over CitationService.

Architecture:
    MCP Tool (this file) -> CitationService -> SQLAlchemy -> Database
"""
from __future__ import annotations

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
        # Consolidated BibTeX management tool
        Tool(
            name="manage_bibtex",
            description="BibTeX operations. Actions: parse, link, import, export, sync",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["parse", "link", "import", "export", "sync"],
                        "description": "Action: parse (parse .bib), link (match to DB), import (add to DB), export (from DB), sync (update .bib from DB)",
                        "default": "parse",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to .bib file (for parse/link/import/sync)",
                    },
                    "content": {
                        "type": "string",
                        "description": "BibTeX content (alternative to file_path)",
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.8,
                        "description": "For link: minimum title similarity (0-1)",
                    },
                    "skip_existing": {
                        "type": "boolean",
                        "default": True,
                        "description": "For import: skip entries already in DB",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For import: tags to apply",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "For export: paper IDs (omit for all)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "For export: output .bib path",
                    },
                    "tag": {
                        "type": "string",
                        "description": "For export: filter by tag",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": "For sync: preview changes without writing",
                    },
                },
            },
        ),
        # Consolidated citation health check tool
        Tool(
            name="citation_health_check",
            description="Check citation health. Checks: all (default), orphans, missing, incomplete, duplicates",
            inputSchema={
                "type": "object",
                "properties": {
                    "check": {
                        "type": "string",
                        "enum": ["all", "orphans", "missing", "incomplete", "duplicates"],
                        "description": "Check type: all (comprehensive), orphans (uncited bib), missing (cited but not in bib), incomplete (missing fields), duplicates",
                        "default": "all",
                    },
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory (for all/orphans/missing)",
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "default": 0.9,
                        "description": "For duplicates: title similarity threshold",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        # Consolidated citation scanning tool
        Tool(
            name="scan_citations",
            description="Scan TeX files for citations. Mode: scan (all keys), locate (specific key)",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["scan", "locate"],
                        "description": "Mode: scan (find all \\cite{}), locate (find specific key)",
                        "default": "scan",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                    "citation_key": {
                        "type": "string",
                        "description": "For locate: the citation key to find",
                    },
                    "recursive": {
                        "type": "boolean",
                        "default": True,
                        "description": "For scan: recursively scan directories",
                    },
                },
                "required": ["file_path"],
            },
        ),
        # Consolidated project config tool
        Tool(
            name="manage_project",
            description="Project citation config. Actions: get, set",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set"],
                        "description": "Action: get (read config), set (update config)",
                        "default": "get",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root",
                    },
                    "bib_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For set: .bib file paths",
                    },
                    "tex_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For set: .tex paths",
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
    try:
        # Consolidated manage_bibtex tool
        if name == "manage_bibtex":
            action = arguments.get("action", "parse")
            if action == "parse":
                return _parse_bib_file(arguments)
            elif action == "link":
                return _link_bib_to_database(arguments)
            elif action == "import":
                return _import_bib_to_database(arguments)
            elif action == "export":
                return _export_database_to_bib(arguments)
            elif action == "sync":
                return _sync_bib_from_database(arguments)
            else:
                return _to_response(error(f"Unknown action: {action}", code="UNKNOWN_ACTION"))

        # Consolidated citation_health_check tool
        if name == "citation_health_check":
            check = arguments.get("check", "all")
            if check == "all":
                return _citation_health_check(arguments)
            elif check == "orphans":
                return _find_orphan_citations(arguments)
            elif check == "missing":
                return _find_missing_citations(arguments)
            elif check == "incomplete":
                return _find_incomplete_bib_entries(arguments)
            elif check == "duplicates":
                return _find_duplicate_bib_entries(arguments)
            else:
                return _to_response(error(f"Unknown check: {check}", code="UNKNOWN_CHECK"))

        # Consolidated scan_citations tool
        if name == "scan_citations":
            mode = arguments.get("mode", "scan")
            if mode == "scan":
                return _scan_tex_citations(arguments)
            elif mode == "locate":
                return _get_citation_locations(arguments)
            else:
                return _to_response(error(f"Unknown mode: {mode}", code="UNKNOWN_MODE"))

        # Consolidated manage_project tool
        if name == "manage_project":
            action = arguments.get("action", "get")
            if action == "get":
                return _get_project_config(arguments)
            elif action == "set":
                return _set_project_config(arguments)
            else:
                return _to_response(error(f"Unknown action: {action}", code="UNKNOWN_ACTION"))

        return _to_response(error(f"Unknown project tool: {name}", code="UNKNOWN_TOOL"))

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
