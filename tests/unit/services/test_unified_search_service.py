"""Tests for UnifiedSearchService query preprocessing.

Covers spell correction (acronym/technical-token safety, caching) and
acronym expansion (explicit OR grouping for FTS5 recall).
"""
from __future__ import annotations

from literature_core.fts import create_fts_tables, search_fts
from literature_core.models import Paper
from services.unified_search_service import UnifiedSearchService


class TestExpandAcronyms:
    """Acronym expansion must broaden recall via explicit OR groups."""

    def test_single_acronym_expands_to_or_group(self):
        expanded, expansions = UnifiedSearchService.expand_acronyms("euv")
        assert expanded == '(EUV OR "extreme ultraviolet" OR "EUV lithography")'
        assert "EUV -> extreme ultraviolet" in expansions

    def test_acronym_with_other_words_joined_by_or(self):
        expanded, _ = UnifiedSearchService.expand_acronyms("euv resist")
        assert expanded == '(EUV OR "extreme ultraviolet" OR "EUV lithography") OR resist'

    def test_no_acronym_query_unchanged(self):
        expanded, expansions = UnifiedSearchService.expand_acronyms("zinc oxide films")
        assert expanded == "zinc oxide films"
        assert expansions == []

    def test_expanded_query_recall_not_narrowed(self, db, test_engine, test_session):
        """Expanded FTS query must match at least the papers the bare acronym matches."""
        create_fts_tables(test_engine)
        test_session.add_all([
            Paper(title="EUV photoresist development"),
            Paper(title="Advances in extreme ultraviolet lithography"),
        ])
        test_session.commit()

        plain = search_fts("euv", limit=10, engine=test_engine)
        expanded_query, _ = UnifiedSearchService.expand_acronyms("euv")
        expanded = search_fts(expanded_query, limit=10, engine=test_engine)

        assert len(expanded) >= len(plain)
        assert {r.paper_id for r in plain} <= {r.paper_id for r in expanded}


class TestCorrectSpelling:
    """Spell correction must never rewrite scientific acronyms or technical tokens."""

    def test_lowercase_acronyms_not_corrected(self, db):
        for word in ["xps", "dft", "cvd", "afm", "xrd"]:
            corrected, corrections = UnifiedSearchService.correct_spelling(word)
            assert corrected == word
            assert corrections == []

    def test_acronym_in_sentence_not_corrected(self, db):
        corrected, corrections = UnifiedSearchService.correct_spelling("dft calculations")
        assert corrected == "dft calculations"
        assert corrections == []

    def test_short_mixed_case_token_not_corrected(self, db):
        corrected, corrections = UnifiedSearchService.correct_spelling("GaAs substrate")
        assert corrected == "GaAs substrate"
        assert corrections == []

    def test_token_with_digits_not_corrected(self, db):
        corrected, corrections = UnifiedSearchService.correct_spelling("TiO2 deposition")
        assert corrected == "TiO2 deposition"
        assert corrections == []

    def test_word_in_fts_index_not_corrected(self, db, test_engine, test_session):
        """Out-of-dictionary words already present in the FTS index are domain vocabulary."""
        create_fts_tables(test_engine)
        test_session.add(Paper(title="Zincone films from molecular layer deposition"))
        test_session.commit()

        corrected, corrections = UnifiedSearchService.correct_spelling("zincone films")
        assert corrected == "zincone films"
        assert corrections == []

    def test_corrections_are_cached(self, db, monkeypatch):
        """Repeated correction of the same word must hit an LRU cache, not pyspellchecker."""

        class CountingSpell:
            def __init__(self):
                self.calls = 0

            def __contains__(self, word):
                return False

            def correction(self, word):
                self.calls += 1
                return word + "x"

        counting = CountingSpell()
        monkeypatch.setattr(UnifiedSearchService, "_spell_checker", counting)

        UnifiedSearchService.correct_spelling("blorptastic")
        UnifiedSearchService.correct_spelling("blorptastic")
        assert counting.calls == 1


class TestExpandQueryPipeline:
    """End-to-end expand_query: acronyms survive spell correction and get expanded."""

    def test_smart_expansion_preserves_and_expands_acronym(self, db):
        expansion = UnifiedSearchService.expand_query("dft calculations", add_synonyms=False)
        assert '(DFT OR "density functional theory")' in expansion.final_query
        assert expansion.spell_corrected is None
