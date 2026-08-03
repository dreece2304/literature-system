"""Regression tests for N+1 lazy loads in SearchService entity searches.

Audit finding: search_by_author, search_by_tag, the keyword LIKE fallback,
and search_by_doi queried Paper without joinedload, so paper_to_result's
access to paper.authors / paper.tags issued two lazy-load SELECTs per result
row. These tests count executed SELECT statements via a SQLAlchemy event
listener and assert the query count does not scale with the result count.
"""
import pytest
from sqlalchemy import event

from services import PaperService
from services.search_service import SearchService


class QueryCounter:
    """Counts SELECT statements executed on an engine within a block."""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        event.remove(self.engine, "before_cursor_execute", self._record)
        return False


@pytest.fixture
def papers_with_relations(db):
    """Three papers, each with two authors and two tags."""
    created = []
    for i in range(3):
        created.append(PaperService.create(
            title=f"Zinc oxide deposition study {i}",
            abstract=f"Abstract text for paper {i} about zinc oxide.",
            year=2020 + i,
            doi=f"10.1000/test.{i}",
            authors=["Alice Smith", f"Bob Jones {i}"],
            tags=["ald", "zinc-oxide"],
        ))
    return created


class TestSearchByAuthorEagerLoading:
    def test_no_n_plus_one_queries(self, db, papers_with_relations):
        with QueryCounter(db.engine) as counter:
            results = SearchService.search_by_author("Smith", limit=10)

        assert results.count == 3
        # Authors and tags must still be populated in results
        assert all(r["authors"] for r in results.results)
        assert all(r["tags"] for r in results.results)
        # Eager loading: a single query (small fixed bound), not 1 + 2 per row
        assert len(counter.statements) <= 2, (
            f"Expected eager-loaded query, got {len(counter.statements)} SELECTs"
        )


class TestSearchByTagEagerLoading:
    def test_no_n_plus_one_queries(self, db, papers_with_relations):
        with QueryCounter(db.engine) as counter:
            results = SearchService.search_by_tag("ald", limit=10)

        assert results.count == 3
        assert all(r["authors"] for r in results.results)
        assert all(r["tags"] for r in results.results)
        assert len(counter.statements) <= 2, (
            f"Expected eager-loaded query, got {len(counter.statements)} SELECTs"
        )

    def test_exact_match_no_n_plus_one(self, db, papers_with_relations):
        with QueryCounter(db.engine) as counter:
            results = SearchService.search_by_tag("ald", limit=10, exact_match=True)

        assert results.count == 3
        assert len(counter.statements) <= 2


class TestKeywordLikeFallbackEagerLoading:
    def test_no_n_plus_one_queries(self, db, papers_with_relations):
        # Test DB has no papers_fts table, so keyword_search uses the LIKE
        # fallback (one extra SELECT probes sqlite_master for FTS availability).
        with QueryCounter(db.engine) as counter:
            results = SearchService.keyword_search("zinc oxide", limit=10)

        assert results.search_type == "keyword_like"
        assert results.count == 3
        assert all(r["authors"] for r in results.results)
        assert len(counter.statements) <= 3, (
            f"Expected FTS probe + one eager query, got {len(counter.statements)} SELECTs"
        )


class TestSearchByDoiEagerLoading:
    def test_no_lazy_loads(self, db, papers_with_relations):
        with QueryCounter(db.engine) as counter:
            result = SearchService.search_by_doi("10.1000/test.0")

        assert result is not None
        assert result["authors"]
        assert result["tags"]
        assert len(counter.statements) <= 2, (
            f"Expected single eager-loaded query, got {len(counter.statements)} SELECTs"
        )
