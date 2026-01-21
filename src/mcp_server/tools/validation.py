"""Validation Tools for MCP Server.

These tools provide paper validation against external databases
(CrossRef, Semantic Scholar, etc.) to verify papers exist.

Architecture:
    MCP Tool (this file) -> ValidationService -> ExternalSearchService -> External APIs

Consolidated tools:
    - get_validation_status: Coverage statistics
    - validate_papers: Queue, validate, and reset operations via action parameter
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool, TextContent

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import get_logger, success, error, batch_result, serialize
from services import ValidationService

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List validation tools."""
    return [
        Tool(
            name="get_validation_status",
            description="Validation coverage stats (verified, not found, errors)",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="validate_papers",
            description="Validate, queue, or reset paper validation. Actions: validate (default), queue, reset",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["validate", "queue", "reset"],
                        "description": "Action: validate (run validation), queue (get papers needing validation), reset (clear validation status)",
                        "default": "validate",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paper IDs (omit to use queue for validate, or reset ALL for reset)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max papers for validate/queue (default: 20)",
                        "default": 20,
                    },
                    "prioritize_with_doi": {
                        "type": "boolean",
                        "description": "For queue: show papers with DOI first",
                        "default": True,
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "For reset without paper_ids: must be true to reset ALL",
                    },
                },
            },
        ),
    ]


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


def _get_validation_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get validation coverage statistics."""
    status = ValidationService.get_validation_status()

    return _to_response(success({
        "total_papers": status.total_papers,
        "validated_papers": status.validated_papers,
        "unvalidated_papers": status.unvalidated_papers,
        "breakdown": {
            "verified": status.verified_papers,
            "not_found": status.not_found_papers,
            "error": status.error_papers,
        },
        "coverage": {
            "validation_percent": round(status.validation_coverage_percent, 1),
            "verification_rate_percent": round(status.verification_rate_percent, 1),
        },
        "identifier_stats": {
            "papers_with_doi": status.papers_with_doi,
            "papers_with_arxiv": status.papers_with_arxiv,
            "papers_with_title_only": status.papers_with_title_only,
        },
    }), "get_validation_status")


def _get_validation_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers needing validation."""
    papers = ValidationService.get_papers_needing_validation(
        limit=arguments.get("limit", 20),
        prioritize_with_doi=arguments.get("prioritize_with_doi", True)
    )

    return _to_response(success({
        "count": len(papers),
        "papers": papers,
    }), "get_validation_queue")


async def _validate_papers(arguments: dict[str, Any]) -> list[TextContent]:
    """Validate paper(s) against external databases."""
    paper_ids = arguments.get("paper_ids")
    limit = arguments.get("limit", 20)

    # Single paper validation
    if paper_ids and len(paper_ids) == 1:
        result = await ValidationService.validate_paper(paper_ids[0])

        response = {
            "paper_id": result.paper_id,
            "status": result.status,
            "source": result.source,
            "confidence": result.confidence,
        }

        if result.matched_doi:
            response["matched_doi"] = result.matched_doi
        if result.matched_title:
            response["matched_title"] = result.matched_title
        if result.message:
            response["message"] = result.message

        return _to_response(success(response), "validate_papers")

    # Batch validation
    result = await ValidationService.validate_batch(
        paper_ids=paper_ids,
        limit=limit
    )

    return _to_response(batch_result(
        processed=[
            {"verified": result.papers_verified},
            {"not_found": result.papers_not_found},
            {"error": result.papers_error},
        ],
        failed=[{"error": e} for e in result.errors],
        message=(
            f"Processed {result.papers_processed} papers: "
            f"{result.papers_verified} verified, "
            f"{result.papers_not_found} not found, "
            f"{result.papers_error} errors"
        )
    ), "validate_papers")


def _reset_validation(arguments: dict[str, Any]) -> list[TextContent]:
    """Reset validation status for papers."""
    paper_ids = arguments.get("paper_ids")
    confirm = arguments.get("confirm", False)

    # Require confirmation for resetting all papers
    if not paper_ids and not confirm:
        return _to_response(error(
            "Resetting ALL papers requires confirm=true",
            code="CONFIRMATION_REQUIRED"
        ))

    count = ValidationService.reset_validation(paper_ids=paper_ids)

    return _to_response(success({
        "papers_reset": count,
        "message": f"Reset validation status for {count} papers"
    }), "reset_validation")


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a validation tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    try:
        if name == "get_validation_status":
            return _get_validation_status(arguments)

        if name == "validate_papers":
            action = arguments.get("action", "validate")

            if action == "queue":
                return _get_validation_queue(arguments)
            elif action == "reset":
                return _reset_validation(arguments)
            else:  # validate (default)
                return await _validate_papers(arguments)

        return _to_response(error(f"Unknown validation tool: {name}", code="UNKNOWN_TOOL"))

    except Exception as e:
        logger.error(f"Validation tool error in {name}: {e}")
        return _to_response(error(f"Validation error: {str(e)}", code="VALIDATION_ERROR"))
