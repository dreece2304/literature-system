"""Shared summary enrichment for MCP tool modules.

Single implementation of the batch summary enrichment that was previously
copy-pasted verbatim in search.py and discovery.py (audit 2026-07-23).

Usage:
    from mcp_server.tools._summaries import enrich_with_summaries

    results = enrich_with_summaries(results)
"""
from __future__ import annotations


def enrich_with_summaries(results: list[dict]) -> list[dict]:
    """Batch-enrich search results with extraction summaries.

    Efficiently fetches one_sentence_summary and paper_type for all results
    in a single database query. Prefers deep-tier extraction fields over
    quick-tier when both are present; null-fills papers with no content row.

    Args:
        results: List of search result dicts with 'id' field

    Returns:
        Results with added 'summary', 'paper_type' and 'topics' fields
    """
    if not results:
        return results

    # Imported at call time so the test suite's DatabaseOverride (which
    # patches literature_core.get_session) is honored.
    from literature_core import get_session
    from literature_core.models import PaperContent

    paper_ids = [r["id"] for r in results if "id" in r]

    with get_session() as session:
        contents = session.query(
            PaperContent.paper_id,
            PaperContent.one_sentence_summary,
            PaperContent.paper_type,
            PaperContent.topics,
            PaperContent.deep_one_sentence_summary,
            PaperContent.deep_paper_type,
        ).filter(PaperContent.paper_id.in_(paper_ids)).all()

        # Build lookup map
        summary_map = {}
        for content in contents:
            # Prefer deep extraction if available, else quick
            summary = content.deep_one_sentence_summary or content.one_sentence_summary
            paper_type = content.deep_paper_type or content.paper_type
            summary_map[content.paper_id] = {
                "summary": summary,
                "paper_type": paper_type,
                "topics": content.topics or [],
            }

    # Enrich results
    enriched = []
    for result in results:
        paper_id = result.get("id")
        enriched_result = result.copy()
        if paper_id in summary_map:
            enriched_result["summary"] = summary_map[paper_id]["summary"]
            enriched_result["paper_type"] = summary_map[paper_id]["paper_type"]
            enriched_result["topics"] = summary_map[paper_id]["topics"]
        else:
            enriched_result["summary"] = None
            enriched_result["paper_type"] = None
            enriched_result["topics"] = []
        enriched.append(enriched_result)

    return enriched
