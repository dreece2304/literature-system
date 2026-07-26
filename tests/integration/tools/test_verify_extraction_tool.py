"""Integration tests for verify_extraction MCP tool queue scope."""
from __future__ import annotations

import json

import pytest

from literature_core import get_session
from literature_core.models import Paper, PaperContent
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
