"""Import/Export Tools for MCP Server.

Consolidated tools:
    - import_paper: Import via wizard (default), bibtex, or external lookup
    - export: Export papers by IDs or collection
    - get_enrichment_queue: Papers needing enrichment

Architecture:
    MCP Tool (this file) -> ImportExportService/PaperImportService -> Database
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
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
    """Return consolidated import/export tools (6 → 3)."""
    return [
        # =================================================================
        # CONSOLIDATED: import_bibtex + import_from_external + import_paper_wizard
        # =================================================================
        Tool(
            name="import_paper",
            description="Import papers. source: wizard (smart, default), bibtex, external",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["wizard", "bibtex", "external"],
                        "description": "wizard=smart import with duplicate check, bibtex=from BibTeX, external=DOI/arXiv lookup",
                        "default": "wizard",
                    },
                    # Identifier params (wizard/external)
                    "doi": {
                        "type": "string",
                        "description": "DOI to import (most reliable)",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID (e.g., '2301.12345')",
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title for lookup",
                    },
                    "authors": {
                        "type": "string",
                        "description": "Authors for disambiguation (wizard)",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Year for disambiguation (wizard)",
                    },
                    # BibTeX params
                    "bibtex_content": {
                        "type": "string",
                        "description": "Raw BibTeX content (source=bibtex)",
                    },
                    # Common params
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Add to collection",
                    },
                    # Wizard-specific
                    "pdf_path": {
                        "type": "string",
                        "description": "Local PDF path (wizard)",
                    },
                    "skip_duplicate_check": {
                        "type": "boolean",
                        "default": False,
                        "description": "Skip duplicate detection (wizard)",
                    },
                    "auto_chunk_pdf": {
                        "type": "boolean",
                        "default": True,
                        "description": "Auto-chunk PDF text (wizard)",
                    },
                },
            },
        ),
        # =================================================================
        # CONSOLIDATED: export_papers + export_collection
        # =================================================================
        Tool(
            name="export",
            description="Export papers. source: papers (by IDs, default), collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["papers", "collection"],
                        "description": "papers=by paper_ids, collection=by collection_id",
                        "default": "papers",
                    },
                    # Papers source params
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paper IDs to export (source=papers, omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max papers (source=papers, max 500)",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Skip N papers for pagination",
                    },
                    # Collection source params
                    "collection_id": {
                        "type": "integer",
                        "description": "Collection ID (source=collection)",
                    },
                    "include_subcollections": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include child collections",
                    },
                    # Common params
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "json", "csv"],
                        "default": "bibtex",
                        "description": "Export format",
                    },
                    "include_abstract": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include abstracts",
                    },
                    "include_notes": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include notes (JSON only)",
                    },
                },
            },
        ),
        # =================================================================
        # KEPT AS-IS
        # =================================================================
        Tool(
            name="get_enrichment_queue",
            description="Papers needing enrichment (missing abstract, PDF, or chunks)",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["needs_abstract", "needs_pdf", "needs_chunks", "pending", "failed"],
                        "description": "Filter by enrichment status",
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
# Tool Implementations
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


async def _import_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated import tool."""
    source = arguments.get("source", "wizard")

    if source == "bibtex":
        # Import from BibTeX content
        bibtex_content = arguments.get("bibtex_content")
        if not bibtex_content:
            return _to_response(error("bibtex_content required for source=bibtex", code="MISSING_PARAM"))

        result = ImportExportService.import_bibtex(
            bibtex_content=bibtex_content,
            tags=arguments.get("tags"),
            collection_id=arguments.get("collection_id"),
        )

        return _to_response({
            "source": "bibtex",
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

    elif source == "external":
        # Simple external lookup (no duplicate check)
        result = await ImportExportService.import_from_external(
            doi=arguments.get("doi"),
            arxiv_id=arguments.get("arxiv_id"),
            title=arguments.get("title"),
            tags=arguments.get("tags"),
            collection_id=arguments.get("collection_id"),
        )

        result_dict = {
            "source": "external",
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

    else:
        # wizard (default) - smart import with duplicate detection
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
            "source": "wizard",
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


def _export(arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated export tool."""
    source = arguments.get("source", "papers")

    if source == "collection":
        # Export collection
        collection_id = arguments.get("collection_id")
        if not collection_id:
            return _to_response(error("collection_id required for source=collection", code="MISSING_PARAM"))

        output = ImportExportService.export_collection(
            collection_id=collection_id,
            format=arguments.get("format", "bibtex"),
            include_subcollections=arguments.get("include_subcollections", False),
        )

        return [TextContent(type="text", text=output)]

    else:
        # Export papers (default)
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

        return [TextContent(type="text", text=output)]


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
    """Execute an import/export tool."""
    try:
        if name == "import_paper":
            return await _import_paper(arguments)

        if name == "export":
            return _export(arguments)

        if name == "get_enrichment_queue":
            return _get_enrichment_queue(arguments)

        return _to_response(error(f"Unknown import/export tool: {name}", code="UNKNOWN_TOOL"))

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
