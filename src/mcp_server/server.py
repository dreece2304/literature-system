"""
Main MCP Server for Literature Management.

This server exposes tools to Claude Code for managing a literature database,
searching papers, and interacting with external academic APIs.

ARCHITECTURE: MCP Server → Service Layer → SQLAlchemy → SQLite
No HTTP API layer required - direct database access via services.

TOOL ROUTING: Uses a registry pattern where each tool module registers its
tools at startup. Tool names are mapped to their handler functions, eliminating
routing conflicts from pattern matching.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any, Callable, Awaitable

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
from .tools import papers  # noqa: E402
from .tools import search  # noqa: E402
from .tools import external  # noqa: E402
from .tools import citations  # noqa: E402
from .tools import pdf  # noqa: E402
from .tools import collections  # noqa: E402
from .tools import notes  # noqa: E402
from .tools import import_export  # noqa: E402
from .tools import project  # noqa: E402
from .tools import zotero  # noqa: E402
from .tools import browser_pdf  # noqa: E402
from .tools import discovery  # noqa: E402
from .tools import citation_network  # noqa: E402
from .tools import validation  # noqa: E402
from .resources.handlers import (  # noqa: E402
    list_resources,
    read_resource,
)

# Initialize the MCP Server
server = Server("literature")

# ============================================================================
# Tool Registry
# ============================================================================
# Maps tool names to their handler functions. Built at startup by iterating
# through all tool modules. This eliminates routing conflicts from pattern
# matching (e.g., "import_bib_to_database" matching "startswith('import_')").

# Type alias for tool handler functions
ToolHandler = Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]

# Registry mapping tool names to handlers
TOOL_REGISTRY: dict[str, ToolHandler] = {}

# All tool modules with their list_tools and call_tool functions
TOOL_MODULES = [
    (papers, "papers"),
    (search, "search"),
    (external, "external"),
    (citations, "citations"),
    (pdf, "pdf"),
    (collections, "collections"),
    (notes, "notes"),
    (import_export, "import_export"),
    (project, "project"),
    (zotero, "zotero"),
    (browser_pdf, "browser_pdf"),
    (discovery, "discovery"),
    (citation_network, "citation_network"),
    (validation, "validation"),
]


async def build_tool_registry() -> list[Tool]:
    """Build the tool registry and return all tools.

    Iterates through all tool modules, calls their list_tools() function,
    and registers each tool name with its module's call_tool handler.

    Returns:
        List of all Tool objects for the list_tools handler.
    """
    all_tools: list[Tool] = []

    for module, module_name in TOOL_MODULES:
        try:
            # Get tools from this module
            tools = await module.list_tools()

            # Register each tool with this module's call_tool handler
            for tool in tools:
                if tool.name in TOOL_REGISTRY:
                    logger.warning(
                        f"Duplicate tool name '{tool.name}' from module '{module_name}' "
                        f"- overwriting previous registration"
                    )
                TOOL_REGISTRY[tool.name] = module.call_tool

            all_tools.extend(tools)
            logger.debug(f"Registered {len(tools)} tools from {module_name}")

        except Exception as e:
            logger.error(f"Failed to load tools from {module_name}: {e}")

    logger.info(f"Tool registry built: {len(TOOL_REGISTRY)} tools registered")
    return all_tools


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available tools.

    Uses the tool registry to collect tools from all modules.
    The registry is built on first call and cached.
    """
    return await build_tool_registry()


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to appropriate handlers using the tool registry.

    The registry maps tool names directly to their module's call_tool function,
    eliminating routing conflicts from pattern matching.
    """
    # Ensure registry is built (idempotent after first call)
    if not TOOL_REGISTRY:
        await build_tool_registry()

    # Direct lookup - no pattern matching ambiguity
    if name not in TOOL_REGISTRY:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return await TOOL_REGISTRY[name](name, arguments)


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
