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

from literature_core import get_logger, success, error, batch_result, serialize  # noqa: E402
from services import ExtractionService, PaperService, PaperImportService  # noqa: E402
from literature_core import Paper, PaperContent, PaperReference, get_session  # noqa: E402
from dataclasses import asdict  # noqa: E402
from difflib import SequenceMatcher  # noqa: E402

logger = get_logger(__name__)


async def list_tools() -> list[Tool]:
    """List extraction tools (consolidated from 22 to 8)."""
    return [
        # =================================================================
        # CONSOLIDATED: extract_paper (merges quick/deep/legacy)
        # =================================================================
        Tool(
            name="extract_paper",
            description="AI extraction. tier: quick (abstract→type,topics,summary) or deep (full-text→findings,methods,claims)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to extract",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["quick", "deep"],
                        "description": "Extraction tier: quick (abstract-only) or deep (full-text, requires PDF)",
                        "default": "quick",
                    },
                    "backend": {
                        "type": "string",
                        "enum": ["ollama", "auto"],
                        "description": "LLM backend",
                        "default": "auto",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Re-extract even if exists",
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        # =================================================================
        # CONSOLIDATED: get_extraction_status (merges status/llm/queue views)
        # =================================================================
        Tool(
            name="get_extraction_status",
            description="Extraction info. view: status (coverage), llm (backend), queue (needs extraction), reextraction (has extraction)",
            inputSchema={
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "enum": ["status", "llm", "queue", "reextraction"],
                        "description": "View: status (coverage stats), llm (backend availability), queue (needs extraction), reextraction (existing extractions)",
                        "default": "status",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For queue/reextraction: max papers",
                        "default": 50,
                    },
                    "older_than_days": {
                        "type": "integer",
                        "description": "For reextraction: filter by age",
                    },
                },
            },
        ),
        # =================================================================
        # CONSOLIDATED: manage_pdf_processing (merges 5 tools)
        # =================================================================
        Tool(
            name="manage_pdf_processing",
            description="PDF text chunking. action: status, queue_status, add, process, retry",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "queue_status", "add", "process", "retry"],
                        "description": "Action: status (single paper), queue_status (queue list), add (queue paper), process (run queue), retry (failed papers)",
                        "default": "queue_status",
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "For status/add/retry: paper ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For queue_status/process/retry: max papers",
                        "default": 20,
                    },
                    "force": {
                        "type": "boolean",
                        "description": "For add/process: re-process even if exists",
                        "default": False,
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["pending", "processing", "failed", "needs_processing"],
                        "description": "For queue_status: filter by status",
                    },
                },
            },
        ),
        # =================================================================
        # CONSOLIDATED: manage_references (merges 4 tools)
        # =================================================================
        Tool(
            name="manage_references",
            description="PDF-extracted references. action: list, unmatched, match, import",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "unmatched", "match", "import"],
                        "description": "Action: list (paper refs), unmatched (all unmatched), match (find library match), import (create paper)",
                        "default": "list",
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "For list: paper ID to get references for",
                    },
                    "reference_id": {
                        "type": "integer",
                        "description": "For match/import: reference ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For unmatched: max references",
                        "default": 50,
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "unmatched", "matched", "imported"],
                        "description": "For list: filter by match status",
                        "default": "all",
                    },
                    "with_doi_only": {
                        "type": "boolean",
                        "description": "For unmatched: only refs with DOI",
                        "default": False,
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For import: tags to apply",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "For import: collection to add to",
                    },
                },
            },
        ),
        # =================================================================
        # CONSOLIDATED: verify_extraction (merges 3 tools)
        # =================================================================
        Tool(
            name="verify_extraction",
            description="Verify extractions. scope: single, batch, report (quality check)",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["single", "batch", "report"],
                        "description": "Scope: single (one paper), batch (multiple), report (quality summary)",
                        "default": "single",
                    },
                    "paper_id": {
                        "type": "integer",
                        "description": "For single: paper ID to verify",
                    },
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "For batch: paper IDs (omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For batch/report: max papers",
                        "default": 50,
                    },
                },
            },
        ),
        # =================================================================
        # KEPT SEPARATE: Batch, prepare, flag, delete
        # =================================================================
        Tool(
            name="extract_papers_batch",
            description="Batch extraction with rate limiting. Uses queue if no paper_ids",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paper IDs to extract (omit to use queue)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max papers from queue",
                        "default": 10,
                    },
                    "delay": {
                        "type": "number",
                        "description": "Seconds between extractions",
                        "default": 1.0,
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Re-extract existing",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="prepare_extraction",
            description="Get paper content for Claude extraction. tier: quick or deep",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["quick", "deep"],
                        "description": "Extraction tier",
                        "default": "quick",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Max chars for deep tier",
                        "default": 80000,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="flag_for_deep_extraction",
            description="Flag paper(s) for deep extraction",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "integer", "description": "Single paper ID"},
                    "paper_ids": {"type": "array", "items": {"type": "integer"}, "description": "Batch paper IDs"},
                },
            },
        ),
    ]


