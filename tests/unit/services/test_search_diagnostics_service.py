"""Tests for Search Diagnostics Service.

Tests cover:
- FTS5 status checking
- ChromaDB status checking
- Database statistics
- Recommendations generation
- Simplified health check
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.search_diagnostics_service import (
    SearchDiagnostics,
    SearchDiagnosticsService,
    get_search_status,
)


class TestSearchDiagnostics:
    """Tests for SearchDiagnostics dataclass."""

    def test_default_values(self):
        """Test default values for SearchDiagnostics."""
        diag = SearchDiagnostics()

        assert diag.fts_available is False
        assert diag.fts_indexed_count == 0
        assert diag.fts_needs_rebuild is False
        assert diag.chromadb_available is False
        assert diag.chromadb_paper_count == 0
        assert diag.chromadb_chunk_count == 0
        assert diag.total_papers == 0
        assert diag.papers_with_embeddings == 0
        assert diag.embedding_coverage_percent == 0.0
        assert diag.warnings == []
        assert diag.errors == []
        assert diag.recommendations == []
        assert isinstance(diag.check_time, datetime)

    def test_custom_values(self):
        """Test SearchDiagnostics with custom values."""
        diag = SearchDiagnostics(
            fts_available=True,
            fts_indexed_count=100,
            total_papers=100,
            chromadb_available=True,
            chromadb_paper_count=50,
            papers_with_embeddings=50,
            embedding_coverage_percent=50.0,
        )

        assert diag.fts_available is True
        assert diag.fts_indexed_count == 100
        assert diag.chromadb_available is True
        assert diag.embedding_coverage_percent == 50.0


class TestSearchDiagnosticsService:
    """Tests for SearchDiagnosticsService."""

    @pytest.fixture
    def mock_fts_status(self):
        """Mock FTS status."""
        status = MagicMock()
        status.is_available = True
        status.indexed_count = 100
        status.papers_count = 100
        status.needs_rebuild = False
        status.last_error = None
        return status

    def test_check_fts_status_available(self, mock_fts_status):
        """Test FTS status check when available."""
        diag = SearchDiagnostics()

        with patch('literature_core.fts.get_fts_status', return_value=mock_fts_status):
            SearchDiagnosticsService._check_fts_status(diag)

        assert diag.fts_available is True
        assert diag.fts_indexed_count == 100
        assert diag.fts_needs_rebuild is False
        assert len(diag.warnings) == 0

    def test_check_fts_status_unavailable(self):
        """Test FTS status check when unavailable."""
        diag = SearchDiagnostics()
        mock_status = MagicMock()
        mock_status.is_available = False
        mock_status.indexed_count = 0
        mock_status.papers_count = 50
        mock_status.needs_rebuild = False
        mock_status.last_error = None

        with patch('literature_core.fts.get_fts_status', return_value=mock_status):
            SearchDiagnosticsService._check_fts_status(diag)

        assert diag.fts_available is False
        assert "FTS5 not available" in diag.warnings[0]

    def test_check_fts_status_needs_rebuild(self):
        """Test FTS status check when rebuild needed."""
        diag = SearchDiagnostics()
        mock_status = MagicMock()
        mock_status.is_available = True
        mock_status.indexed_count = 50
        mock_status.papers_count = 100
        mock_status.needs_rebuild = True
        mock_status.last_error = None

        with patch('literature_core.fts.get_fts_status', return_value=mock_status):
            SearchDiagnosticsService._check_fts_status(diag)

        assert diag.fts_needs_rebuild is True
        assert "out of sync" in diag.warnings[0]

    def test_check_database_stats(self, test_session):
        """Test database statistics check."""
        from literature_core.models import Paper, PaperChunk

        # Add test papers
        paper1 = Paper(
            title="Test Paper 1",
            abstract="Abstract 1",
        )
        paper2 = Paper(
            title="Test Paper 2",
            abstract=None,
        )
        test_session.add_all([paper1, paper2])
        test_session.flush()  # Get IDs

        # Add chunk for paper1 (Paper.full_text column is deprecated)
        chunk = PaperChunk(
            paper_id=paper1.id,
            chunk_order=0,
            content="Full text content",
        )
        test_session.add(chunk)
        test_session.commit()

        diag = SearchDiagnostics()

        # Patch get_session to return our test session
        with patch('services.search_diagnostics_service.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=test_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
            SearchDiagnosticsService._check_database_stats(diag)

        assert diag.total_papers == 2
        assert diag.papers_with_abstract == 1
        assert diag.papers_with_full_text == 1  # Paper with chunks

    def test_check_vectorstore_status_unavailable(self):
        """Test vector store status when unavailable."""
        diag = SearchDiagnostics()
        diag.total_papers = 100

        with patch.dict('sys.modules', {'embeddings.vectorstore': MagicMock()}):
            with patch('embeddings.vectorstore.get_vector_store', side_effect=Exception("Not available")):
                SearchDiagnosticsService._check_vectorstore_status(diag)

        assert diag.chromadb_available is False
        assert "ChromaDB not available" in diag.warnings[0]

    def test_generate_recommendations_fts_unavailable(self):
        """Test recommendations when FTS is unavailable."""
        diag = SearchDiagnostics()
        diag.fts_available = False

        SearchDiagnosticsService._generate_recommendations(diag)

        assert any("migrate_fts5" in r for r in diag.recommendations)

    def test_generate_recommendations_fts_needs_rebuild(self):
        """Test recommendations when FTS needs rebuild."""
        diag = SearchDiagnostics()
        diag.fts_available = True
        diag.fts_needs_rebuild = True

        SearchDiagnosticsService._generate_recommendations(diag)

        assert any("rebuild" in r for r in diag.recommendations)

    def test_generate_recommendations_embeddings_needed(self):
        """Test recommendations when embeddings are needed."""
        diag = SearchDiagnostics()
        diag.fts_available = True
        diag.papers_needing_embeddings = 50

        SearchDiagnosticsService._generate_recommendations(diag)

        assert any("embeddings" in r.lower() for r in diag.recommendations)

    def test_generate_recommendations_missing_full_text(self):
        """Test recommendations when many papers missing full text."""
        diag = SearchDiagnostics()
        diag.fts_available = True
        diag.total_papers = 100
        diag.papers_with_full_text = 30  # Only 30% have full text

        SearchDiagnosticsService._generate_recommendations(diag)

        assert any("full text" in r.lower() for r in diag.recommendations)

    def test_get_embedding_coverage(self):
        """Test get_embedding_coverage method."""
        with patch.object(
            SearchDiagnosticsService, 'get_diagnostics'
        ) as mock_diag:
            mock_diag.return_value = SearchDiagnostics(
                total_papers=100,
                papers_with_embeddings=50,
                papers_needing_embeddings=50,
                embedding_coverage_percent=50.0,
                chromadb_chunk_count=1000,
            )

            coverage = SearchDiagnosticsService.get_embedding_coverage()

        assert coverage["total_papers"] == 100
        assert coverage["papers_with_embeddings"] == 50
        assert coverage["coverage_percent"] == 50.0
        assert coverage["chunk_count"] == 1000

    def test_get_search_health_healthy(self):
        """Test get_search_health when system is healthy."""
        with patch.object(
            SearchDiagnosticsService, 'get_diagnostics'
        ) as mock_diag:
            mock_diag.return_value = SearchDiagnostics(
                fts_available=True,
                chromadb_available=True,
                total_papers=100,
                embedding_coverage_percent=80.0,
                warnings=[],
                errors=[],
            )

            health = SearchDiagnosticsService.get_search_health()

        assert health["status"] == "healthy"
        assert health["fts_available"] is True
        assert health["semantic_available"] is True

    def test_get_search_health_degraded(self):
        """Test get_search_health when system is degraded."""
        with patch.object(
            SearchDiagnosticsService, 'get_diagnostics'
        ) as mock_diag:
            mock_diag.return_value = SearchDiagnostics(
                fts_available=True,
                chromadb_available=False,
                total_papers=100,
                warnings=["ChromaDB not available"],
                errors=[],
            )

            health = SearchDiagnosticsService.get_search_health()

        assert health["status"] == "degraded"
        assert len(health["warnings"]) > 0

    def test_get_search_health_unhealthy(self):
        """Test get_search_health when system has errors."""
        with patch.object(
            SearchDiagnosticsService, 'get_diagnostics'
        ) as mock_diag:
            mock_diag.return_value = SearchDiagnostics(
                fts_available=False,
                chromadb_available=False,
                total_papers=100,
                warnings=[],
                errors=["Database connection failed"],
            )

            health = SearchDiagnosticsService.get_search_health()

        assert health["status"] == "unhealthy"
        assert len(health["errors"]) > 0

    def test_get_search_health_contains_check_time(self):
        """Test that get_search_health returns check_time."""
        with patch.object(
            SearchDiagnosticsService, 'get_diagnostics'
        ) as mock_diag:
            mock_diag.return_value = SearchDiagnostics()

            health = SearchDiagnosticsService.get_search_health()

        assert "check_time" in health
        # Should be ISO format string
        assert isinstance(health["check_time"], str)


class TestConvenienceFunction:
    """Tests for convenience function."""

    def test_get_search_status(self):
        """Test get_search_status convenience function."""
        with patch.object(
            SearchDiagnosticsService, 'get_search_health'
        ) as mock_health:
            mock_health.return_value = {"status": "healthy"}

            result = get_search_status()

        assert result["status"] == "healthy"
        mock_health.assert_called_once()
