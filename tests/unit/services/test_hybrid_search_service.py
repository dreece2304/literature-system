"""Tests for Hybrid Search Service with Reciprocal Rank Fusion.

Tests cover:
- RRF algorithm correctness
- Score normalization
- Hybrid search with keyword + semantic
- Graceful degradation when components unavailable
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from literature_core.models import Paper
from literature_core.fts import create_fts_tables
from services.hybrid_search_service import (
    HybridSearchService,
    HybridSearchResults,
    HybridSearchDiagnostics,
    DEFAULT_RRF_K,
    DEFAULT_ALPHA,
    DEFAULT_MIN_SIMILARITY,
)


class TestReciprocalRankFusion:
    """Tests for the RRF algorithm."""

    def test_rrf_single_list(self):
        """Test RRF with a single ranked list."""
        results = [
            (1, 0.9),  # rank 0
            (2, 0.8),  # rank 1
            (3, 0.7),  # rank 2
        ]

        merged = HybridSearchService.reciprocal_rank_fusion(
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

        merged = HybridSearchService.reciprocal_rank_fusion(
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

        merged = HybridSearchService.reciprocal_rank_fusion(
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
        merged = HybridSearchService.reciprocal_rank_fusion(
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

        merged = HybridSearchService.reciprocal_rank_fusion(
            ranked_lists=[keyword_results, semantic_results],
            k=60,
        )

        # Should still return keyword results
        paper_ids = [pid for pid, _ in merged]
        assert set(paper_ids) == {1, 2}

    def test_rrf_both_empty(self):
        """Test RRF with both lists empty."""
        merged = HybridSearchService.reciprocal_rank_fusion(
            ranked_lists=[[], []],
            k=60,
        )
        assert merged == []


class TestScoreNormalization:
    """Tests for score normalization."""

    def test_normalize_minmax(self):
        """Test min-max normalization."""
        results = [(1, 100.0), (2, 50.0), (3, 0.0)]

        normalized = HybridSearchService.normalize_scores(results, method="minmax")

        id_to_score = {pid: score for pid, score in normalized}
        assert id_to_score[1] == 1.0  # Max -> 1.0
        assert id_to_score[2] == 0.5  # Middle -> 0.5
        assert id_to_score[3] == 0.0  # Min -> 0.0

    def test_normalize_empty(self):
        """Test normalization with empty input."""
        normalized = HybridSearchService.normalize_scores([])
        assert normalized == []

    def test_normalize_single_value(self):
        """Test normalization with single value."""
        results = [(1, 5.0)]
        normalized = HybridSearchService.normalize_scores(results)
        # Single value normalizes to 1.0
        assert normalized[0][1] == 1.0

    def test_normalize_same_values(self):
        """Test normalization when all values are same."""
        results = [(1, 5.0), (2, 5.0), (3, 5.0)]
        normalized = HybridSearchService.normalize_scores(results)
        # All same -> all 1.0
        for _, score in normalized:
            assert score == 1.0


class TestHybridSearchWithFTS:
    """Tests for hybrid search with FTS5 integration."""

    @pytest.fixture
    def papers_with_fts(self, test_engine, test_session):
        """Create papers with FTS5 index."""
        create_fts_tables(test_engine)

        papers = [
            Paper(
                title="Machine Learning for Natural Language Processing",
                abstract="Deep learning approaches to NLP.",
                year=2023
            ),
            Paper(
                title="Neural Network Architectures",
                abstract="Survey of modern neural architectures.",
                year=2024
            ),
            Paper(
                title="Statistical Methods in Data Science",
                abstract="Classical statistical techniques.",
                year=2022
            ),
        ]

        for paper in papers:
            test_session.add(paper)
        test_session.commit()

        return {"papers": papers, "engine": test_engine}

    @pytest.mark.asyncio
    async def test_hybrid_search_keyword_only(self, papers_with_fts):
        """Test hybrid search with keyword-only mode."""
        engine = papers_with_fts["engine"]

        # Patch get_engine to use test engine
        with patch('literature_core.fts.get_engine', return_value=engine):
            with patch('services.hybrid_search_service.get_fts_status') as mock_status:
                mock_status.return_value = MagicMock(is_available=True)

                with patch('services.hybrid_search_service.search_fts') as mock_fts:
                    # Mock FTS results
                    mock_fts.return_value = [
                        MagicMock(paper_id=1, bm25_score=5.0),
                        MagicMock(paper_id=2, bm25_score=3.0),
                    ]

                    results = await HybridSearchService.search(
                        query="machine learning",
                        limit=10,
                        alpha=0.0,  # Keyword only
                        search_modes=["keyword"],
                    )

                    assert results.count >= 0
                    assert results.alpha == 0.0
                    assert "keyword" in results.search_modes

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_diagnostics(self, papers_with_fts):
        """Test that hybrid search returns proper diagnostics."""
        engine = papers_with_fts["engine"]

        with patch('literature_core.fts.get_engine', return_value=engine):
            with patch('services.hybrid_search_service.get_fts_status') as mock_status:
                mock_status.return_value = MagicMock(is_available=True)

                with patch('services.hybrid_search_service.search_fts') as mock_fts:
                    mock_fts.return_value = []

                    results = await HybridSearchService.search(
                        query="test query",
                        limit=10,
                    )

                    assert hasattr(results, 'diagnostics')
                    diag = results.diagnostics
                    assert hasattr(diag, 'fts_available')
                    assert hasattr(diag, 'keyword_results_count')
                    assert hasattr(diag, 'semantic_results_count')

    @pytest.mark.asyncio
    async def test_hybrid_search_fallback_when_fts_unavailable(self, papers_with_fts):
        """Test fallback to SQL LIKE when FTS5 unavailable."""
        with patch('services.hybrid_search_service.get_fts_status') as mock_status:
            mock_status.return_value = MagicMock(is_available=False)

            results = await HybridSearchService.search(
                query="machine",
                limit=10,
                alpha=0.0,
                search_modes=["keyword"],
            )

            # Should still work with fallback
            assert results.diagnostics.fallback_used is True
            assert "FTS5 not available" in results.diagnostics.fallback_reason


class TestHybridSearchMocked:
    """Tests with fully mocked components."""

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_results(self):
        """Test that hybrid search properly combines keyword and semantic."""
        with patch('services.hybrid_search_service.get_fts_status') as mock_fts_status:
            mock_fts_status.return_value = MagicMock(is_available=True)

            with patch('services.hybrid_search_service.search_fts') as mock_fts:
                # Keyword results: paper 1, 2, 3
                mock_fts.return_value = [
                    MagicMock(paper_id=1, bm25_score=10.0),
                    MagicMock(paper_id=2, bm25_score=8.0),
                    MagicMock(paper_id=3, bm25_score=6.0),
                ]

                with patch.object(
                    HybridSearchService, '_semantic_search', new_callable=AsyncMock
                ) as mock_semantic:
                    # Semantic results: paper 3, 4, 1 (different order, partial overlap)
                    mock_semantic.return_value = [
                        (3, 0.95),  # Paper 3 is best semantically
                        (4, 0.85),  # Paper 4 only in semantic
                        (1, 0.75),  # Paper 1 also in keyword
                    ]

                    with patch('services.hybrid_search_service.get_session') as mock_session:
                        # Mock the database session
                        mock_paper_1 = MagicMock(
                            id=1, title="Paper 1", year=2024,
                            abstract="Abstract 1", doi="10.1/1",
                            authors=[], tags=[]
                        )
                        mock_paper_3 = MagicMock(
                            id=3, title="Paper 3", year=2023,
                            abstract="Abstract 3", doi="10.1/3",
                            authors=[], tags=[]
                        )
                        mock_paper_4 = MagicMock(
                            id=4, title="Paper 4", year=2022,
                            abstract="Abstract 4", doi="10.1/4",
                            authors=[], tags=[]
                        )

                        mock_query = MagicMock()
                        mock_query.options.return_value.filter.return_value.all.return_value = [
                            mock_paper_1, mock_paper_3, mock_paper_4
                        ]
                        mock_session.return_value.__enter__.return_value.query.return_value = mock_query

                        results = await HybridSearchService.search(
                            query="test",
                            limit=10,
                            alpha=0.5,  # Equal weight
                        )

                        # Papers 1 and 3 should rank higher (in both lists)
                        assert results.count > 0
                        assert results.diagnostics.keyword_results_count == 3
                        assert results.diagnostics.semantic_results_count == 3

    @pytest.mark.asyncio
    async def test_hybrid_search_with_year_filter(self):
        """Test hybrid search with year filters."""
        with patch('services.hybrid_search_service.get_fts_status') as mock_status:
            mock_status.return_value = MagicMock(is_available=True)

            with patch('services.hybrid_search_service.search_fts') as mock_fts:
                mock_fts.return_value = []

                results = await HybridSearchService.search(
                    query="test",
                    limit=10,
                    year_min=2020,
                    year_max=2024,
                    search_modes=["keyword"],
                )

                # Verify year filters were passed
                mock_fts.assert_called_once()
                call_kwargs = mock_fts.call_args[1]
                assert call_kwargs.get('year_min') == 2020
                assert call_kwargs.get('year_max') == 2024


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
