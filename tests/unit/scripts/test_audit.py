"""Tests for scripts.audit: check collection, --fix repairs, and the outage clear."""
from __future__ import annotations

import pytest

from literature_core import get_session
from literature_core.fts import create_fts_tables
from literature_core.models import Paper, PaperContent
from scripts.audit import OUTAGE_KEY, run_audit

# Signature of a verification written while the NLI verifier was unreachable:
# every claim came back `supported: None`.
OUTAGE_BLOB = {
    "score": 0.4,
    "routing": "review",
    "evidence": {"claims": [{"claim": "c1", "supported": None},
                            {"claim": "c2", "supported": None}]},
}
REAL_BLOB = {
    "score": 0.9,
    "routing": "accept",
    "evidence": {"claims": [{"claim": "c1", "supported": True}]},
}


@pytest.fixture
def audit_db(db):
    # fts_drift queries papers_fts, which Base.metadata.create_all does not create.
    create_fts_tables(db.engine)
    return db


def _finding(report, key):
    return next(f for f in report.findings if f.key == key)


def _paper_with_content(s, title, **content):
    p = Paper(title=title)
    s.add(p)
    s.flush()
    s.add(PaperContent(paper_id=p.id, **content))
    return p.id


class TestCleanDatabase:
    def test_all_checks_pass_on_empty_db(self, audit_db):
        report = run_audit()
        assert report.fixed == {}
        assert all(f.count == 0 for f in report.findings)
        keys = {f.key for f in report.findings}
        assert {"empty_extraction_marked_complete", OUTAGE_KEY,
                "missing_pdf_on_disk", "fts_drift"} <= keys

    def test_fix_on_clean_db_repairs_nothing(self, audit_db):
        report = run_audit(fix=True)
        assert report.fixed == {}
        assert all(f.count == 0 for f in report.findings)


class TestSilentFailures:
    def test_empty_comprehensive_extraction_is_flagged_and_requeued(self, audit_db):
        with get_session() as s:
            empty = _paper_with_content(s, "Empty", extraction_depth="comprehensive",
                                        key_findings=[])
            _paper_with_content(s, "Healthy", extraction_depth="comprehensive",
                                deep_one_sentence_summary="ok", key_findings=[])
            s.commit()

        before = _finding(run_audit(), "empty_extraction_marked_complete")
        assert before.count == 1
        assert before.samples == [empty]
        assert before.fixable

        report = run_audit(fix=True)
        assert report.fixed["empty_extraction_marked_complete"] == 1
        assert _finding(report, "empty_extraction_marked_complete").count == 0
        with get_session() as s:
            row = s.query(PaperContent).filter_by(paper_id=empty).one()
            assert row.extraction_depth is None
            healthy = s.query(PaperContent).filter(PaperContent.paper_id != empty).one()
            assert healthy.extraction_depth == "comprehensive"


class TestOutageFix:
    def test_fix_clears_more_than_ten_outage_rows(self, audit_db):
        """Regression: --fix must clear every victim, not just the 10 display samples."""
        with get_session() as s:
            victims = [
                _paper_with_content(s, f"Victim {i}", verification=OUTAGE_BLOB,
                                    verification_score=0.4, deep_one_sentence_summary="s")
                for i in range(12)
            ]
            real = _paper_with_content(s, "Real", verification=REAL_BLOB,
                                       verification_score=0.9, deep_one_sentence_summary="s")
            s.commit()

        before = _finding(run_audit(), OUTAGE_KEY)
        assert before.count == 12
        assert len(before.samples) == 10
        assert before.fixable

        report = run_audit(fix=True)
        assert report.fixed[OUTAGE_KEY] == 12
        assert _finding(report, OUTAGE_KEY).count == 0
        with get_session() as s:
            for pid in victims:
                row = s.query(PaperContent).filter_by(paper_id=pid).one()
                assert row.verification is None and row.verification_score is None
            kept = s.query(PaperContent).filter_by(paper_id=real).one()
            assert kept.verification_score == 0.9
            assert kept.verification == REAL_BLOB
