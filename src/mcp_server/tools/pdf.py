"""PDF Management Tools for MCP Server.

These tools provide PDF acquisition, status tracking, and duplicate detection.
This module is a thin wrapper over PDFService.

Architecture:
    MCP Tool (this file) -> PDFService -> SQLAlchemy -> Database
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
# pdf.py is at src/mcp_server/tools/pdf.py, so parent.parent.parent = src/
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

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List PDF management tools."""
    return [
        Tool(
            name="acquire_paper_pdf",
            description="Download PDF via open access, VPN, OpenURL, or EZProxy",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to acquire PDF for",
                    },
                    "use_vpn": {
                        "type": "boolean",
                        "description": "Try direct publisher URLs (use when connected to UW VPN)",
                        "default": False,
                    },
                    "use_openurl": {
                        "type": "boolean",
                        "description": "Use UW Primo OpenURL resolver to find full-text links",
                        "default": False,
                    },
                    "use_proxy": {
                        "type": "boolean",
                        "description": "Use UW EZProxy URLs (requires browser cookies)",
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_pdf_status",
            description="Get PDF status for papers - which have PDFs downloaded, which need PDFs",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "has_pdf", "needs_pdf"],
                        "description": "Filter papers by PDF status",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 50,
                    },
                },
            },
        ),
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
# Tool Implementations - Thin wrappers over PDFService
# ============================================================================


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


async def _acquire_paper_pdf(arguments: dict[str, Any]) -> list[TextContent]:
    """Acquire PDF for a paper."""
    result = await PDFService.acquire(
        paper_id=arguments["paper_id"],
        use_vpn=arguments.get("use_vpn", False),
        use_openurl=arguments.get("use_openurl", False),
        use_proxy=arguments.get("use_proxy", False),
    )

    # Convert dataclass to dict for JSON serialization
    result_dict = asdict(result)
    # Remove None values for cleaner output
    result_dict = {k: v for k, v in result_dict.items() if v is not None}

    return _to_response(result_dict)


def _get_pdf_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get PDF status for papers."""
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
    """Execute a PDF tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    tool_map = {
        "get_pdf_status": _get_pdf_status,
        "find_duplicates": _find_duplicates,
    }

    if name not in tool_map and name != "acquire_paper_pdf":
        return _to_response(error(f"Unknown PDF tool: {name}", code="UNKNOWN_TOOL"))

    try:
        if name == "acquire_paper_pdf":
            return await _acquire_paper_pdf(arguments)
        return tool_map[name](arguments)

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
