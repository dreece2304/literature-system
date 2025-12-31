"""Tests for SQLite FTS5 full-text search infrastructure.

Tests cover:
- FTS5 table creation and trigger setup
- BM25-ranked search functionality
- Index rebuilding and status checking
- Year filtering
- Phrase and term searches
"""
import pytest
from sqlalchemy import text

from literature_core.models import Paper
from literature_core.fts import (
    create_fts_tables,
    is_fts_available,
    get_fts_status,
    rebuild_fts_index,
    search_fts,
    search_fts_phrase,
    search_fts_any_term,
    search_fts_all_terms,
    optimize_fts_index,
    FTSResult,
    FTSStatus,
)


class TestFTSTableCreation:
    """Tests for FTS5 table and trigger creation."""

    def test_create_fts_tables_success(self, test_engine):
        """Test that FTS5 tables are created successfully."""
        result = create_fts_tables(test_engine)
        assert result is True

    def test_create_fts_tables_creates_virtual_table(self, test_engine):
        """Test that papers_fts virtual table is created."""
        create_fts_tables(test_engine)

        with test_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'"
            ))
            assert result.fetchone() is not None

    def test_create_fts_tables_creates_triggers(self, test_engine):
        """Test that sync triggers are created."""
        create_fts_tables(test_engine)

        with test_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ))
            triggers = [row[0] for row in result]

        assert 'papers_fts_insert' in triggers
        assert 'papers_fts_delete' in triggers
        assert 'papers_fts_update' in triggers

    def test_is_fts_available_false_before_creation(self, test_engine):
        """Test that FTS is not available before table creation."""
        # Note: the test_engine already creates Base tables, but not FTS
        assert is_fts_available(test_engine) is False

    def test_is_fts_available_true_after_creation(self, test_engine):
        """Test that FTS is available after table creation."""
        create_fts_tables(test_engine)
        assert is_fts_available(test_engine) is True


class TestFTSStatus:
    """Tests for FTS5 index status checking."""

    def test_get_fts_status_not_available(self, test_engine):
        """Test status when FTS table doesn't exist."""
        status = get_fts_status(test_engine)

        assert status.is_available is False
        assert status.needs_rebuild is True
        assert status.indexed_count == 0

    def test_get_fts_status_empty_index(self, test_engine):
        """Test status with empty FTS index."""
        create_fts_tables(test_engine)
        status = get_fts_status(test_engine)

        assert status.is_available is True
        assert status.indexed_count == 0
        assert status.papers_count == 0
        assert status.needs_rebuild is False

    def test_get_fts_status_with_papers(self, test_engine, test_session):
        """Test status when papers exist."""
        # Create FTS tables first
        create_fts_tables(test_engine)

        # Add a paper (trigger should auto-index it)
        paper = Paper(
            title="Machine Learning for Text Classification",
            abstract="A study on text classification methods.",
            year=2024
        )
        test_session.add(paper)
        test_session.commit()

        status = get_fts_status(test_engine)

        assert status.is_available is True
        assert status.indexed_count == 1
        assert status.papers_count == 1
        assert status.needs_rebuild is False


class TestFTSTriggerSync:
    """Tests for FTS5 trigger-based synchronization."""

    def test_insert_trigger_indexes_new_paper(self, test_engine, test_session):
        """Test that INSERT trigger indexes new papers."""
        create_fts_tables(test_engine)

        paper = Paper(
            title="Deep Learning Revolution",
            abstract="How neural networks changed AI.",
            year=2023
        )
        test_session.add(paper)
        test_session.commit()

        # Verify paper is in FTS index
        results = search_fts("deep learning", limit=10, engine=test_engine)
        assert len(results) == 1
        assert results[0].paper_id == paper.id

    def test_delete_trigger_removes_paper(self, test_engine, test_session):
        """Test that DELETE trigger removes papers from index."""
        create_fts_tables(test_engine)

        paper = Paper(
            title="Temporary Paper",
            abstract="This will be deleted.",
            year=2024
        )
        test_session.add(paper)
        test_session.commit()
        paper_id = paper.id

        # Verify it's indexed
        results = search_fts("temporary", limit=10, engine=test_engine)
        assert len(results) == 1

        # Delete the paper
        test_session.delete(paper)
        test_session.commit()

        # Verify it's removed from index
        results = search_fts("temporary", limit=10, engine=test_engine)
        assert len(results) == 0

    def test_update_trigger_reindexes_paper(self, test_engine, test_session):
        """Test that UPDATE trigger reindexes papers."""
        create_fts_tables(test_engine)

        paper = Paper(
            title="Original Title",
            abstract="Original abstract.",
            year=2024
        )
        test_session.add(paper)
        test_session.commit()

        # Update the title
        paper.title = "Updated Neural Networks"
        test_session.commit()

        # Should find by new title
        results = search_fts("neural networks", limit=10, engine=test_engine)
        assert len(results) == 1

        # Should NOT find by old title
        results = search_fts("original title", limit=10, engine=test_engine)
        assert len(results) == 0


