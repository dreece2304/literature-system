"""Integration tests for the papers MCP tool module.

Covers audit findings:
- store_extraction must persist deep-extraction fields (is_quick derivation)
- update_paper with file_path must queue the paper for chunking
  (ExtractionMetadata PENDING row), matching PaperService.update behavior
"""
from __future__ import annotations

import json

import pytest

from literature_core import ChunkingStatus, ExtractionMetadata
from services import PaperService


def _parse(response) -> dict:
    """Parse the JSON payload from a tool handler response."""
    return json.loads(response[0].text)


class TestStoreExtractionTool:
    """Tests for the store_extraction tool's is_quick handling."""

    def test_deep_fields_are_persisted(self, db):
        """Calling store_extraction with deep fields must store them as a
        deep extraction, not silently drop them via the quick branch."""
        from mcp_server.tools.papers import _store_extraction

        paper = PaperService.create(title="Deep extraction target")

        response = _parse(_store_extraction({
            "paper_id": paper["id"],
            "paper_type": "research_article",
            "topics": ["ALD", "zinc oxide"],
            "one_sentence_summary": "A deep summary.",
            "key_findings": ["Finding one", "Finding two"],
            "methodology_summary": "In-situ QCM during ALD.",
            "quantitative_results": [{"metric": "GPC", "value": "1.2 A/cycle"}],
        }))
        assert response["success"] is True

        content = PaperService.get_content(paper["id"])
        assert content["extraction"]["key_findings"] == ["Finding one", "Finding two"]
        assert content["extraction"]["methodology_summary"] == "In-situ QCM during ALD."
        assert content["extraction"]["quantitative_results"] == [
            {"metric": "GPC", "value": "1.2 A/cycle"}
        ]
        assert content["extraction_tier"] == "deep"
        assert response["data"]["extraction_tier"] == "deep"

    def test_quick_only_fields_stored_as_quick(self, db):
        """Without any deep field, the extraction must remain a quick one."""
        from mcp_server.tools.papers import _store_extraction

        paper = PaperService.create(title="Quick extraction target")

        response = _parse(_store_extraction({
            "paper_id": paper["id"],
            "paper_type": "review",
            "topics": ["EUV"],
            "one_sentence_summary": "A quick summary.",
        }))
        assert response["success"] is True
        assert response["data"]["extraction_tier"] == "quick"
        assert "extended_fields_stored" not in response["data"]

        content = PaperService.get_content(paper["id"])
        assert content["extraction_tier"] == "quick"
        assert content["extraction"]["paper_type"] == "review"

    def test_response_reports_extended_fields_only_when_present(self, db):
        """extended_fields_stored must list exactly the persisted extended fields."""
        from mcp_server.tools.papers import _store_extraction

        paper = PaperService.create(title="Extended fields target")

        response = _parse(_store_extraction({
            "paper_id": paper["id"],
            "key_findings": ["Only finding"],
            "citable_claims": [{"claim": "X improves Y"}],
        }))
        assert response["data"]["extended_fields_stored"] == ["citable_claims"]
        assert response["data"]["extraction_tier"] == "deep"

        content = PaperService.get_content(paper["id"])
        assert content["extraction"]["key_findings"] == ["Only finding"]
        assert content["extraction"]["citable_claims"] == [{"claim": "X improves Y"}]


class TestUpdatePaperPDFQueueing:
    """Tests that update_paper(file_path=...) queues chunking."""

    @pytest.fixture
    def fake_pdf(self, tmp_path):
        """A minimal file with a %PDF header (content extraction may fail,
        which link_local_pdf tolerates)."""
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")
        return pdf

    @pytest.fixture
    def patched_extraction_session(self, db, monkeypatch):
        """Route extraction_service's module-level get_session to the test DB."""
        import services.extraction_service as extraction_service
        monkeypatch.setattr(extraction_service, "get_session", db.get_session)
        return db

    def test_update_paper_with_file_path_creates_pending_queue_entry(
        self, patched_extraction_session, fake_pdf
    ):
        """Attaching a PDF via the update_paper tool must create an
        ExtractionMetadata row with chunking_status=PENDING, exactly like
        PaperService.update's file_path branch does."""
        from mcp_server.tools.papers import _update_paper

        db = patched_extraction_session
        paper = PaperService.create(title="PDF queue target")

        response = _parse(_update_paper({
            "paper_id": paper["id"],
            "file_path": str(fake_pdf),
        }))
        assert response["success"] is True
        assert response["data"]["file_path"] == str(fake_pdf.resolve())

        with db.get_session() as session:
            metadata = (
                session.query(ExtractionMetadata)
                .filter(ExtractionMetadata.paper_id == paper["id"])
                .first()
            )
            assert metadata is not None, (
                "update_paper attached a PDF but never queued it for chunking "
                "(no ExtractionMetadata row)"
            )
            assert metadata.chunking_status == ChunkingStatus.PENDING

    def test_update_paper_without_file_path_does_not_queue(
        self, patched_extraction_session
    ):
        """A plain metadata update must not enqueue anything."""
        from mcp_server.tools.papers import _update_paper

        db = patched_extraction_session
        paper = PaperService.create(title="No PDF here")

        response = _parse(_update_paper({
            "paper_id": paper["id"],
            "rating": 4,
        }))
        assert response["success"] is True

        with db.get_session() as session:
            metadata = (
                session.query(ExtractionMetadata)
                .filter(ExtractionMetadata.paper_id == paper["id"])
                .first()
            )
            assert metadata is None
