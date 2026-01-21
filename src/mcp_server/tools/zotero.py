"""Zotero Sync Tools for MCP Server.

Consolidated tools (6 → 2):
    - zotero_sync: Sync operations (pull, push, push_paper, push_pdf)
    - zotero_status: Status and connection check

Architecture:
    MCP Tool (this file) -> ZoteroSync -> Zotero API
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent
from loguru import logger

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import serialize
from extractors.zotero_sync import ZoteroSync


# Lazy-initialized ZoteroSync instance
_zotero_sync: ZoteroSync | None = None


def get_zotero_sync() -> ZoteroSync:
    """Get or create ZoteroSync instance."""
    global _zotero_sync
    if _zotero_sync is None:
        _zotero_sync = ZoteroSync()
    return _zotero_sync


async def list_tools() -> list[Tool]:
    """List consolidated Zotero tools (6 → 2)."""
    return [
        # =================================================================
        # CONSOLIDATED: sync_from/to_zotero + push_paper/pdf_to_zotero
        # =================================================================
        Tool(
            name="zotero_sync",
            description="Zotero sync. direction: pull, push, push_paper, push_pdf",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["pull", "push", "push_paper", "push_pdf"],
                        "description": (
                            "pull=from Zotero to DB, push=DB to Zotero, "
                            "push_paper=single paper, push_pdf=upload PDF"
                        ),
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID (for push_paper/push_pdf)",
                    },
                    "create_new_items": {
                        "type": "boolean",
                        "description": "Create new Zotero items for papers not in Zotero (for push)",
                        "default": False,
                    },
                    "create_if_missing": {
                        "type": "boolean",
                        "description": "Create new Zotero item if missing (for push_paper)",
                        "default": True,
                    },
                },
                "required": ["direction"],
            },
        ),
        # =================================================================
        # CONSOLIDATED: get_zotero_sync_status + check_zotero_connection
        # =================================================================
        Tool(
            name="zotero_status",
            description="Zotero status and connection check",
            inputSchema={
                "type": "object",
                "properties": {
                    "check_connection": {
                        "type": "boolean",
                        "description": "Include detailed connection diagnostics",
                        "default": False,
                    },
                },
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a Zotero tool."""
    try:
        zs = get_zotero_sync()

        if name == "zotero_sync":
            return await _zotero_sync_handler(zs, arguments)

        if name == "zotero_status":
            return _zotero_status_handler(zs, arguments)

        return [TextContent(
            type="text",
            text=serialize({"error": f"Unknown Zotero tool: {name}"})
        )]

    except Exception as e:
        logger.error(f"Zotero tool error: {e}")
        import traceback
        return [TextContent(
            type="text",
            text=serialize({
                "error": str(e),
                "traceback": traceback.format_exc()
            })
        )]


async def _zotero_sync_handler(zs: ZoteroSync, arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated sync handler."""
    direction = arguments.get("direction")
    if not direction:
        return [TextContent(
            type="text",
            text=serialize({"error": "direction is required"})
        )]

    # Check web API availability (required for all sync operations)
    api_info = zs.get_api_info()
    if not api_info.get('web_api'):
        return [TextContent(
            type="text",
            text=serialize({
                "error": "Zotero web API not configured",
                "details": "Web API is required for sync operations.",
                "help": "Configure API key in config/credentials.yml",
                "zotero_running": api_info.get('local_api', False)
            })
        )]

    if direction == "pull":
        # Pull from Zotero to database
        added, updated = zs.sync_from_api()
        return [TextContent(
            type="text",
            text=serialize({
                "success": True,
                "direction": "pull",
                "papers_added": added,
                "papers_updated": updated,
                "api_used": "web"
            })
        )]

    elif direction == "push":
        # Push from database to Zotero
        create_new = arguments.get("create_new_items", False)
        result = zs.sync_to_zotero(enrich_only=not create_new)
        return [TextContent(
            type="text",
            text=serialize({
                "success": True,
                "direction": "push",
                "created": result.get('created', 0),
                "updated": result.get('updated', 0),
                "skipped": result.get('skipped', 0),
                "errors": result.get('errors', 0),
                "mode": "full_sync" if create_new else "enrich_only"
            })
        )]

    elif direction == "push_paper":
        # Push single paper to Zotero
        paper_id = arguments.get("paper_id")
        if not paper_id:
            return [TextContent(
                type="text",
                text=serialize({"error": "paper_id required for push_paper"})
            )]

        create_if_missing = arguments.get("create_if_missing", True)
        result = zs.push_paper_to_zotero(paper_id, create_if_missing=create_if_missing)
        result["direction"] = "push_paper"
        return [TextContent(
            type="text",
            text=serialize(result)
        )]

    elif direction == "push_pdf":
        # Push PDF to Zotero
        paper_id = arguments.get("paper_id")
        if not paper_id:
            return [TextContent(
                type="text",
                text=serialize({"error": "paper_id required for push_pdf"})
            )]

        result = zs.push_pdf_to_zotero(paper_id)
        result["direction"] = "push_pdf"
        return [TextContent(
            type="text",
            text=serialize(result)
        )]

    else:
        return [TextContent(
            type="text",
            text=serialize({"error": f"Unknown direction: {direction}"})
        )]


def _zotero_status_handler(zs: ZoteroSync, arguments: dict[str, Any]) -> list[TextContent]:
    """Consolidated status handler."""
    check_connection = arguments.get("check_connection", False)

    if check_connection:
        # Detailed connection check
        api_info = zs.get_api_info()
        local_available = api_info.get('local_api', False)
        web_available = api_info.get('web_api', False)

        result = {
            "zotero_app": {
                "running": local_available,
                "note": api_info.get('local_api_note', 'Unknown'),
            },
            "web_api": {
                "configured": web_available,
                "note": "Required for sync operations",
            },
            "can_sync": web_available,
            "can_push": web_available,
            "help": None if web_available else "Configure API key in config/credentials.yml"
        }
    else:
        # Basic sync status
        result = zs.get_sync_status()

    return [TextContent(
        type="text",
        text=serialize(result)
    )]
