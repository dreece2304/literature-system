"""
Main MCP Server for Literature Management.

This server exposes tools to Claude Code for managing a literature database,
searching papers, and interacting with external academic APIs.

ARCHITECTURE: MCP Server → Service Layer → SQLAlchemy → SQLite
No HTTP API layer required - direct database access via services.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    Prompt,
    PromptArgument,
    PromptMessage,
    GetPromptResult,
)
from mcp.server.stdio import stdio_server
from loguru import logger

# Add src directory to path for service imports
# Now that everything is consolidated in src/, we just need the parent of mcp_server/
_src_path = Path(__file__).parent.parent  # src/
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import setup_logging, settings as core_settings  # noqa: E402

# Import tool implementations
from .tools.papers import (  # noqa: E402
    list_tools as list_paper_tools,
    call_tool as call_paper_tool,
)
from .tools.search import (  # noqa: E402
    list_tools as list_search_tools,
    call_tool as call_search_tool,
)
from .tools.external import (  # noqa: E402
    list_tools as list_external_tools,
    call_tool as call_external_tool,
)
from .tools.citations import (  # noqa: E402
    list_tools as list_citation_tools,
    call_tool as call_citation_tool,
)
from .tools.pdf import (  # noqa: E402
    list_tools as list_pdf_tools,
    call_tool as call_pdf_tool,
)
from .tools.collections import (  # noqa: E402
    list_tools as list_collection_tools,
    call_tool as call_collection_tool,
)
from .tools.notes import (  # noqa: E402
    list_tools as list_note_tools,
    call_tool as call_note_tool,
)
from .tools.import_export import (  # noqa: E402
    list_tools as list_import_export_tools,
    call_tool as call_import_export_tool,
)
from .tools.project import (  # noqa: E402
    list_tools as list_project_tools,
    call_tool as call_project_tool,
)
from .tools.zotero import (  # noqa: E402
    list_tools as list_zotero_tools,
    call_tool as call_zotero_tool,
)
from .tools.browser_pdf import (  # noqa: E402
    list_tools as list_browser_pdf_tools,
    call_tool as call_browser_pdf_tool,
)
from .tools.discovery import (  # noqa: E402
    list_tools as list_discovery_tools,
    call_tool as call_discovery_tool,
)
from .resources.handlers import (  # noqa: E402
    list_resources,
    read_resource,
)

# Initialize the MCP Server
server = Server("literature")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available tools."""
    tools = []
    tools.extend(await list_paper_tools())
    tools.extend(await list_search_tools())
    tools.extend(await list_external_tools())
    tools.extend(await list_citation_tools())
    tools.extend(await list_pdf_tools())
    tools.extend(await list_collection_tools())
    tools.extend(await list_note_tools())
    tools.extend(await list_import_export_tools())
    tools.extend(await list_project_tools())
    tools.extend(await list_zotero_tools())
    tools.extend(await list_browser_pdf_tools())
    tools.extend(await list_discovery_tools())
    return tools


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to appropriate handlers."""
    # Paper tools
    if name.startswith("paper_") or name.startswith("batch_") or name in [
        "search_papers", "get_paper", "add_paper", "update_paper", "list_papers",
        "get_paper_content", "store_extraction", "get_extraction_queue",
        "batch_update_papers", "batch_delete_papers"
    ]:
        return await call_paper_tool(name, arguments)

    # External API tools (check BEFORE search tools since search_external_papers starts with "search_")
    if name.startswith("external_") or name in [
        "lookup_paper_metadata", "find_open_access_pdf", "enrich_paper",
        "search_external_papers", "get_citation_count"
    ]:
        return await call_external_tool(name, arguments)

    # Search tools
    if name.startswith("search_") or name in [
        "semantic_search", "keyword_search", "search_by_author", "search_by_tag"
    ]:
        return await call_search_tool(name, arguments)

    # Citation tools
    if name.startswith("citation_") or name in [
        "scan_manuscript", "check_citations", "suggest_citation_key",
        "generate_bibtex", "format_bibliography", "validate_citations"
    ]:
        return await call_citation_tool(name, arguments)

    # PDF tools
    if name.startswith("pdf_") or name in [
        "acquire_paper_pdf", "get_pdf_status", "find_duplicates"
    ]:
        return await call_pdf_tool(name, arguments)

    # Collection tools
    if name.startswith("collection_") or name in [
        "list_collections", "get_collection", "create_collection",
        "update_collection", "delete_collection", "add_papers_to_collection",
        "remove_papers_from_collection", "get_collection_children"
    ]:
        return await call_collection_tool(name, arguments)

    # Note tools
    if name.startswith("note_") or name in [
        "list_notes", "get_note", "create_note", "update_note", "delete_note",
        "get_paper_notes", "delete_paper_notes"
    ]:
        return await call_note_tool(name, arguments)

    # Import/Export tools
    if name.startswith("import_") or name.startswith("export_") or name in [
        "import_bibtex", "export_papers", "import_from_external", "export_collection"
    ]:
        return await call_import_export_tool(name, arguments)

    # Project management tools
    if name in [
        "parse_bib_file", "link_bib_to_database",
        "scan_tex_citations", "get_citation_locations",
        "citation_health_check", "find_orphan_citations", "find_missing_citations",
        "find_incomplete_bib_entries", "find_duplicate_bib_entries",
        "sync_bib_from_database", "import_bib_to_database", "export_database_to_bib",
        "get_project_config", "set_project_config"
    ]:
        return await call_project_tool(name, arguments)

    # Zotero sync tools
    if name.startswith("zotero_") or name in [
        "sync_from_zotero", "sync_to_zotero", "push_paper_to_zotero",
        "push_pdf_to_zotero", "get_zotero_sync_status", "check_zotero_connection"
    ]:
        return await call_zotero_tool(name, arguments)

    # Browser-based PDF acquisition tools
    if name.startswith("queue_") or name in [
        "queue_pdf_download", "queue_batch_pdf_download",
        "get_download_queue_status", "process_downloaded_pdfs",
        "clear_download_queue"
    ]:
        return await call_browser_pdf_tool(name, arguments)

    # Discovery tools (similar papers, citation suggestions, reading queue)
    if name in [
        "find_similar_papers", "find_papers_like_text", "suggest_citations_for_text",
        "get_reading_queue", "suggest_paper_tags"
    ]:
        return await call_discovery_tool(name, arguments)

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available resources for @ mentions."""
    return await list_resources()


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read resource content."""
    return await read_resource(uri)


@server.list_prompts()
async def handle_list_prompts() -> list[Prompt]:
    """List available prompts for slash commands."""
    return [
        Prompt(
            name="summarize_paper",
            description="Summarize a research paper comprehensively",
            arguments=[
                PromptArgument(
                    name="paper_id",
                    description="ID of the paper to summarize",
                    required=True,
                )
            ],
        ),
        Prompt(
            name="analyze_paper",
            description="Analyze a paper's methodology, findings, and relevance",
            arguments=[
                PromptArgument(
                    name="paper_id",
                    description="ID of the paper to analyze",
                    required=True,
                ),
                PromptArgument(
                    name="focus",
                    description="Focus area: methodology, findings, limitations, or all",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="find_related",
            description="Find papers related to a given paper or topic",
            arguments=[
                PromptArgument(
                    name="query",
                    description="Paper ID or topic to find related papers for",
                    required=True,
                ),
                PromptArgument(
                    name="limit",
                    description="Maximum number of papers to return",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name="extraction_report",
            description="Get a report on papers needing AI extraction",
            arguments=[],
        ),
    ]


@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> GetPromptResult:
    """Get prompt content for slash commands."""
    args = arguments or {}

    if name == "summarize_paper":
        paper_id = args.get("paper_id", "")
        return GetPromptResult(
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please use the literature tools to:
1. Get the full content of paper {paper_id} using get_paper_content
2. Provide a comprehensive summary including:
   - Main research question/objective
   - Methodology used
   - Key findings (3-5 bullet points)
   - Conclusions and implications
   - Limitations mentioned
3. Store your extraction using store_extraction

Be thorough but concise.""",
                    ),
                )
            ]
        )

    if name == "analyze_paper":
        paper_id = args.get("paper_id", "")
        focus = args.get("focus", "all")
        return GetPromptResult(
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please analyze paper {paper_id}:

1. First, get the paper content using get_paper_content
2. Analyze focusing on: {focus}
3. Provide structured analysis with:
   - Methodology assessment (rigor, appropriateness)
   - Key findings evaluation
   - Relevance to current research
   - Potential applications
   - Identified limitations or gaps
4. Store your analysis using store_extraction""",
                    ),
                )
            ]
        )

    if name == "find_related":
        query = args.get("query", "")
        limit = args.get("limit", "10")
        return GetPromptResult(
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Find papers related to: {query}

1. Use semantic_search to find up to {limit} related papers
2. For each result, briefly explain why it's relevant
3. Group results by relevance level (highly relevant, somewhat relevant)
4. Suggest which papers deserve closer examination""",
                    ),
                )
            ]
        )

    if name == "extraction_report":
        return GetPromptResult(
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""Generate an extraction status report:

1. Use get_extraction_queue to see papers needing extraction
2. Summarize:
   - Total papers needing extraction
   - Papers with full text available
   - Papers missing abstracts
3. Recommend which papers to prioritize for extraction""",
                    ),
                )
            ]
        )

    return GetPromptResult(messages=[])


async def main_async():
    """Run the MCP server (async)."""
    # Initialize logging
    setup_logging()

    logger.info("Starting Literature MCP Server...")
    logger.info(f"Database: {core_settings.database_path}")
    logger.info("Architecture: MCP → Services → SQLAlchemy → SQLite (no HTTP)")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def _handle_shutdown(signum, frame):
    """Handle graceful shutdown."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """Entry point for the MCP server."""
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("MCP Server stopped by user")
    except Exception as e:
        logger.error(f"MCP Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
