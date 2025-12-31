"""Extraction Tools for MCP Server.

These tools provide AI-powered paper extraction using local LLM (Ollama)
or Claude API to extract summaries, key findings, methodology, and topics.

Architecture:
    MCP Tool (this file) -> ExtractionService -> LLM (Ollama/Claude)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import get_logger, success, error, batch_result  # noqa: E402
from services import ExtractionService  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List extraction tools."""
    return [
        Tool(
            name="get_extraction_status",
            description=(
                "Get extraction coverage statistics. Shows how many papers have "
                "AI-extracted summaries, key findings, and methodology."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_llm_status",
            description=(
                "Check which LLM backends are available for extraction. "
                "Shows Ollama (local) and Claude API status."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="extract_paper",
            description=(
                "Extract structured content from a paper using AI. Extracts: "
                "paper type, topics, one-sentence summary, key findings, methodology. "
                "Uses Ollama by default, falls back to Claude if configured."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to extract",
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["ollama", "claude", "auto"],
                        "description": "LLM backend: ollama, claude, or auto",
                        "default": "auto",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Re-extract even if extraction exists (default: false)",
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="extract_papers_batch",
            description=(
                "Extract multiple papers in batch. Includes rate limiting to "
                "avoid overloading the LLM. Use for processing the extraction queue."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to extract (omit to use queue)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max papers from queue if no IDs specified (default: 10)",
                        "default": 10,
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["ollama", "claude", "auto"],
                        "description": "LLM backend to use (default: auto)",
                        "default": "auto",
                    },
                    "delay": {
                        "type": "number",
                        "description": "Seconds between extractions (rate limiting)",
                        "default": 1.0,
                    },
                },
            },
        ),
        Tool(
            name="delete_extraction",
            description=(
                "Delete extraction for a paper to allow re-extraction. "
                "Use when extraction quality was poor or paper content was updated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to delete extraction for",
                    },
                },
                "required": ["paper_id"],
            },
        ),
    ]


def _to_response(data: dict) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=json.dumps(data, indent=2))]


def _get_extraction_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get extraction coverage statistics."""
    status = ExtractionService.get_extraction_status()

    return _to_response(success({
        "total_papers": status.total_papers,
        "papers_with_full_text": status.papers_with_full_text,
        "papers_with_abstract": status.papers_with_abstract,
        "papers_with_extraction": status.papers_with_extraction,
        "papers_needing_extraction": status.papers_needing_extraction,
        "extraction_coverage_percent": round(status.extraction_coverage_percent, 1),
    }))


def _get_llm_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get LLM backend status."""
    status = ExtractionService.get_llm_status()
    return _to_response(success(status))


async def _extract_paper(arguments: dict[str, Any]) -> list[TextContent]:
    """Extract a single paper."""
    paper_id = arguments["paper_id"]
    backend = arguments.get("backend", "auto")
    force = arguments.get("force", False)

    result = await ExtractionService.extract_paper(
        paper_id=paper_id,
        backend=backend,
        force=force
    )

    response = {
        "paper_id": result.paper_id,
        "success": result.success,
        "extractor_model": result.extractor_model,
    }

    if result.success:
        response["extraction"] = {
            "paper_type": result.paper_type,
            "topics": result.topics,
            "one_sentence_summary": result.one_sentence_summary,
            "key_findings": result.key_findings,
            "methodology_summary": result.methodology_summary,
        }

    if result.error:
        response["message"] = result.error

    return _to_response(success(response) if result.success else error(
        result.error or "Extraction failed",
        code="EXTRACTION_FAILED",
        details={"paper_id": paper_id}
    ))


async def _extract_papers_batch(arguments: dict[str, Any]) -> list[TextContent]:
    """Extract multiple papers."""
    paper_ids = arguments.get("paper_ids")
    limit = arguments.get("limit", 10)
    backend = arguments.get("backend", "auto")
    delay = arguments.get("delay", 1.0)

    result = await ExtractionService.extract_batch(
        paper_ids=paper_ids,
        limit=limit,
        backend=backend,
        delay=delay
    )

    return _to_response(batch_result(
        processed=[
            {"extracted": result.papers_extracted},
            {"skipped": result.papers_skipped},
            {"error": result.papers_error},
        ],
        failed=[{"error": e} for e in result.errors],
        message=(
            f"Processed {result.papers_processed} papers: "
            f"{result.papers_extracted} extracted, "
            f"{result.papers_skipped} already done, "
            f"{result.papers_error} errors"
        )
    ))


def _delete_extraction(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete extraction for a paper."""
    paper_id = arguments["paper_id"]
    deleted = ExtractionService.delete_extraction(paper_id)

    if deleted:
        return _to_response(success({
            "paper_id": paper_id,
            "message": f"Extraction deleted for paper {paper_id}"
        }))
    else:
        return _to_response(error(
            f"No extraction found for paper {paper_id}",
            code="NOT_FOUND",
            details={"paper_id": paper_id}
        ))


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute an extraction tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    try:
        if name == "get_extraction_status":
            return _get_extraction_status(arguments)

        if name == "get_llm_status":
            return _get_llm_status(arguments)

        if name == "extract_paper":
            return await _extract_paper(arguments)

        if name == "extract_papers_batch":
            return await _extract_papers_batch(arguments)

        if name == "delete_extraction":
            return _delete_extraction(arguments)

        return _to_response(error(f"Unknown extraction tool: {name}", code="UNKNOWN_TOOL"))

    except Exception as e:
        logger.error(f"Extraction tool error in {name}: {e}")
        return _to_response(error(f"Extraction error: {str(e)}", code="EXTRACTION_ERROR"))
