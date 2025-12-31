"""
Unit tests for score_storage.py

Tests CRUD operations, context filtering, and statistics.
"""

import pytest
from datetime import datetime


@pytest.mark.unit
class TestScoreStorage:
    """Test suite for ScoreStorage class."""

    def test_init_creates_database(self, temp_db_path):
        """Test that initializing creates the database file and schema."""
        from src.services.score_storage import ScoreStorage

        assert not temp_db_path.exists()

        storage = ScoreStorage(db_path=temp_db_path)

        assert temp_db_path.exists()
        assert temp_db_path.stat().st_size > 0

    def test_store_score_creates_entry(self, score_storage):
        """Test storing a new score."""
        stored = score_storage.store_score(
            paper_id="test-001",
            score=7,
            justification="Good paper",
            dimensions={"relevance": 0.8},
            key_takeaways=["Interesting findings"],
            action="should_read",
            research_interests=["ML"],
            title="Test Paper",
            authors="Smith, J.",
            year=2024,
            context_id="test-ctx",
        )

        assert stored.paper_id == "test-001"
        assert stored.score == 7
        assert stored.context_id == "test-ctx"
        assert stored.title == "Test Paper"

    def test_store_score_updates_existing(self, score_storage):
        """Test that storing again updates the score (upsert)."""
        # Store initial score
        score_storage.store_score(
            paper_id="test-001",
            score=5,
            justification="Initial",
            dimensions={},
            key_takeaways=[],
            action="skim",
            research_interests=["ML"],
            title="Test Paper",
            authors="Smith, J.",
            context_id="ctx-1",
        )

        # Update with new score
        updated = score_storage.store_score(
            paper_id="test-001",
            score=9,
            justification="Updated",
            dimensions={"relevance": 0.95},
            key_takeaways=["Much better"],
            action="must_read",
            research_interests=["ML", "DL"],
            title="Test Paper",
            authors="Smith, J.",
            context_id="ctx-1",
        )

        assert updated.score == 9
        assert updated.justification == "Updated"

        # Verify only one entry exists
        all_scores = score_storage.get_all_scores()
        assert len(all_scores) == 1

    def test_get_score_retrieves_correct_score(self, score_storage_with_data):
        """Test retrieving a specific score."""
        score = score_storage_with_data.get_score("mock-001", "test-context-1")

        assert score is not None
        assert score.paper_id == "mock-001"
        assert score.context_id == "test-context-1"
        assert score.score == 8
        assert score.action == "must_read"

    def test_get_score_returns_none_for_missing(self, score_storage):
        """Test that get_score returns None for non-existent paper."""
        score = score_storage.get_score("nonexistent", "any-context")

        assert score is None

    def test_context_isolation(self, score_storage_with_data):
        """Test that contexts are isolated."""
        # mock-001 has different scores in different contexts
        score_ctx1 = score_storage_with_data.get_score("mock-001", "test-context-1")
        score_ctx2 = score_storage_with_data.get_score("mock-001", "test-context-2")

        assert score_ctx1.score == 8
        assert score_ctx2.score == 4
        assert score_ctx1.score != score_ctx2.score

    def test_get_top_papers_filters_by_context(self, score_storage_with_data):
        """Test that get_top_papers filters by context."""
        top_ctx1 = score_storage_with_data.get_top_papers(
            context_id="test-context-1",
            min_score=0,
            limit=10,
        )

        # Context 1 has 2 papers
        assert len(top_ctx1) == 2
        assert all(s.context_id == "test-context-1" for s in top_ctx1)

    def test_get_top_papers_filters_by_min_score(self, score_storage_with_data):
        """Test that get_top_papers respects min_score."""
        top_papers = score_storage_with_data.get_top_papers(
            context_id="test-context-1",
            min_score=7,
            limit=10,
        )

        # Only mock-001 with score=8 should pass
        assert len(top_papers) == 1
        assert top_papers[0].paper_id == "mock-001"
        assert top_papers[0].score >= 7

    def test_get_top_papers_sorted_by_score(self, score_storage_with_data):
        """Test that top papers are sorted by score descending."""
        top_papers = score_storage_with_data.get_top_papers(
            context_id="test-context-1",
            min_score=0,
            limit=10,
        )

        scores = [p.score for p in top_papers]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == 8  # mock-001
        assert scores[1] == 6  # mock-002

    def test_get_top_papers_respects_limit(self, score_storage_with_data):
        """Test that limit parameter works."""
        top_papers = score_storage_with_data.get_top_papers(
            context_id="test-context-1",
            min_score=0,
            limit=1,
        )

        assert len(top_papers) == 1

    def test_get_all_scores_no_filter(self, score_storage_with_data):
        """Test getting all scores without context filter."""
        all_scores = score_storage_with_data.get_all_scores()

        # We added 3 scores total (2 in ctx-1, 1 in ctx-2)
        assert len(all_scores) == 3

    def test_get_all_scores_with_context_filter(self, score_storage_with_data):
        """Test getting all scores filtered by context."""
        ctx1_scores = score_storage_with_data.get_all_scores(context_id="test-context-1")

        assert len(ctx1_scores) == 2
        assert all(s.context_id == "test-context-1" for s in ctx1_scores)

    def test_delete_score_removes_entry(self, score_storage_with_data):
        """Test deleting a score."""
        # Verify score exists
        score = score_storage_with_data.get_score("mock-001", "test-context-1")
        assert score is not None

        # Delete it
        deleted = score_storage_with_data.delete_score("mock-001", "test-context-1")
        assert deleted is True

        # Verify it's gone
        score = score_storage_with_data.get_score("mock-001", "test-context-1")
        assert score is None

    def test_delete_score_returns_false_for_missing(self, score_storage):
        """Test that deleting non-existent score returns False."""
        deleted = score_storage.delete_score("nonexistent", "any-context")
        assert deleted is False

    def test_delete_only_affects_specific_context(self, score_storage_with_data):
        """Test that delete only removes from specific context."""
        # Delete from context-1
        score_storage_with_data.delete_score("mock-001", "test-context-1")

        # Context-2 should still have it
        score_ctx2 = score_storage_with_data.get_score("mock-001", "test-context-2")
        assert score_ctx2 is not None

    def test_get_contexts_lists_all_contexts(self, score_storage_with_data):
        """Test getting list of all contexts."""
        contexts = score_storage_with_data.get_contexts()

        assert len(contexts) == 2
        context_ids = {c["context_id"] for c in contexts}
        assert "test-context-1" in context_ids
        assert "test-context-2" in context_ids

    def test_get_contexts_includes_counts(self, score_storage_with_data):
        """Test that context list includes paper counts."""
        contexts = score_storage_with_data.get_contexts()

        ctx1 = next(c for c in contexts if c["context_id"] == "test-context-1")
        ctx2 = next(c for c in contexts if c["context_id"] == "test-context-2")

        assert ctx1["paper_count"] == 2
        assert ctx2["paper_count"] == 1

    def test_get_contexts_includes_avg_score(self, score_storage_with_data):
        """Test that context list includes average scores."""
        contexts = score_storage_with_data.get_contexts()

        ctx1 = next(c for c in contexts if c["context_id"] == "test-context-1")

        # Context-1 has scores 8 and 6, avg = 7
        assert ctx1["avg_score"] == 7.0

    def test_get_stats_overall(self, score_storage_with_data):
        """Test getting overall statistics."""
        stats = score_storage_with_data.get_stats()

        assert stats["total_scores"] == 3
        assert stats["min_score"] == 4
        assert stats["max_score"] == 8
        # Average: (8 + 6 + 4) / 3 = 6.0
        assert stats["avg_score"] == 6.0

    def test_get_stats_by_context(self, score_storage_with_data):
        """Test getting statistics filtered by context."""
        stats = score_storage_with_data.get_stats(context_id="test-context-1")

        assert stats["total_scores"] == 2
        assert stats["context_id"] == "test-context-1"
        # Average: (8 + 6) / 2 = 7.0
        assert stats["avg_score"] == 7.0

    def test_get_stats_action_counts(self, score_storage_with_data):
        """Test that stats include action counts."""
        stats = score_storage_with_data.get_stats()

        assert stats["action_counts"]["must_read"] == 1
        assert stats["action_counts"]["should_read"] == 1
        assert stats["action_counts"]["skim"] == 1
        assert stats["action_counts"]["skip"] == 0

    def test_stored_score_has_timestamp(self, score_storage):
        """Test that stored scores include timestamp."""
        stored = score_storage.store_score(
            paper_id="test-001",
            score=5,
            justification="Test",
            dimensions={},
            key_takeaways=[],
            action="skim",
            research_interests=["test"],
            title="Test",
            authors="Test",
        )

        assert stored.scored_at is not None
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(stored.scored_at)

    def test_dimensions_stored_as_json(self, score_storage):
        """Test that dimensions dict is properly serialized."""
        dimensions = {
            "relevance": 0.85,
            "novelty": 0.72,
            "methodology": 0.90,
        }

        score_storage.store_score(
            paper_id="test-001",
            score=8,
            justification="Test",
            dimensions=dimensions,
            key_takeaways=[],
            action="must_read",
            research_interests=["test"],
            title="Test",
            authors="Test",
        )

        retrieved = score_storage.get_score("test-001", "default")
        assert retrieved.dimensions == dimensions

    def test_key_takeaways_stored_as_json(self, score_storage):
        """Test that key_takeaways list is properly serialized."""
        takeaways = [
            "Novel approach to problem",
            "Strong experimental validation",
            "Open source code available",
        ]

        score_storage.store_score(
            paper_id="test-001",
            score=9,
            justification="Test",
            dimensions={},
            key_takeaways=takeaways,
            action="must_read",
            research_interests=["test"],
            title="Test",
            authors="Test",
        )

        retrieved = score_storage.get_score("test-001", "default")
        assert retrieved.key_takeaways == takeaways

    def test_research_interests_stored_as_json(self, score_storage):
        """Test that research_interests list is properly serialized."""
        interests = ["machine learning", "NLP", "transformers"]

        score_storage.store_score(
            paper_id="test-001",
            score=7,
            justification="Test",
            dimensions={},
            key_takeaways=[],
            action="should_read",
            research_interests=interests,
            title="Test",
            authors="Test",
        )

        retrieved = score_storage.get_score("test-001", "default")
        assert retrieved.research_interests == interests

    def test_singleton_pattern(self):
        """Test that get_score_storage returns singleton."""
        from src.services.score_storage import get_score_storage

        storage1 = get_score_storage()
        storage2 = get_score_storage()

        assert storage1 is storage2
