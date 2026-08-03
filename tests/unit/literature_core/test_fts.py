"""Tests for FTS5 search query handling (operator detection and OR-conversion)."""
from __future__ import annotations

import pytest

from literature_core.fts import create_fts_tables, search_fts
from literature_core.models import Paper


@pytest.fixture
def fts_engine(test_engine, test_session):
    """Test engine with FTS5 tables and a small paper corpus."""
    create_fts_tables(test_engine)
    test_session.add_all([
        Paper(title="Stress corrosion mechanisms in stainless steel"),
        Paper(title="Fatigue cracking of aluminum alloys"),
        Paper(title="ALD of zinc oxide thin films"),
        Paper(title="MLD hybrid films for barrier coatings"),
        Paper(title="Atomic layer deposition of alumina"),
        Paper(title="Assembly of layer stacks on atomic templates"),
    ])
    test_session.commit()
    return test_engine


class TestSearchFtsOperatorDetection:
    """OR-conversion must only be disabled by whole-token FTS5 operators."""

    def test_operator_substring_words_still_or_converted(self, fts_engine):
        """'corrosion' contains 'OR' but is not an operator: query must be OR-joined."""
        results = search_fts("corrosion cracking", limit=10, engine=fts_engine)
        # OR semantics: one paper matches 'corrosion', another matches 'cracking'
        assert len(results) == 2

    def test_explicit_or_operator_preserved(self, fts_engine):
        """Whole-token OR must be passed through verbatim."""
        results = search_fts("ald OR mld", limit=10, engine=fts_engine)
        assert len(results) == 2

    def test_explicit_and_operator_preserved(self, fts_engine):
        """Whole-token AND must stay strict AND (no paper has both terms)."""
        results = search_fts("corrosion AND cracking", limit=10, engine=fts_engine)
        assert results == []

    def test_quoted_phrase_not_or_converted(self, fts_engine):
        """Quoted phrases must stay phrase queries (adjacency required)."""
        results = search_fts('"atomic layer"', limit=10, engine=fts_engine)
        # Only 'Atomic layer deposition of alumina' has the words adjacent
        assert len(results) == 1
