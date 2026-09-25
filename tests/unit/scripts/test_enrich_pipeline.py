"""Tests for enrich_pipeline stage planning and arg handling."""
from __future__ import annotations

from unittest.mock import patch

import httpx

import embeddings.vectorstore as vectorstore_module
import services.embedding_service as embedding_service_module
from literature_core import get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from scripts.enrich_pipeline import (
    parse_args, plan_backfill, plan_embed, plan_extract, plan_verify, preflight,
)
from services.verification_service import JudgeClient, MiniCheckClient

from tests.unit.services.test_embedding_service_status import FakeChunkStore, FakePaperStore


def _paper(s, title, file_path=None, chunked=False, depth=None, vscore=None):
    p = Paper(title=title, file_path=file_path)
    s.add(p)
    s.flush()
    if chunked:
        s.add(PaperChunk(paper_id=p.id, chunk_order=1, content="text",
                         word_count=1, char_count=4))
    if depth is not None or vscore is not None:
        s.add(PaperContent(paper_id=p.id, extraction_depth=depth,
                           verification_score=vscore))
    return p.id


class TestPlanning:
    def test_backfill_finds_pdf_without_chunks(self, db):
        with get_session() as s:
            stuck = _paper(s, "Stuck", file_path="/x/a.pdf", chunked=False)
            _paper(s, "Fine", file_path="/x/b.pdf", chunked=True)
            _paper(s, "NoPdf", file_path=None)
            s.commit()
            assert plan_backfill(s) == [stuck]

    def test_extract_finds_chunked_not_comprehensive(self, db):
        with get_session() as s:
            todo = _paper(s, "Abstract only", file_path="/x/a.pdf", chunked=True,
                          depth="abstract_only")
            _paper(s, "Done", file_path="/x/b.pdf", chunked=True, depth="comprehensive")
            s.commit()
            assert plan_extract(s, limit=10) == [todo]

    def test_verify_finds_unscored_comprehensive(self, db):
        with get_session() as s:
            todo = _paper(s, "Unscored", chunked=True, depth="comprehensive", vscore=None)
            _paper(s, "Scored", chunked=True, depth="comprehensive", vscore=0.9)
            s.commit()
            assert plan_verify(s, limit=10) == [todo]


class TestArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.stage == "all" and args.dry_run is False and args.limit is None

    def test_paper_ids_parsed(self):
        args = parse_args(["--stage", "verify", "--paper-ids", "3,5,8"])
        assert args.paper_ids == [3, 5, 8]


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200


class _FakeHttpxClient:
    """Stands in for httpx.Client; every GET returns the configured tags text."""

    tags_text = ""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return _FakeResponse(self.tags_text)


class TestPreflight:
    def test_non_llm_stages_skip_ollama_entirely(self):
        with patch.object(MiniCheckClient, "is_available", side_effect=AssertionError("must not be called")):
            assert preflight("backfill") is None
            assert preflight("embed") is None

    def test_unreachable_ollama_returns_actionable_error(self):
        with patch.object(MiniCheckClient, "is_available", return_value=False):
            msg = preflight("extract")
        assert msg is not None
        assert "unavailable" in msg and "ollama serve" in msg

    def test_verify_requires_judge_model(self, monkeypatch):
        # Verifier reachable, but the judge model is absent from /api/tags.
        _FakeHttpxClient.tags_text = '{"models": [{"name": "some-other-model:latest"}]}'
        monkeypatch.setattr(httpx, "Client", _FakeHttpxClient)
        with patch.object(MiniCheckClient, "is_available", return_value=True):
            msg = preflight("verify")
        assert msg is not None and "ollama pull" in msg

    def test_verify_passes_when_both_models_present(self, monkeypatch):
        _FakeHttpxClient.tags_text = JudgeClient().model
        monkeypatch.setattr(httpx, "Client", _FakeHttpxClient)
        with patch.object(MiniCheckClient, "is_available", return_value=True):
            assert preflight("verify") is None


class TestPlanEmbed:
    def _seed(self, db, monkeypatch):
        monkeypatch.setattr(embedding_service_module, "get_session", db.get_session)
        with db.get_session() as s:
            ps = [Paper(title=f"Paper {i}", abstract=f"abstract {i}") for i in range(3)]
            s.add_all(ps)
            s.flush()
            ids = [p.id for p in ps]
            s.add_all([PaperChunk(paper_id=pid, chunk_order=0, content="chunk") for pid in ids])
        p1, p2, p3 = ids
        # p1 fully embedded; p2 has chunk vectors but no paper vector; p3 has nothing.
        monkeypatch.setattr(vectorstore_module, "get_vector_store",
                            lambda: FakePaperStore([str(p1)]))
        monkeypatch.setattr(vectorstore_module, "get_chunk_store",
                            lambda: FakeChunkStore([f"{p1}_0", f"{p2}_0"]))
        return p1, p2, p3

    def test_selects_papers_missing_paper_or_chunk_vectors(self, db, monkeypatch):
        p1, p2, p3 = self._seed(db, monkeypatch)
        with db.get_session() as s:
            assert plan_embed(s, None) == sorted([p2, p3])

    def test_limit_is_honoured(self, db, monkeypatch):
        p1, p2, p3 = self._seed(db, monkeypatch)
        with db.get_session() as s:
            assert plan_embed(s, 1) == [min(p2, p3)]