def _to_response(data: dict, tool_name: str | None = None) -> list[TextContent]:
    """Convert a response dict to TextContent list."""
    return [TextContent(type="text", text=serialize(data, tool_name))]


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


def _get_reextraction_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers with existing extractions for re-extraction."""
    papers = ExtractionService.get_papers_with_extractions(
        limit=arguments.get("limit", 50),
        older_than_days=arguments.get("older_than_days"),
        schema_version=arguments.get("schema_version"),
        extractor_model=arguments.get("extractor_model"),
    )

    return _to_response(success({
        "count": len(papers),
        "papers": papers,
        "hint": "Use extract_papers_batch with paper_ids and force=true to re-extract"
    }))


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


async def _extract_paper_quick(arguments: dict[str, Any]) -> list[TextContent]:
    """Extract quick tier (abstract-only) for a paper."""
    paper_id = arguments["paper_id"]
    backend = arguments.get("backend", "auto")
    force = arguments.get("force", False)

    result = await ExtractionService.extract_paper_quick(
        paper_id=paper_id,
        backend=backend,
        force=force
    )

    response = {
        "paper_id": result.paper_id,
        "success": result.success,
        "tier": "quick",
        "extractor_model": result.extractor_model,
    }

    if result.success:
        response["extraction"] = {
            "paper_type": result.paper_type,
            "topics": result.topics,
            "one_sentence_summary": result.one_sentence_summary,
        }

    if result.error:
        response["message"] = result.error

    if result.elapsed_seconds:
        response["elapsed_seconds"] = round(result.elapsed_seconds, 2)

    return _to_response(success(response) if result.success else error(
        result.error or "Quick extraction failed",
        code="EXTRACTION_FAILED",
        details={"paper_id": paper_id, "tier": "quick"}
    ))


async def _extract_paper_deep(arguments: dict[str, Any]) -> list[TextContent]:
    """Extract deep tier using 2-pass approach (chunks → consolidation)."""
    paper_id = arguments["paper_id"]
    backend = arguments.get("backend", "auto")
    force = arguments.get("force", False)

    result = await ExtractionService.extract_paper_deep(
        paper_id=paper_id,
        backend=backend,
        force=force
    )

    response = {
        "paper_id": result.paper_id,
        "success": result.success,
        "tier": "deep",
        "extractor_model": result.extractor_model,
    }

    if result.success:
        response["extraction"] = {
            "paper_type": result.paper_type,
            "topics": result.topics,
            "one_sentence_summary": result.one_sentence_summary,
            "key_findings": result.key_findings,
            "methodology_summary": result.methodology_summary,
            "quantitative_results": result.quantitative_results,
            "citable_claims": result.citable_claims,
            "techniques_used": result.techniques_used,
        }

    if result.error:
        response["message"] = result.error

    if result.elapsed_seconds:
        response["elapsed_seconds"] = round(result.elapsed_seconds, 2)

    return _to_response(success(response) if result.success else error(
        result.error or "Deep extraction failed",
        code="EXTRACTION_FAILED",
        details={"paper_id": paper_id, "tier": "deep"}
    ))


async def _extract_papers_batch(arguments: dict[str, Any]) -> list[TextContent]:
    """Extract multiple papers."""
    paper_ids = arguments.get("paper_ids")
    limit = arguments.get("limit", 10)
    backend = arguments.get("backend", "auto")
    delay = arguments.get("delay", 1.0)
    force = arguments.get("force", False)

    result = await ExtractionService.extract_batch(
        paper_ids=paper_ids,
        limit=limit,
        backend=backend,
        delay=delay,
        force=force
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


def _prepare_extraction(arguments: dict[str, Any]) -> list[TextContent]:
    """Prepare paper content and project context for Claude extraction.

    Returns everything Claude needs to extract structured data from a paper:
    - Paper content (title, abstract, optionally full text)
    - Project registry with topics and relevance hints
    - Whether paper is already cited in each project's .bib file
    - Extraction schema for the requested tier
    """
    paper_id = arguments["paper_id"]
    tier = arguments.get("tier", "quick")
    max_chars = arguments.get("max_chars", 80000)

    # Get paper from database
    with get_session() as session:
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return _to_response(error(
                f"Paper {paper_id} not found",
                code="NOT_FOUND",
                details={"paper_id": paper_id}
            ))

        # Get existing extraction if any
        existing = session.query(PaperContent).filter(
            PaperContent.paper_id == paper_id
        ).first()

        # Build paper content
        paper_content = {
            "id": paper.id,
            "title": paper.title,
            "authors": [a.name for a in paper.authors] if paper.authors else [],
            "year": paper.year,
            "doi": paper.doi,
            "journal": paper.journal,
            "abstract": paper.abstract,
        }

        # Add full text for deep tier
        # Get full text from chunks (Paper.full_text column is deprecated)
        full_text = PaperService.get_full_text(paper_id, session)

        if tier == "deep" and full_text:
            word_count = len(full_text.split())

            # Smart truncation for long papers
            if len(full_text) > max_chars:
                # Try to preserve key sections
                truncated = _smart_truncate(full_text, max_chars)
                paper_content["full_text"] = truncated
                paper_content["full_text_truncated"] = True
                paper_content["original_chars"] = len(full_text)
            else:
                paper_content["full_text"] = full_text
                paper_content["full_text_truncated"] = False

            paper_content["word_count"] = word_count
        else:
            paper_content["full_text"] = None
            paper_content["word_count"] = len(paper.abstract.split()) if paper.abstract else 0

        # Build existing extraction info
        existing_extraction = None
        if existing:
            existing_extraction = {
                "has_extraction": True,
                "paper_type": existing.paper_type,
                "one_sentence_summary": existing.one_sentence_summary,
                "extraction_date": existing.extraction_date.isoformat() if existing.extraction_date else None,
                "extractor_model": existing.extractor_model,
            }
        else:
            existing_extraction = {"has_extraction": False}

    # Get projects with bib status
    projects = PaperService.get_projects_with_bib_status(paper_id)

    # Detect if likely a review paper
    word_count = paper_content.get("word_count", 0)
    review_detection = {
        "likely_review": word_count > 15000,
        "word_count": word_count,
        "recommendation": "two_pass" if word_count > 15000 else "single_pass"
    }

    # Build extraction schema based on tier
    if tier == "quick":
        extraction_schema = {
            "tier": "quick",
            "required_fields": ["paper_type", "topics", "one_sentence_summary", "project_relevance"],
            "optional_fields": [],
            "instructions": (
                "Extract paper_type (research_article, review, letter, conference, etc.), "
                "3-5 topics, a one_sentence_summary (WHAT + HOW + RESULT), and "
                "project_relevance scores for each project listed."
            ),
            "project_relevance_schema": {
                "relevance": "high|medium|low|none",
                "reason": "Brief explanation",
                "primary_use": "background|methods|results_comparison|discussion|none",
                "already_cited": "boolean (from paper_in_bib field)"
            }
        }
    else:
        extraction_schema = {
            "tier": "deep",
            "required_fields": [
                "paper_type", "topics", "one_sentence_summary", "project_relevance",
                "key_findings", "methodology_summary"
            ],
            "optional_fields": [
                "quantitative_results", "citable_claims", "techniques_used",
                "experimental_conditions", "discussion_summary", "research_context",
                "prior_work_comparison", "citation_contexts", "future_directions",
                "papers_to_follow"
            ],
            "instructions": (
                "Extract all required fields plus as many optional fields as the paper supports. "
                "For quantitative_results, include specific numbers with units and conditions. "
                "For papers_to_follow, identify 2-3 key cited papers worth reading."
            ),
            "project_relevance_schema": {
                "relevance": "high|medium|low|none",
                "reason": "Brief explanation",
                "primary_use": "background|methods|results_comparison|discussion|none",
                "already_cited": "boolean (from paper_in_bib field)"
            }
        }

    return _to_response(success({
        "paper_id": paper_id,
        "tier": tier,
        "paper": paper_content,
        "existing_extraction": existing_extraction,
        "projects": projects,
        "review_detection": review_detection,
        "extraction_schema": extraction_schema,
    }))


def _smart_truncate(text: str, max_chars: int) -> str:
    """Smart truncation that preserves key sections.

    Tries to keep: abstract/introduction, methods, results/discussion, conclusion.
    """
    if len(text) <= max_chars:
        return text

    # Simple approach: take beginning and end
    # More sophisticated: find section headers and sample proportionally
    half = max_chars // 2

    # Try to find natural break points
    intro_end = text.find("\n\n", half - 1000, half + 1000)
    if intro_end == -1:
        intro_end = half

    conclusion_start = text.rfind("\n\n", len(text) - half - 1000, len(text) - half + 1000)
    if conclusion_start == -1:
        conclusion_start = len(text) - half

    truncated = (
        text[:intro_end] +
        "\n\n[... content truncated for length ...]\n\n" +
        text[conclusion_start:]
    )

    return truncated


# ============================================================================
# PDF Processing Tool Handlers (renamed from Chunking)
# ============================================================================


def _get_pdf_processing_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get PDF processing status for a paper."""
    paper_id = arguments["paper_id"]
    status = ExtractionService.get_queue_status(paper_id)
    return _to_response(success(status))


