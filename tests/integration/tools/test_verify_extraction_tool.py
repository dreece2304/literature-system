"""Integration tests for verify_extraction MCP tool queue scope."""
from __future__ import annotations

import json

import pytest

from literature_core import get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from mcp_server.tools import extraction as extraction_tools


@pytest.fixture
def scored_papers(db):
    with get_session() as s:
        for title, score, routing in [("Low paper", 0.4, "review"),
                                      ("Mid paper", 0.7, "review"),
                                      ("Good paper", 0.95, "accept")]:
            p = Paper(title=title)
            s.add(p)
            s.flush()
            s.add(PaperContent(paper_id=p.id, verification_score=score,
                               verification={"routing": routing, "failures": ["x"]}))
        s.commit()


SOURCE = "Water flux reached 42.7 L/m2/h. Contact angle fell to 45.1 degrees."


@pytest.fixture
def unverified_comprehensive_papers(db):
    """Comprehensive extractions with grounded (dict) key_findings, not yet verified."""
    ids = []
    with get_session() as s:
        for i, title in enumerate(["Batch paper A", "Batch paper B"]):
            p = Paper(title=title, abstract="Flux and wetting study.")
            s.add(p)
            s.flush()
            s.add(PaperChunk(paper_id=p.id, chunk_order=1, content=SOURCE,
                             word_count=11, char_count=len(SOURCE)))
            s.add(PaperContent(
                paper_id=p.id,
                extraction_depth="comprehensive",
                verification_score=None,
                deep_one_sentence_summary="Membrane flux hit 42.7 L/m2/h.",
                key_findings=[
                    {"finding": "Flux reached 42.7 L/m2/h",
                     "quote": "Water flux reached 42.7 L/m2/h"},
                ],
            ))
            s.commit()
            ids.append(p.id)
    return ids


@pytest.mark.asyncio
class TestVerifyQueue:
    async def test_queue_returns_low_scores_ascending(self, scored_papers):
        out = await extraction_tools.call_tool("verify_extraction", {"scope": "queue"})
        data = json.loads(out[0].text)
        titles = [p["title"] for p in data["data"]["papers"]]
        assert titles == ["Low paper", "Mid paper"]  # accept-tier paper excluded

    async def test_queue_respects_limit(self, scored_papers):
        out = await extraction_tools.call_tool("verify_extraction", {"scope": "queue", "limit": 1})
        data = json.loads(out[0].text)
        assert len(data["data"]["papers"]) == 1


@pytest.mark.asyncio
class TestVerifyBatch:
    async def test_batch_verifies_grounded_findings_and_persists_score(
        self, unverified_comprehensive_papers
    ):
        """scope=batch must route through VerificationService (grounded-schema safe)
        rather than the legacy ExtractionService.batch_verify/_find_evidence path,
        which crashes (re.findall on a dict) whenever key_findings are grounded dicts.
        """
        out = await extraction_tools.call_tool(
            "verify_extraction",
            {"scope": "batch", "paper_ids": unverified_comprehensive_papers},
        )
        data = json.loads(out[0].text)
        assert data["success"] is True
        payload = data["data"]
        assert payload["count"] == 2
        assert payload["errors"] == 0
        assert "average_score" in payload
        assert len(payload["results"]) == 2

        with get_session() as s:
            for pid in unverified_comprehensive_papers:
                content = s.query(PaperContent).filter_by(paper_id=pid).first()
                assert content.verification_score is not None

    async def test_batch_without_paper_ids_selects_unverified_comprehensive(
        self, unverified_comprehensive_papers
    ):
        out = await extraction_tools.call_tool("verify_extraction", {"scope": "batch"})
        data = json.loads(out[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 2
