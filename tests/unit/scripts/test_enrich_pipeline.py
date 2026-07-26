"""Tests for enrich_pipeline stage planning and arg handling."""
from __future__ import annotations

from literature_core import get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from scripts.enrich_pipeline import parse_args, plan_backfill, plan_extract, plan_verify


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
