"""Tests for the shared search-result summary enrichment helper.

Audit finding (2026-07-23): _enrich_with_summaries was copy-pasted verbatim
in mcp_server/tools/search.py and mcp_server/tools/discovery.py. The logic
now lives in mcp_server.tools._summaries and the tool modules import it.
"""
import literature_core
from literature_core.models import Paper, PaperContent

from mcp_server.tools._summaries import enrich_with_summaries


class TestEnrichWithSummaries:
    """Behavior of the shared enrichment helper."""

    def test_empty_results_returned_unchanged(self, db):
        assert enrich_with_summaries([]) == []

    def test_prefers_deep_extraction_over_quick(self, db):
        with literature_core.get_session() as session:
            paper = Paper(title="Deep Paper")
            session.add(paper)
            session.flush()
            session.add(PaperContent(
                paper_id=paper.id,
                one_sentence_summary="quick summary",
                paper_type="experimental",
                topics=["ald"],
                deep_one_sentence_summary="deep summary",
                deep_paper_type="review",
            ))
            pid = paper.id

        results = enrich_with_summaries([{"id": pid}])

        assert results[0]["summary"] == "deep summary"
        assert results[0]["paper_type"] == "review"
        assert results[0]["topics"] == ["ald"]

    def test_falls_back_to_quick_fields(self, db):
        with literature_core.get_session() as session:
            paper = Paper(title="Quick Paper")
            session.add(paper)
            session.flush()
            session.add(PaperContent(
                paper_id=paper.id,
                one_sentence_summary="quick summary",
                paper_type="experimental",
            ))
            pid = paper.id

        results = enrich_with_summaries([{"id": pid}])

        assert results[0]["summary"] == "quick summary"
        assert results[0]["paper_type"] == "experimental"
        assert results[0]["topics"] == []

    def test_null_fills_papers_without_content(self, db):
        with literature_core.get_session() as session:
            paper = Paper(title="No Content")
            session.add(paper)
            session.flush()
            pid = paper.id

        results = enrich_with_summaries([{"id": pid, "title": "No Content"}])

        assert results[0]["summary"] is None
        assert results[0]["paper_type"] is None
        assert results[0]["topics"] == []
        # Original fields are preserved
        assert results[0]["title"] == "No Content"

    def test_does_not_mutate_input_dicts(self, db):
        with literature_core.get_session() as session:
            paper = Paper(title="Immutable")
            session.add(paper)
            session.flush()
            pid = paper.id

        original = {"id": pid}
        enrich_with_summaries([original])
        assert "summary" not in original


class TestSharedHelperWiring:
    """The tool modules must use the single shared implementation."""

    def test_discovery_uses_shared_helper(self):
        from mcp_server.tools import discovery
        from mcp_server.tools import _summaries

        assert discovery._enrich_with_summaries is _summaries.enrich_with_summaries
