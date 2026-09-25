"""Integration-style tests for verify_paper (DB + fake clients)."""
from __future__ import annotations

import pytest

from literature_core import PaperNotFoundError, get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from services.verification_service import VerificationService

from .test_verification_minicheck import FakeMiniCheck
from .test_verification_judge import FakeJudge

SOURCE = "Water flux reached 42.7 L/m2/h. Contact angle fell to 45.1 degrees."


@pytest.fixture
def grounded_paper(db):
    with get_session() as s:
        p = Paper(title="Test membrane paper", abstract="Flux and wetting study.")
        s.add(p)
        s.flush()
        s.add(PaperChunk(paper_id=p.id, chunk_order=1, content=SOURCE,
                         word_count=11, char_count=len(SOURCE)))
        s.add(PaperContent(
            paper_id=p.id,
            deep_one_sentence_summary="Membrane flux hit 42.7 L/m2/h with contact angle 45.1.",
            key_findings=[
                {"finding": "Flux reached 42.7 L/m2/h",
                 "quote": "Water flux reached 42.7 L/m2/h"},
                {"finding": "Contact angle fell to 45.1 degrees",
                 "quote": "Contact angle fell to 45.1 degrees"},
            ],
        ))
        s.commit()
        return p.id


class TestVerifyPaper:
    def test_clean_paper_accepts_and_persists(self, grounded_paper):
        mc = FakeMiniCheck({"Flux reached 42.7 L/m2/h": True,
                            "Contact angle fell to 45.1 degrees": True})
        result = VerificationService.verify_paper(grounded_paper, minicheck=mc)
        assert result["score"] >= 0.85 and result["routing"] == "accept"
        with get_session() as s:
            content = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            assert content.verification_score == result["score"]
            assert content.verification["routing"] == "accept"

    def test_hallucinated_number_lowers_score(self, grounded_paper):
        with get_session() as s:
            c = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            c.key_findings = [{"finding": "Flux reached 99.9 L/m2/h",
                               "quote": "Water flux reached 99.9 L/m2/h"}]
            s.commit()
        mc = FakeMiniCheck({"Flux reached 99.9 L/m2/h": False})
        result = VerificationService.verify_paper(grounded_paper, minicheck=mc)
        assert result["numeric_fidelity"] < 1.0
        assert result["routing"] in ("reextract", "review")

    def test_borderline_invokes_judge(self, grounded_paper):
        mc = FakeMiniCheck({"Flux reached 42.7 L/m2/h": True,
                            "Contact angle fell to 45.1 degrees": False})
        judge = FakeJudge([True, True, True])
        VerificationService.verify_paper(grounded_paper, minicheck=mc, judge=judge)
        assert len(judge.questions) == 3  # borderline -> judge consulted

    def test_missing_paper_raises(self, db):
        with pytest.raises(PaperNotFoundError):
            VerificationService.verify_paper(999999)


class TestVerifierUnavailable:
    """An unreachable verifier must never be recorded as a verification result."""

    def test_does_not_persist_when_verifier_is_down(self, grounded_paper):
        mc = FakeMiniCheck({})  # every call returns None, as during an Ollama outage
        result = VerificationService.verify_paper(grounded_paper, minicheck=mc)

        assert result.get("error"), "outage must surface as an error, not a score"
        assert "score" not in result
        with get_session() as s:
            content = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            assert content.verification_score is None
            assert content.verification is None

    def test_previous_good_score_is_not_overwritten_by_an_outage(self, grounded_paper):
        good = FakeMiniCheck({"Flux reached 42.7 L/m2/h": True,
                              "Contact angle fell to 45.1 degrees": True})
        first = VerificationService.verify_paper(grounded_paper, minicheck=good)

        VerificationService.verify_paper(grounded_paper, minicheck=FakeMiniCheck({}))

        with get_session() as s:
            content = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            assert content.verification_score == first["score"]
            assert content.verification["routing"] == "accept"


class TestEmptyExtraction:
    """An extraction with no summary and no findings is refused, not scored."""

    def test_empty_extraction_is_error_not_score(self, db):
        with get_session() as s:
            p = Paper(title="Empty extraction", abstract="Some abstract text.")
            s.add(p)
            s.flush()
            s.add(PaperContent(paper_id=p.id, key_findings=[]))
            s.commit()
            paper_id = p.id

        result = VerificationService.verify_paper(paper_id, minicheck=FakeMiniCheck({}))

        assert "error" in result and "audit --fix" in result["error"]
        assert "score" not in result
        assert "routing" not in result
        with get_session() as s:
            content = s.query(PaperContent).filter_by(paper_id=paper_id).first()
            assert content.verification_score is None
            assert content.verification is None
