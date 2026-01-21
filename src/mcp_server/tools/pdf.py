"""PDF Management Tools for MCP Server.

Consolidated tools:
    - acquire_pdf: Download via open access OR queue for browser download
    - manage_pdf: PDF status checking AND browser queue management
    - find_duplicates: Find duplicate papers by hash or title

Architecture:
    MCP Tool (this file) -> PDFService -> Database
                        -> browser_pdf helpers -> Windows queue files
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
    PaperNotFoundError,
    PDFError,
    LiteratureError,
)
from services import PDFService

# Import browser PDF helper functions
from mcp_server.tools import browser_pdf as _browser

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List PDF management tools (consolidated from 5 to 3)."""
    return [
        # Consolidated: acquire_paper_pdf + queue_pdf_download
        Tool(
            name="acquire_pdf",
            description="Get PDF. method: open_access (try download), browser_queue (queue for Windows)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to acquire PDF for",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "For browser_queue: batch paper IDs",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["open_access", "browser_queue"],
                        "description": "Method: open_access (try download now) or browser_queue (queue for Windows browser)",
                        "default": "open_access",
                    },
                    # open_access options
                    "use_vpn": {
                        "type": "boolean",
                        "description": "For open_access: try direct publisher URLs (UW VPN)",
                        "default": False,
                    },
                    "use_openurl": {
                        "type": "boolean",
                        "description": "For open_access: use UW Primo OpenURL resolver",
                        "default": False,
                    },
                    "use_proxy": {
                        "type": "boolean",
                        "description": "For open_access: use UW EZProxy URLs",
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        # Consolidated: get_pdf_status + manage_pdf_queue
        Tool(
            name="manage_pdf",
            description="PDF management. action: status (papers with/without PDFs), queue_status, process, clear",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "queue_status", "process", "clear"],
                        "description": "Action: status (PDF coverage), queue_status (browser queue), process (import downloaded), clear (clear queue)",
                        "default": "status",
                    },
                    # For status action
                    "filter": {
                        "type": "string",
                        "enum": ["all", "has_pdf", "needs_pdf"],
                        "description": "For status: filter papers by PDF availability",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 50,
                    },
                    # For queue_status action
                    "paper_id": {
                        "type": "integer",
                        "description": "For queue_status: check specific paper",
                    },
                    # For process action
                    "auto_match": {
                        "type": "boolean",
                        "description": "For process: match PDFs by DOI in filename",
                        "default": True,
                    },
                    # For clear action
                    "clear_all": {
                        "type": "boolean",
                        "description": "For clear: remove all including pending",
                        "default": False,
                    },
                },
            },
        ),
        # Keep as-is
        Tool(
            name="find_duplicates",
            description="Find duplicate papers by file hash or title similarity",
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["hash", "title"],
                        "description": "Method: 'hash' (exact file match) or 'title' (similar)",
                        "default": "title",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Similarity threshold for title matching (0.0-1.0)",
                        "default": 0.85,
                        "minimum": 0.0,
                        "maximum": 1.0,
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


async def _acquire_pdf(arguments: dict[str, Any]) -> list[TextContent]:
    """Acquire PDF via open access or queue for browser download."""
    method = arguments.get("method", "open_access")

    if method == "browser_queue":
        # Use browser queue (batch supported)
        return _browser._queue_pdf_download(arguments)
    else:
        # Use open access download
        result = await PDFService.acquire(
            paper_id=arguments["paper_id"],
            use_vpn=arguments.get("use_vpn", False),
            use_openurl=arguments.get("use_openurl", False),
            use_proxy=arguments.get("use_proxy", False),
        )
        result_dict = asdict(result)
        result_dict = {k: v for k, v in result_dict.items() if v is not None}
        return _to_response(result_dict)


def _manage_pdf(arguments: dict[str, Any]) -> list[TextContent]:
    """Manage PDFs - status checking and queue management."""
    action = arguments.get("action", "status")

    if action == "status":
        # PDF status for papers in database
        result = PDFService.get_status(
            filter_type=arguments.get("filter", "all"),
            limit=arguments.get("limit", 50),
        )
        return _to_response({
            "summary": {
                "total_papers": result.total_papers,
                "has_pdf": result.has_pdf,
                "needs_pdf": result.needs_pdf,
                "no_identifier": result.no_identifier,
            },
            "filter": result.filter_type,
            "papers": result.papers,
        })

    elif action == "queue_status":
        # Browser download queue status
        return _browser._get_download_queue_status(arguments)

    elif action == "process":
        # Process downloaded PDFs
        return _browser._process_downloaded_pdfs(arguments)

    elif action == "clear":
        # Clear download queue
        return _browser._clear_download_queue(arguments)

    else:
        return _to_response(error(f"Unknown action: {action}", code="UNKNOWN_ACTION"))


def _find_duplicates(arguments: dict[str, Any]) -> list[TextContent]:
    """Find duplicate papers."""
    result = PDFService.find_duplicates(
        method=arguments.get("method", "title"),
        threshold=arguments.get("threshold", 0.85),
    )

    return _to_response({
        "method": result.method,
        "threshold": result.threshold,
        "total_papers": result.total_papers,
        "duplicate_groups": len(result.duplicate_groups),
        "duplicates": [
            {
                "type": dup.type,
                "file_hash": dup.file_hash,
                "similarity": dup.similarity,
                "papers": dup.papers,
            }
            for dup in result.duplicate_groups
        ],
    })


# ============================================================================
# Main entry point
# ============================================================================


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a PDF tool."""
    try:
        if name == "acquire_pdf":
            return await _acquire_pdf(arguments)

        if name == "manage_pdf":
            return _manage_pdf(arguments)

        if name == "find_duplicates":
            return _find_duplicates(arguments)

        return _to_response(error(f"Unknown PDF tool: {name}", code="UNKNOWN_TOOL"))

    except PaperNotFoundError as e:
        logger.warning(f"Paper not found: {e.paper_id}")
        return _to_response(
            error(str(e), code=e.code, details={"paper_id": e.paper_id})
        )

    except PDFError as e:
        logger.warning(f"PDF error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except LiteratureError as e:
        logger.error(f"Literature error: {e.message}")
        return _to_response(error(str(e), code=e.code))

    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}")
        return _to_response(error(f"Internal error: {str(e)}", code="INTERNAL_ERROR"))
