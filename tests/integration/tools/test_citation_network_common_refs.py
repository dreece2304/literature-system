"""Regression tests for find_common_references using local citation data.

Audit finding: _find_common_references made up to ~100 sequential rate-limited
Semantic Scholar calls per invocation (one pair per library paper) while
ignoring the local, indexed paper_references table. It must answer from
paper_references first and consult the external API at most once (for the
source paper's own references, only when no local ones exist).
"""
import json
from types import SimpleNamespace

import pytest

from mcp_server.tools import citation_network
from services import PaperService
from services.external_search import ExternalSearchService
from literature_core import PaperReference


def _add_reference(db, paper_id: int, order: int, doi: str | None):
    with db.get_session() as session:
        session.add(PaperReference(
            paper_id=paper_id,
            reference_order=order,
            raw_text=f"Reference {order} of paper {paper_id}",
            parsed_doi=doi,
        ))


def _result_data(response) -> dict:
    payload = json.loads(response[0].text)
    assert payload.get("success") is True, payload
    return payload["data"]


@pytest.fixture
def external_refs_mock(monkeypatch):
    """Patch ExternalSearchService.get_paper_references, counting calls."""
    state = {"calls": 0, "return_value": []}

    async def fake_get_paper_references(self, doi=None, title=None, limit=100):
        state["calls"] += 1
        return state["return_value"]

    monkeypatch.setattr(
        ExternalSearchService, "get_paper_references", fake_get_paper_references
    )
    return state


class TestFindCommonReferencesLocalFirst:
    async def test_local_references_answer_without_external_calls(
        self, db, external_refs_mock
    ):
        source = PaperService.create(title="Source paper", doi="10.1000/source")
        strong = PaperService.create(title="Strongly related", doi="10.1000/strong")
        weak = PaperService.create(title="Weakly related", doi="10.1000/weak")

        for i, ref_doi in enumerate(["10.1/aaa", "10.1/bbb", "10.1/ccc"]):
            _add_reference(db, source["id"], i, ref_doi)
        _add_reference(db, strong["id"], 0, "10.1/aaa")
        _add_reference(db, strong["id"], 1, "10.1/bbb")
        _add_reference(db, weak["id"], 0, "10.1/aaa")

        response = await citation_network._find_common_references(
            {"paper_id": source["id"], "min_shared": 2}
        )
        data = _result_data(response)

        assert external_refs_mock["calls"] == 0, (
            "Local reference data must be used without any external API calls"
        )
        assert data["reference_source"] == "local"
        assert data["source_reference_count"] == 3
        assert data["related_paper_count"] == 1
        assert len(data["related_papers"]) == 1
        related = data["related_papers"][0]
        assert related["id"] == strong["id"]
        assert related["shared_references"] == 2
        assert sorted(related["shared_dois"]) == ["10.1/aaa", "10.1/bbb"]

    async def test_doi_prefix_and_case_normalized(self, db, external_refs_mock):
        source = PaperService.create(title="Source paper")
        other = PaperService.create(title="Other paper")

        _add_reference(db, source["id"], 0, "10.1/AAA")
        _add_reference(db, source["id"], 1, "doi:10.1/bbb")
        _add_reference(db, other["id"], 0, "https://doi.org/10.1/aaa")
        _add_reference(db, other["id"], 1, "10.1/BBB")

        response = await citation_network._find_common_references(
            {"paper_id": source["id"], "min_shared": 2}
        )
        data = _result_data(response)

        assert external_refs_mock["calls"] == 0
        assert data["related_paper_count"] == 1
        assert data["related_papers"][0]["id"] == other["id"]
        assert data["related_papers"][0]["shared_references"] == 2

    async def test_external_fallback_makes_single_call(self, db, external_refs_mock):
        # Source paper has NO local references -> one external lookup allowed.
        source = PaperService.create(title="Source paper", doi="10.1000/source")
        # Library papers with DOIs: the old implementation looped over these
        # with one external call each.
        related = PaperService.create(title="Related paper", doi="10.1000/related")
        other = PaperService.create(title="Other paper", doi="10.1000/other")

        _add_reference(db, related["id"], 0, "10.1/aaa")
        _add_reference(db, related["id"], 1, "10.1/bbb")
        _add_reference(db, other["id"], 0, "10.1/zzz")

        external_refs_mock["return_value"] = [
            SimpleNamespace(doi="10.1/aaa"),
            SimpleNamespace(doi="10.1/bbb"),
            SimpleNamespace(doi=None),
        ]

        response = await citation_network._find_common_references(
            {"paper_id": source["id"], "min_shared": 2}
        )
        data = _result_data(response)

        assert external_refs_mock["calls"] == 1, (
            f"Expected a single external call for the source paper, got {external_refs_mock['calls']}"
        )
        assert data["reference_source"] == "external"
        assert data["source_reference_count"] == 3
        assert data["related_paper_count"] == 1
        assert data["related_papers"][0]["id"] == related["id"]

    async def test_no_references_anywhere_returns_message(self, db, external_refs_mock):
        source = PaperService.create(title="Lonely paper", doi="10.1000/lonely")

        response = await citation_network._find_common_references(
            {"paper_id": source["id"]}
        )
        data = _result_data(response)

        assert external_refs_mock["calls"] == 1
        assert data["related_papers"] == []
        assert "message" in data

    async def test_missing_paper_returns_error(self, db, external_refs_mock):
        # Via call_tool so PaperNotFoundError is converted to an error response
        response = await citation_network.call_tool(
            "find_common_references", {"paper_id": 999999}
        )
        payload = json.loads(response[0].text)
        assert payload.get("success") is False
        assert external_refs_mock["calls"] == 0