def _get_pdf_processing_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get papers in the PDF processing queue."""
    status = arguments.get("status")
    limit = arguments.get("limit", 20)

    # Map needs_processing to needs_extraction for service compatibility
    if status == "needs_processing":
        status = "needs_extraction"

    papers = ExtractionService.get_extraction_queue(status=status, limit=limit)

    return _to_response(success({
        "count": len(papers),
        "status_filter": status,
        "papers": papers,
    }))


def _queue_pdf_processing(arguments: dict[str, Any]) -> list[TextContent]:
    """Queue a paper for PDF processing."""
    paper_id = arguments["paper_id"]
    force = arguments.get("force", False)

    result = ExtractionService.queue_extraction(paper_id, force=force)
    return _to_response(success(result))


def _process_pdf_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Process papers in the PDF queue."""
    limit = arguments.get("limit", 10)
    force = arguments.get("force", False)

    results = ExtractionService.process_extraction_queue(limit=limit, force=force)

    summary = {
        "processed": len(results),
        "complete": sum(1 for r in results if r.status == "complete"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
    }

    details = [asdict(r) for r in results]

    return _to_response(success({
        "summary": summary,
        "results": details,
    }))


def _retry_pdf_processing(arguments: dict[str, Any]) -> list[TextContent]:
    """Retry PDF processing for failed papers."""
    paper_id = arguments.get("paper_id")
    limit = arguments.get("limit", 10)

    if paper_id:
        # Retry single paper
        result = ExtractionService.queue_extraction(paper_id, force=True)
        return _to_response(success({
            "paper_id": paper_id,
            "result": result,
        }))
    else:
        # Retry all failed
        requeued = ExtractionService.retry_failed_extractions(limit=limit)
        return _to_response(success({
            "requeued_count": len(requeued),
            "papers": requeued,
        }))


# ============================================================================
# Reference Tool Handlers
# ============================================================================


def _get_extracted_references(arguments: dict[str, Any]) -> list[TextContent]:
    """Get PDF-extracted references for a paper."""
    paper_id = arguments["paper_id"]
    status_filter = arguments.get("status", "all")

    with get_session() as session:
        query = session.query(PaperReference).filter(
            PaperReference.paper_id == paper_id
        )

        if status_filter != "all":
            query = query.filter(PaperReference.match_status == status_filter)

        refs = query.order_by(PaperReference.reference_order).all()

        reference_list = [{
            "id": ref.id,
            "order": ref.reference_order,
            "raw_text": ref.raw_text[:200] + "..." if len(ref.raw_text) > 200 else ref.raw_text,
            "parsed": {
                "title": ref.parsed_title,
                "authors": ref.parsed_authors,
                "year": ref.parsed_year,
                "journal": ref.parsed_journal,
                "doi": ref.parsed_doi,
                "arxiv_id": ref.parsed_arxiv_id,
            },
            "match_status": ref.match_status,
            "matched_paper_id": ref.matched_paper_id,
            "confidence": ref.parse_confidence,
        } for ref in refs]

        return _to_response(success({
            "paper_id": paper_id,
            "count": len(reference_list),
            "references": reference_list,
        }))


def _match_reference_to_library(arguments: dict[str, Any]) -> list[TextContent]:
    """Try to match a reference to papers in the library."""
    reference_id = arguments["reference_id"]

    with get_session() as session:
        ref = session.query(PaperReference).filter(
            PaperReference.id == reference_id
        ).first()

        if not ref:
            return _to_response(error(
                f"Reference {reference_id} not found",
                code="NOT_FOUND"
            ))

        matches = []

        # Try DOI match first (most reliable)
        if ref.parsed_doi:
            paper = session.query(Paper).filter(
                Paper.doi == ref.parsed_doi
            ).first()
            if paper:
                matches.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "match_type": "doi",
                    "confidence": 1.0,
                })

        # Try title similarity if no DOI match
        if not matches and ref.parsed_title:
            # Get papers with similar titles
            papers = session.query(Paper.id, Paper.title).all()
            for paper_id, paper_title in papers:
                if paper_title:
                    similarity = SequenceMatcher(
                        None,
                        ref.parsed_title.lower(),
                        paper_title.lower()
                    ).ratio()
                    if similarity > 0.85:
                        matches.append({
                            "paper_id": paper_id,
                            "title": paper_title,
                            "match_type": "title_similarity",
                            "confidence": round(similarity, 3),
                        })

        # Sort by confidence
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        matches = matches[:5]  # Top 5 matches

        # Update reference if we found a strong match
        if matches and matches[0]["confidence"] >= 0.95:
            ref.match_status = "matched"
            ref.matched_paper_id = matches[0]["paper_id"]
            session.commit()

        return _to_response(success({
            "reference_id": reference_id,
            "reference_title": ref.parsed_title,
            "matches": matches,
            "updated_status": ref.match_status,
        }))


