"""Tests for Search Services - RRF and Unified Search.

Tests cover:
- RRF algorithm correctness (SearchService.reciprocal_rank_fusion)
- Score normalization (SearchService.normalize_scores)
- Unified search modes (smart, keyword, semantic, hybrid)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from literature_core.models import Paper
from literature_core.fts import create_fts_tables
from services.search_service import SearchService
from services.search_constants import (
    DEFAULT_RRF_K,
    DEFAULT_ALPHA,
    DEFAULT_MIN_SIMILARITY,
)


class TestReciprocalRankFusion:
    """Tests for the RRF algorithm in SearchService."""

    def test_rrf_single_list(self):
        """Test RRF with a single ranked list."""
        results = [
            (1, 0.9),  # rank 0
            (2, 0.8),  # rank 1
            (3, 0.7),  # rank 2
        ]

        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[results],
            k=60,
        )

        # Should maintain order
        assert merged[0][0] == 1
        assert merged[1][0] == 2
        assert merged[2][0] == 3

        # Scores should be RRF: 1/(k+rank+1)
        assert abs(merged[0][1] - 1.0 / 61) < 0.001
        assert abs(merged[1][1] - 1.0 / 62) < 0.001
        assert abs(merged[2][1] - 1.0 / 63) < 0.001

    def test_rrf_two_lists_same_items(self):
        """Test RRF with two lists containing same items."""
        keyword_results = [(1, 0.9), (2, 0.8), (3, 0.7)]
        semantic_results = [(1, 0.95), (3, 0.85), (2, 0.75)]

        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[keyword_results, semantic_results],
            k=60,
        )

        # Item 1 is rank 0 in both lists, should be first
        assert merged[0][0] == 1

        # All items should be present
        paper_ids = [pid for pid, _ in merged]
        assert set(paper_ids) == {1, 2, 3}

    def test_rrf_two_lists_different_items(self):
        """Test RRF with partially overlapping lists."""
        keyword_results = [(1, 0.9), (2, 0.8)]  # Has 1, 2
        semantic_results = [(3, 0.95), (1, 0.85)]  # Has 3, 1

        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[keyword_results, semantic_results],
            k=60,
        )

        # All unique items should be present
        paper_ids = [pid for pid, _ in merged]
        assert set(paper_ids) == {1, 2, 3}

        # Item 1 appears in both lists, should rank higher
        # than items only in one list
        id_to_score = {pid: score for pid, score in merged}
        assert id_to_score[1] > id_to_score[2]  # 1 is in both, 2 is in one
        assert id_to_score[1] > id_to_score[3]  # 1 is in both, 3 is in one

    def test_rrf_with_weights(self):
        """Test RRF with custom weights."""
        keyword_results = [(1, 0.9)]  # Only item 1
        semantic_results = [(2, 0.95)]  # Only item 2

        # Heavy semantic weight
        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[keyword_results, semantic_results],
            k=60,
            weights=[0.1, 0.9],  # 10% keyword, 90% semantic
        )

        id_to_score = {pid: score for pid, score in merged}
        # Item 2 (semantic) should score higher due to weight
        assert id_to_score[2] > id_to_score[1]

    def test_rrf_empty_list(self):
        """Test RRF with empty list."""
        keyword_results = [(1, 0.9), (2, 0.8)]
        semantic_results = []  # Empty

        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[keyword_results, semantic_results],
            k=60,
        )

        # Should still return keyword results
        paper_ids = [pid for pid, _ in merged]
        assert set(paper_ids) == {1, 2}

    def test_rrf_both_empty(self):
        """Test RRF with both lists empty."""
        merged = SearchService.reciprocal_rank_fusion(
            ranked_lists=[[], []],
            k=60,
        )
        assert merged == []


class TestScoreNormalization:
    """Tests for score normalization in SearchService."""

    def test_normalize_minmax(self):
        """Test min-max normalization."""
        results = [(1, 100.0), (2, 50.0), (3, 0.0)]

        normalized = SearchService.normalize_scores(results, method="minmax")

        id_to_score = {pid: score for pid, score in normalized}
        assert id_to_score[1] == 1.0  # Max -> 1.0
        assert id_to_score[2] == 0.5  # Middle -> 0.5
        assert id_to_score[3] == 0.0  # Min -> 0.0

    def test_normalize_empty(self):
        """Test normalization with empty input."""
        normalized = SearchService.normalize_scores([])
        assert normalized == []

    def test_normalize_single_value(self):
        """Test normalization with single value."""
        results = [(1, 5.0)]
        normalized = SearchService.normalize_scores(results)
        # Single value normalizes to 1.0
        assert normalized[0][1] == 1.0

    def test_normalize_same_values(self):
        """Test normalization when all values are same."""
        results = [(1, 5.0), (2, 5.0), (3, 5.0)]
        normalized = SearchService.normalize_scores(results)
        # All same -> all 1.0
        for _, score in normalized:
            assert score == 1.0


class TestUnifiedSearchModes:
    """Tests for UnifiedSearchService search modes."""

    @pytest.mark.asyncio
    async def test_unified_keyword_search(self):
        """Test UnifiedSearchService keyword mode."""
        from services.unified_search_service import UnifiedSearchService

        with patch.object(SearchService, 'keyword_search') as mock_keyword:
            mock_keyword.return_value = MagicMock(
                results=[{"id": 1, "title": "Test"}],
                count=1,
                search_type="keyword_fts5"
            )

            result = await UnifiedSearchService.search(
                query="test",
                limit=10,
                mode="keyword"
            )

            assert result.mode == "keyword"
            mock_keyword.assert_called_once()

    @pytest.mark.asyncio
    async def test_unified_smart_search_expands_acronyms(self):
        """Test that smart search expands acronyms."""
        from services.unified_search_service import UnifiedSearchService

        # Just test the expansion logic, not the full search
        expansion = UnifiedSearchService.expand_query("ALD thin films")

        assert "ALD -> atomic layer deposition" in expansion.acronyms_expanded
        assert "atomic layer deposition" in expansion.final_query.lower()


class TestDefaultValues:
    """Tests for default configuration values."""

    def test_default_k_value(self):
        """Test default RRF k value."""
        assert DEFAULT_RRF_K == 60  # Standard value

    def test_default_alpha_value(self):
        """Test default alpha (semantic weight)."""
        assert DEFAULT_ALPHA == 0.65  # Slight semantic preference

    def test_default_min_similarity(self):
        """Test default minimum similarity."""
        assert DEFAULT_MIN_SIMILARITY == 0.35  # Discovery-focused