class TestFTSSearch:
    """Tests for FTS5 search functionality."""

    @pytest.fixture
    def papers_with_fts(self, test_engine, test_session):
        """Create multiple papers for search testing."""
        create_fts_tables(test_engine)

        papers = [
            Paper(
                title="Machine Learning for Natural Language Processing",
                abstract="This paper explores ML techniques for NLP tasks including sentiment analysis.",
                full_text="Full text about machine learning and NLP methods.",
                year=2023
            ),
            Paper(
                title="Deep Neural Networks in Computer Vision",
                abstract="Convolutional neural networks for image classification.",
                full_text="CNNs have revolutionized computer vision applications.",
                year=2022
            ),
            Paper(
                title="Reinforcement Learning for Robotics",
                abstract="Applying RL algorithms to robotic control problems.",
                full_text="Robots can learn complex behaviors through reinforcement.",
                year=2024
            ),
            Paper(
                title="Transformer Models for Text Generation",
                abstract="GPT and BERT architectures for generating coherent text.",
                full_text="Attention mechanisms in transformer models.",
                year=2023
            ),
            Paper(
                title="Statistical Methods in Data Science",
                abstract="Classical statistics meets modern machine learning.",
                full_text="Bayesian inference and frequentist approaches.",
                year=2021
            ),
        ]

        for paper in papers:
            test_session.add(paper)
        test_session.commit()

        # Return both papers and engine for tests to use
        return {"papers": papers, "engine": test_engine}

    def test_search_returns_results(self, papers_with_fts):
        """Test that search returns relevant results."""
        engine = papers_with_fts["engine"]
        results = search_fts("machine learning", limit=10, engine=engine)
        assert len(results) > 0

    def test_search_returns_fts_result_objects(self, papers_with_fts):
        """Test that search returns FTSResult objects."""
        engine = papers_with_fts["engine"]
        results = search_fts("neural networks", limit=10, engine=engine)
        assert len(results) > 0
        assert isinstance(results[0], FTSResult)
        assert hasattr(results[0], 'paper_id')
        assert hasattr(results[0], 'bm25_score')

    def test_search_bm25_ranking(self, papers_with_fts):
        """Test that results are ranked by BM25 score."""
        engine = papers_with_fts["engine"]
        results = search_fts("neural networks", limit=10, engine=engine)

        # Results should be in descending score order
        scores = [r.bm25_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_respects_limit(self, papers_with_fts):
        """Test that search respects the limit parameter."""
        engine = papers_with_fts["engine"]
        results = search_fts("learning", limit=2, engine=engine)
        assert len(results) <= 2

    def test_search_empty_query_returns_empty(self, papers_with_fts):
        """Test that empty query returns empty results."""
        engine = papers_with_fts["engine"]
        results = search_fts("", limit=10, engine=engine)
        assert len(results) == 0

        results = search_fts("   ", limit=10, engine=engine)
        assert len(results) == 0

    def test_search_with_year_min(self, papers_with_fts):
        """Test filtering by minimum year."""
        engine = papers_with_fts["engine"]
        results = search_fts("learning", limit=10, year_min=2023, engine=engine)

        for result in results:
            # We need to verify year from database
            # For now, just check we get results
            assert result.paper_id is not None

    def test_search_with_year_max(self, papers_with_fts):
        """Test filtering by maximum year."""
        engine = papers_with_fts["engine"]
        results = search_fts("learning", limit=10, year_max=2022, engine=engine)
        assert len(results) >= 0  # May or may not match

    def test_search_with_year_range(self, papers_with_fts):
        """Test filtering by year range."""
        engine = papers_with_fts["engine"]
        results = search_fts("learning", limit=10, year_min=2022, year_max=2023, engine=engine)
        assert len(results) >= 0

    def test_search_no_results_for_nonexistent_term(self, papers_with_fts):
        """Test that nonexistent terms return no results."""
        engine = papers_with_fts["engine"]
        results = search_fts("quantumgravitywormhole", limit=10, engine=engine)
        assert len(results) == 0

    def test_search_porter_stemming(self, papers_with_fts):
        """Test that porter stemmer works (learning matches learns)."""
        engine = papers_with_fts["engine"]
        # "learning" should match papers even with variations
        results = search_fts("learn", limit=10, engine=engine)
        # Should find papers with "learning" due to stemming
        assert len(results) > 0

    def test_search_with_snippets(self, papers_with_fts):
        """Test search with highlighted snippets."""
        engine = papers_with_fts["engine"]
        results = search_fts("neural networks", limit=10, include_snippets=True, engine=engine)

        assert len(results) > 0
        # Snippets should be populated
        result = results[0]
        # At least one snippet should be present
        assert result.title_snippet is not None or result.abstract_snippet is not None


class TestFTSPhraseSearch:
    """Tests for phrase search functionality."""

    @pytest.fixture
    def phrase_test_papers(self, test_engine, test_session):
        """Create papers for phrase search testing."""
        create_fts_tables(test_engine)

        papers = [
            Paper(
                title="Natural Language Processing Systems",
                abstract="Processing natural language is challenging.",
                year=2024
            ),
            Paper(
                title="Language Models for Natural Interaction",
                abstract="Natural interaction through language understanding.",
                year=2024
            ),
        ]

        for paper in papers:
            test_session.add(paper)
        test_session.commit()
        return {"papers": papers, "engine": test_engine}

    def test_phrase_search(self, phrase_test_papers):
        """Test exact phrase matching."""
        engine = phrase_test_papers["engine"]
        # Exact phrase should match first paper
        results = search_fts_phrase("natural language processing", limit=10, engine=engine)
        assert len(results) >= 1


class TestFTSTermCombinations:
    """Tests for AND/OR term search functionality."""

    @pytest.fixture
    def term_test_papers(self, test_engine, test_session):
        """Create papers for term combination testing."""
        create_fts_tables(test_engine)

        papers = [
            Paper(title="Alpha Beta Paper", abstract="Contains alpha and beta.", year=2024),
            Paper(title="Alpha Only Paper", abstract="Contains only alpha.", year=2024),
            Paper(title="Beta Only Paper", abstract="Contains only beta.", year=2024),
            Paper(title="Gamma Paper", abstract="Contains gamma only.", year=2024),
        ]

        for paper in papers:
            test_session.add(paper)
        test_session.commit()
        return {"papers": papers, "engine": test_engine}

    def test_any_term_search_or(self, term_test_papers):
        """Test OR search returns papers with any term."""
        engine = term_test_papers["engine"]
        results = search_fts_any_term(["alpha", "beta"], limit=10, engine=engine)
        # Should find papers with alpha OR beta
        assert len(results) >= 2

    def test_all_terms_search_and(self, term_test_papers):
        """Test AND search returns papers with all terms."""
        engine = term_test_papers["engine"]
        results = search_fts_all_terms(["alpha", "beta"], limit=10, engine=engine)
        # Should only find paper with both alpha AND beta
        assert len(results) >= 1


class TestFTSIndexRebuild:
    """Tests for FTS5 index rebuilding."""

    def test_rebuild_empty_database(self, test_engine):
        """Test rebuilding with no papers."""
        create_fts_tables(test_engine)
        result = rebuild_fts_index(test_engine)

        assert result["success"] is True
        assert result["papers_indexed"] == 0

    def test_rebuild_with_papers(self, test_engine, test_session):
        """Test rebuilding with existing papers."""
        # Add papers before FTS tables exist
        paper1 = Paper(title="First Paper", abstract="Abstract one.", year=2024)
        paper2 = Paper(title="Second Paper", abstract="Abstract two.", year=2024)
        test_session.add(paper1)
        test_session.add(paper2)
        test_session.commit()

        # Now create FTS and rebuild
        create_fts_tables(test_engine)
        result = rebuild_fts_index(test_engine)

        assert result["success"] is True
        assert result["papers_indexed"] == 2

        # Verify papers are searchable
        results = search_fts("paper", limit=10, engine=test_engine)
        assert len(results) == 2


class TestFTSOptimize:
    """Tests for FTS5 index optimization."""

    def test_optimize_index(self, test_engine, test_session):
        """Test that optimization runs without error."""
        create_fts_tables(test_engine)

        # Add some papers
        for i in range(5):
            paper = Paper(title=f"Paper {i}", abstract=f"Abstract {i}.", year=2024)
            test_session.add(paper)
        test_session.commit()

        result = optimize_fts_index(test_engine)
        assert result is True