async def _import_reference(arguments: dict[str, Any]) -> list[TextContent]:
    """Import a reference as a new paper."""
    reference_id = arguments["reference_id"]
    tags = arguments.get("tags")
    collection_id = arguments.get("collection_id")

    with get_session() as session:
        ref = session.query(PaperReference).filter(
            PaperReference.id == reference_id
        ).first()

        if not ref:
            return _to_response(error(
                f"Reference {reference_id} not found",
                code="NOT_FOUND"
            ))

        if ref.match_status == "imported":
            return _to_response(error(
                f"Reference already imported as paper {ref.matched_paper_id}",
                code="ALREADY_IMPORTED",
                details={"paper_id": ref.matched_paper_id}
            ))

        # Use import wizard with parsed data
        result = await PaperImportService.import_paper(
            doi=ref.parsed_doi,
            arxiv_id=ref.parsed_arxiv_id,
            title=ref.parsed_title,
            authors=ref.parsed_authors,
            year=ref.parsed_year,
            tags=tags,
            collection_id=collection_id,
        )

        # Update reference status
        if result.status == "success" and result.paper_id:
            ref.match_status = "imported"
            ref.matched_paper_id = result.paper_id
            session.commit()

        response = {
            "reference_id": reference_id,
            "import_status": result.status,
            "sources_checked": result.sources_checked,
        }

        if result.paper_id:
            response["paper_id"] = result.paper_id
        if result.paper:
            response["paper"] = result.paper
        if result.message:
            response["message"] = result.message

        return _to_response(success(response))


