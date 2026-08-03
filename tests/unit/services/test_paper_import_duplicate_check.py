"""Regression tests for the fuzzy duplicate-title check in PaperImportService.

Audit finding: _check_duplicates loaded 1,000 full Paper ORM rows (including
abstracts) per imported paper just to compare titles. It must query only the
(id, title) columns, narrowed by a title-length window that cannot exclude
any candidate above the similarity threshold.
"""
import pytest
from sqlalchemy import event

import services.paper_import_service as paper_import_module
from services.paper_import_service import PaperImportService
from literature_core import Paper


@pytest.fixture
def import_db(db, monkeypatch):
    """db fixture with paper_import_service's get_session patched to the test DB."""
    monkeypatch.setattr(paper_import_module, "get_session", db.get_session)
    return db


def _add_paper(import_db, title: str, abstract: str | None = None, doi: str | None = None):
    with import_db.get_session() as session:
        paper = Paper(title=title, abstract=abstract, doi=doi)
        session.add(paper)
        session.flush()
        return paper.id


class TestFuzzyDuplicateBehavior:
    def test_near_identical_title_detected(self, import_db):
        existing_id = _add_paper(
            import_db,
            "Atomic Layer Deposition of Zinc Oxide Thin Films",
            abstract="A very long abstract " * 50,
        )

        check = PaperImportService._check_duplicates(
            doi=None,
            arxiv_id=None,
            title="Atomic layer deposition of zinc oxide thin films",
        )

        assert check.is_duplicate is True
        assert check.match_type == "title_similarity"
        assert check.existing_paper_id == existing_id
        assert check.existing_paper_title == "Atomic Layer Deposition of Zinc Oxide Thin Films"
        assert check.similarity is not None

    def test_different_title_not_flagged(self, import_db):
        _add_paper(import_db, "Atomic Layer Deposition of Zinc Oxide Thin Films")

        check = PaperImportService._check_duplicates(
            doi=None,
            arxiv_id=None,
            title="Extreme Ultraviolet Lithography Resist Chemistry",
        )

        assert check.is_duplicate is False

    def test_doi_match_still_detected(self, import_db):
        existing_id = _add_paper(import_db, "Some Paper", doi="10.1000/dup")

        check = PaperImportService._check_duplicates(
            doi="10.1000/dup",
            arxiv_id=None,
            title="Completely different title",
        )

        assert check.is_duplicate is True
        assert check.match_type == "doi"
        assert check.existing_paper_id == existing_id


class TestFuzzyDuplicateQueryShape:
    def test_fuzzy_pass_does_not_load_abstract_column(self, import_db):
        """The title-similarity query must select only id + title, not full rows."""
        _add_paper(
            import_db,
            "Atomic Layer Deposition of Zinc Oxide Thin Films",
            abstract="Large abstract payload " * 100,
        )

        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(import_db.engine, "before_cursor_execute", record)
        try:
            # doi/arxiv are None so only the fuzzy-title query runs
            PaperImportService._check_duplicates(
                doi=None,
                arxiv_id=None,
                title="Atomic Layer Deposition of Zinc Oxide Films",
            )
        finally:
            event.remove(import_db.engine, "before_cursor_execute", record)

        assert statements, "Expected the fuzzy-title SELECT to run"
        for stmt in statements:
            assert "abstract" not in stmt.lower(), (
                f"Fuzzy duplicate check should not fetch full rows: {stmt}"
            )

    def test_length_window_never_excludes_true_duplicates(self, import_db):
        """Titles above the similarity threshold always fall inside the window.

        SequenceMatcher.ratio() <= 2*min(l1,l2)/(l1+l2), so a candidate whose
        length is outside [t/(2-t), (2-t)/t] * len(title) can never match.
        A title identical except for a short suffix must still be caught.
        """
        existing_id = _add_paper(
            import_db,
            "Diethylzinc mercaptophenol hybrid resist densification",
        )

        check = PaperImportService._check_duplicates(
            doi=None,
            arxiv_id=None,
            title="Diethylzinc mercaptophenol hybrid resist densification.",
        )

        assert check.is_duplicate is True
        assert check.existing_paper_id == existing_id
