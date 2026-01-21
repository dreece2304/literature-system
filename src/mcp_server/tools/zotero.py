"""
Zotero Sync Tools for MCP Server.

These tools provide bidirectional synchronization between
the literature database and Zotero reference manager.
"""

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
    """List Zotero sync tools."""
    return [
        Tool(
            name="sync_from_zotero",
            description="Pull papers from Zotero into database (requires API key)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sync_to_zotero",
            description="Push enriched metadata to Zotero (non-destructive, fills empty fields)",
            inputSchema={
                "type": "object",
                "properties": {
                    "create_new_items": {
                        "type": "boolean",
                        "description": (
                            "If true, create new Zotero items for papers not in Zotero. "
                            "If false (default), only enrich existing Zotero items."
                        ),
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="push_paper_to_zotero",
            description="Push single paper to Zotero (creates or enriches)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID to push to Zotero",
                    },
                    "create_if_missing": {
                        "type": "boolean",
                        "description": "Create new Zotero item if paper doesn't exist there (default: true)",
                        "default": True,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="push_pdf_to_zotero",
            description="Upload PDF to Zotero (paper must exist in Zotero first)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Database paper ID whose PDF to upload",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_zotero_sync_status",
            description="Sync status (linked papers, database-only, API availability)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_zotero_connection",
            description="Check Zotero local/web API connectivity",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a Zotero sync tool."""
    try:
        zs = get_zotero_sync()

        if name == "sync_from_zotero":
            # Check if web API is configured (required for sync)
            api_info = zs.get_api_info()

            if not api_info.get('web_api'):
                return [TextContent(
                    type="text",
                    text=serialize({
                        "error": "Zotero web API not configured",
                        "details": "Web API is required for syncing items from Zotero.",
                        "help": "Configure API key in config/credentials.yml",
                        "zotero_running": api_info.get('local_api', False)
                    })
                )]

            # Perform sync via web API
            added, updated = zs.sync_from_api()

            return [TextContent(
                type="text",
                text=serialize({
                    "success": True,
                    "papers_added": added,
                    "papers_updated": updated,
                    "api_used": "web"
                })
            )]

        elif name == "sync_to_zotero":
            # Check web API first
            api_info = zs.get_api_info()

            if not api_info.get('web_api'):
                return [TextContent(
                    type="text",
                    text=serialize({
                        "error": "Web API required for sync to Zotero",
                        "details": "Push operations require the Zotero web API with write permissions.",
                        "help": "Configure API key in config/credentials.yml"
                    })
                )]

            create_new = arguments.get("create_new_items", False)
            result = zs.sync_to_zotero(enrich_only=not create_new)

            return [TextContent(
                type="text",
                text=serialize({
                    "success": True,
                    "created": result.get('created', 0),
                    "updated": result.get('updated', 0),
                    "skipped": result.get('skipped', 0),
                    "errors": result.get('errors', 0),
                    "mode": "full_sync" if create_new else "enrich_only"
                })
            )]

        elif name == "push_paper_to_zotero":
            # Check web API first
            api_info = zs.get_api_info()

            if not api_info.get('web_api'):
                return [TextContent(
                    type="text",
                    text=serialize({
                        "error": "Web API required",
                        "help": "Configure API key in config/credentials.yml"
                    })
                )]

            paper_id = arguments["paper_id"]
            create_if_missing = arguments.get("create_if_missing", True)

            result = zs.push_paper_to_zotero(paper_id, create_if_missing=create_if_missing)

            return [TextContent(
                type="text",
                text=serialize(result)
            )]

        elif name == "push_pdf_to_zotero":
            # Check web API first
            api_info = zs.get_api_info()

            if not api_info.get('web_api'):
                return [TextContent(
                    type="text",
                    text=serialize({
                        "error": "Web API required",
                        "help": "Configure API key in config/credentials.yml"
                    })
                )]

            paper_id = arguments["paper_id"]
            result = zs.push_pdf_to_zotero(paper_id)

            return [TextContent(
                type="text",
                text=serialize(result)
            )]

        elif name == "get_zotero_sync_status":
            result = zs.get_sync_status()
            return [TextContent(
                type="text",
                text=serialize(result)
            )]

        elif name == "check_zotero_connection":
            api_info = zs.get_api_info()

            # Build details response
            local_available = api_info.get('local_api', False)
            web_available = api_info.get('web_api', False)

            details = {
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

            return [TextContent(
                type="text",
                text=serialize(details)
            )]

        else:
            return [TextContent(
                type="text",
                text=f"Unknown Zotero tool: {name}"
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