def _get_unmatched_references(arguments: dict[str, Any]) -> list[TextContent]:
    """Get unmatched references across all papers."""
    limit = arguments.get("limit", 50)
    with_doi_only = arguments.get("with_doi_only", False)

    with get_session() as session:
        query = session.query(
            PaperReference.id,
            PaperReference.paper_id,
            PaperReference.raw_text,
            PaperReference.parsed_title,
            PaperReference.parsed_authors,
            PaperReference.parsed_year,
            PaperReference.parsed_doi,
            PaperReference.parsed_arxiv_id,
            PaperReference.parse_confidence,
            Paper.title.label('source_paper_title'),
        ).join(
            Paper, PaperReference.paper_id == Paper.id
        ).filter(
            PaperReference.match_status == 'unmatched'
        )

        if with_doi_only:
            query = query.filter(PaperReference.parsed_doi.isnot(None))

        # Order by confidence (higher first) and limit
        query = query.order_by(PaperReference.parse_confidence.desc()).limit(limit)

        refs = query.all()

        reference_list = [{
            "id": r.id,
            "source_paper_id": r.paper_id,
            "source_paper_title": r.source_paper_title,
            "raw_text": r.raw_text[:150] + "..." if len(r.raw_text) > 150 else r.raw_text,
            "parsed_title": r.parsed_title,
            "parsed_authors": r.parsed_authors,
            "parsed_year": r.parsed_year,
            "parsed_doi": r.parsed_doi,
            "parsed_arxiv_id": r.parsed_arxiv_id,
            "confidence": r.parse_confidence,
        } for r in refs]

        return _to_response(success({
            "count": len(reference_list),
            "with_doi_only": with_doi_only,
            "references": reference_list,
        }))


def _verify_paper_extraction(arguments: dict[str, Any]) -> list[TextContent]:
    """Verify extraction against source text."""
    paper_id = arguments["paper_id"]
    result = ExtractionService.verify_extraction(paper_id)

    if "error" in result:
        return _to_response(error(result["error"], code="VERIFICATION_ERROR"))

    return _to_response(success(result))


def _batch_verify_extractions(arguments: dict[str, Any]) -> list[TextContent]:
    """Verify extractions for multiple papers."""
    paper_ids = arguments.get("paper_ids")
    limit = arguments.get("limit", 20)

    results = ExtractionService.batch_verify(paper_ids=paper_ids, limit=limit)

    # Summary stats
    if results:
        scores = [r.get("verification_score", 0) for r in results]
        avg_score = sum(scores) / len(scores)
        low_score_count = sum(1 for s in scores if s < 0.5)
    else:
        avg_score = 0
        low_score_count = 0

    return _to_response(success({
        "count": len(results),
        "average_score": round(avg_score, 2),
        "papers_with_low_score": low_score_count,
        "results": results,
        "hint": "Papers with score < 0.5 may contain hallucinations - consider re-extraction"
    }))


def _get_quality_report(arguments: dict[str, Any]) -> list[TextContent]:
    """Generate extraction quality report."""
    limit = arguments.get("limit", 50)
    report = ExtractionService.generate_quality_report(limit)
    return _to_response(success({"report": report}))


def _flag_for_deep_extraction(arguments: dict) -> list[TextContent]:
    """Flag a paper or papers for deep extraction."""
    paper_ids = arguments.get("paper_ids")
    paper_id = arguments.get("paper_id")

    if paper_ids:
        # Batch flag
        result = PaperService.batch_flag_for_deep_extraction(paper_ids)
        return _to_response(success(result))
    elif paper_id:
        # Single flag
        try:
            paper = PaperService.flag_for_deep_extraction(paper_id)
            return _to_response(success({
                "paper_id": paper_id,
                "status": "flagged",
                "enrichment_status": paper.get("enrichment_status"),
            }))
        except Exception as e:
            return _to_response(error(str(e)))
    else:
        return _to_response(error("Must provide paper_id or paper_ids"))


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute an extraction tool.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with the result
    """
    try:
        # =================================================================
        # CONSOLIDATED: extract_paper (with tier parameter)
        # =================================================================
        if name == "extract_paper":
            tier = arguments.get("tier", "quick")
            if tier == "deep":
                return await _extract_paper_deep(arguments)
            else:
                return await _extract_paper_quick(arguments)

        # =================================================================
        # CONSOLIDATED: get_extraction_status (with view parameter)
        # =================================================================
        if name == "get_extraction_status":
            view = arguments.get("view", "status")
            if view == "llm":
                return _get_llm_status(arguments)
            elif view == "queue":
                # Use existing queue function - papers needing extraction
                return _get_pdf_processing_queue(arguments)
            elif view == "reextraction":
                return _get_reextraction_queue(arguments)
            else:  # status
                return _get_extraction_status(arguments)

        # =================================================================
        # CONSOLIDATED: manage_pdf_processing (with action parameter)
        # =================================================================
        if name == "manage_pdf_processing":
            action = arguments.get("action", "queue_status")
            if action == "status":
                return _get_pdf_processing_status(arguments)
            elif action == "queue_status":
                return _get_pdf_processing_queue(arguments)
            elif action == "add":
                return _queue_pdf_processing(arguments)
            elif action == "process":
                return _process_pdf_queue(arguments)
            elif action == "retry":
                return _retry_pdf_processing(arguments)
            else:
                return _to_response(error(f"Unknown action: {action}"))

        # =================================================================
        # CONSOLIDATED: manage_references (with action parameter)
        # =================================================================
        if name == "manage_references":
            action = arguments.get("action", "list")
            if action == "list":
                return _get_extracted_references(arguments)
            elif action == "unmatched":
                return _get_unmatched_references(arguments)
            elif action == "match":
                return _match_reference_to_library(arguments)
            elif action == "import":
                return await _import_reference(arguments)
            else:
                return _to_response(error(f"Unknown action: {action}"))

        # =================================================================
        # CONSOLIDATED: verify_extraction (with scope parameter)
        # =================================================================
        if name == "verify_extraction":
            scope = arguments.get("scope", "single")
            if scope == "single":
                return _verify_paper_extraction(arguments)
            elif scope == "batch":
                return _batch_verify_extractions(arguments)
            elif scope == "report":
                return _get_quality_report(arguments)
            else:
                return _to_response(error(f"Unknown scope: {scope}"))

        # =================================================================
        # KEPT SEPARATE
        # =================================================================
        if name == "extract_papers_batch":
            return await _extract_papers_batch(arguments)

        if name == "prepare_extraction":
            return _prepare_extraction(arguments)

        if name == "flag_for_deep_extraction":
            return _flag_for_deep_extraction(arguments)

        # =================================================================
        # LEGACY TOOL NAMES (redirect to consolidated tools)
        # =================================================================
        if name == "extract_paper_quick":
            return await _extract_paper_quick(arguments)
        if name == "extract_paper_deep":
            return await _extract_paper_deep(arguments)
        if name == "get_llm_status":
            return _get_llm_status(arguments)
        if name == "get_reextraction_queue":
            return _get_reextraction_queue(arguments)
        if name == "delete_extraction":
            return _delete_extraction(arguments)
        if name == "get_pdf_processing_status":
            return _get_pdf_processing_status(arguments)
        if name == "get_pdf_processing_queue":
            return _get_pdf_processing_queue(arguments)
        if name == "queue_pdf_processing":
            return _queue_pdf_processing(arguments)
        if name == "process_pdf_queue":
            return _process_pdf_queue(arguments)
        if name == "retry_pdf_processing":
            return _retry_pdf_processing(arguments)
        if name == "get_extracted_references":
            return _get_extracted_references(arguments)
        if name == "match_reference_to_library":
            return _match_reference_to_library(arguments)
        if name == "import_reference":
            return await _import_reference(arguments)
        if name == "get_unmatched_references":
            return _get_unmatched_references(arguments)
        if name == "verify_paper_extraction":
            return _verify_paper_extraction(arguments)
        if name == "batch_verify_extractions":
            return _batch_verify_extractions(arguments)
        if name == "get_quality_report":
            return _get_quality_report(arguments)

        return _to_response(error(f"Unknown extraction tool: {name}", code="UNKNOWN_TOOL"))

    except Exception as e:
        logger.error(f"Extraction tool error in {name}: {e}")
        return _to_response(error(f"Extraction error: {str(e)}", code="EXTRACTION_ERROR"))
