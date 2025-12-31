"""Unit tests for ValidationService.

Tests cover:
- Validation status reporting
- Queue management for papers needing validation
- Single paper validation
- Batch validation processing
"""
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from services.validation_service import (
    ValidationService,
    ValidationStatus,
    ValidationResult,
    PaperValidation
)
from services.paper_service import PaperService
from services.external_search import PaperResult
from literature_core import get_session, Paper


class TestValidationStatus:
    """Tests for ValidationStatus dataclass."""

    def test_status_defaults(self):
        """Test default values for ValidationStatus."""
        status = ValidationStatus()

        assert status.total_papers == 0
        assert status.validated_papers == 0
        assert status.verified_papers == 0
        assert status.unvalidated_papers == 0

    def test_validation_coverage_percent_empty(self):
        """Test coverage percent with no papers."""
        status = ValidationStatus()
        assert status.validation_coverage_percent == 100.0

    def test_validation_coverage_percent_calculation(self):
        """Test coverage percent calculation."""
        status = ValidationStatus(
            total_papers=100,
            validated_papers=75,
        )
        assert status.validation_coverage_percent == 75.0

    def test_verification_rate_empty(self):
        """Test verification rate with no validated papers."""
        status = ValidationStatus()
        assert status.verification_rate_percent == 0.0

    def test_verification_rate_calculation(self):
        """Test verification rate calculation."""
        status = ValidationStatus(
            validated_papers=80,
            verified_papers=60,
        )
        assert status.verification_rate_percent == 75.0


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_result_defaults(self):
        """Test default values for ValidationResult."""
        result = ValidationResult()

        assert result.papers_processed == 0
        assert result.papers_verified == 0
        assert result.papers_not_found == 0
        assert result.papers_error == 0
        assert result.errors == []

    def test_success_with_no_errors(self):
        """Test success is True when no errors."""
        result = ValidationResult(papers_processed=5)
        assert result.success is True

    def test_success_with_errors_but_progress(self):
        """Test success is True when there are errors but also progress."""
        result = ValidationResult(
            papers_processed=3,
            errors=["Error on paper 1"]
        )
        assert result.success is True

    def test_success_false_when_only_errors(self):
        """Test success is False when only errors and no progress."""
        result = ValidationResult(
            papers_processed=0,
            errors=["Error 1", "Error 2"]
        )
        assert result.success is False


class TestGetValidationStatus:
    """Tests for ValidationService.get_validation_status."""

    def test_get_status_empty_database(self, db):
        """Test status with empty database."""
        status = ValidationService.get_validation_status()

        assert status.total_papers == 0
        assert status.validated_papers == 0
        assert status.unvalidated_papers == 0

    def test_get_status_with_papers(self, db):
        """Test status counts papers correctly."""
        # Create papers with different validation states
        p1 = PaperService.create(title="Paper 1", doi="10.1000/test1")
        p2 = PaperService.create(title="Paper 2", doi="10.1000/test2")
        p3 = PaperService.create(title="Paper 3")  # No DOI

        # Update validation status directly in DB
        with get_session() as session:
            paper1 = session.query(Paper).filter(Paper.id == p1["id"]).first()
            paper1.validation_status = "verified"
            paper1.validation_source = "crossref"

            paper2 = session.query(Paper).filter(Paper.id == p2["id"]).first()
            paper2.validation_status = "not_found"

            session.commit()

        status = ValidationService.get_validation_status()

        assert status.total_papers == 3
        assert status.verified_papers == 1
        assert status.not_found_papers == 1
        assert status.unvalidated_papers == 1
        assert status.papers_with_doi == 2

    def test_get_status_identifier_counts(self, db):
        """Test status counts papers by identifier type."""
        PaperService.create(title="Paper with DOI", doi="10.1000/test")
        PaperService.create(title="Paper with arXiv", arxiv_id="2301.12345")
        PaperService.create(title="Paper with both", doi="10.1000/both", arxiv_id="2302.54321")
        PaperService.create(title="Paper with nothing")

        status = ValidationService.get_validation_status()

        assert status.papers_with_doi == 2  # DOI and both
        assert status.papers_with_arxiv == 2  # arXiv and both
        assert status.papers_with_title_only == 1  # only "Paper with nothing"


class TestGetPapersNeedingValidation:
    """Tests for ValidationService.get_papers_needing_validation."""

    def test_get_queue_empty(self, db):
        """Test empty queue when no unvalidated papers."""
        p = PaperService.create(title="Validated Paper")
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == p["id"]).first()
            paper.validation_status = "verified"
            session.commit()

        queue = ValidationService.get_papers_needing_validation()
        assert len(queue) == 0

    def test_get_queue_returns_unvalidated(self, db):
        """Test queue returns unvalidated papers."""
        p1 = PaperService.create(title="Unvalidated 1")
        p2 = PaperService.create(title="Unvalidated 2")

        queue = ValidationService.get_papers_needing_validation()

        assert len(queue) == 2
        paper_ids = [p["id"] for p in queue]
        assert p1["id"] in paper_ids
        assert p2["id"] in paper_ids

    def test_get_queue_prioritizes_doi(self, db):
        """Test queue prioritizes papers with DOI."""
        p_no_doi = PaperService.create(title="No DOI")
        p_with_doi = PaperService.create(title="With DOI", doi="10.1000/test")

        queue = ValidationService.get_papers_needing_validation(prioritize_with_doi=True)

        # Paper with DOI should be first
        assert queue[0]["doi"] == "10.1000/test"

    def test_get_queue_respects_limit(self, db):
        """Test queue respects limit parameter."""
        for i in range(10):
            PaperService.create(title=f"Paper {i}")

        queue = ValidationService.get_papers_needing_validation(limit=3)
        assert len(queue) == 3


class TestValidatePaper:
    """Tests for ValidationService.validate_paper."""

    @pytest.mark.asyncio
    async def test_validate_paper_not_found_in_db(self, db):
        """Test validating non-existent paper."""
        result = await ValidationService.validate_paper(99999)

        assert result.status == "error"
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_validate_paper_with_doi_verified(self, db):
        """Test validating paper with DOI that exists in CrossRef."""
        paper = PaperService.create(
            title="Test Paper",
            doi="10.1000/test123"
        )

        mock_result = PaperResult(
            title="Test Paper",
            authors=["Author One"],
            year=2023,
            doi="10.1000/test123",
            journal="Test Journal",
            source="crossref",
            confidence=0.95
        )

        with patch.object(
            ValidationService, '_update_paper_validation'
        ) as mock_update:
            with patch(
                'services.validation_service.ExternalSearchService'
            ) as MockService:
                mock_instance = MockService.return_value
                mock_instance.lookup_by_doi = AsyncMock(return_value=mock_result)
                mock_instance.find_doi_by_title = AsyncMock(return_value=None)

                result = await ValidationService.validate_paper(paper["id"])

        assert result.status == "verified"
        assert result.source == "crossref"
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_validate_paper_by_title(self, db):
        """Test validating paper by title search."""
        paper = PaperService.create(
            title="Novel Research Paper",
            authors=["Smith, John"]
        )

        mock_result = PaperResult(
            title="Novel Research Paper",
            authors=["John Smith"],
            year=2023,
            doi="10.1000/found",
            journal="Found Journal",
            source="semantic_scholar",
            confidence=0.90
        )

        with patch.object(
            ValidationService, '_update_paper_validation'
        ) as mock_update:
            with patch(
                'services.validation_service.ExternalSearchService'
            ) as MockService:
                mock_instance = MockService.return_value
                mock_instance.lookup_by_doi = AsyncMock(return_value=None)
                mock_instance.find_doi_by_title = AsyncMock(return_value=mock_result)

                result = await ValidationService.validate_paper(paper["id"])

        assert result.status == "verified"
        assert result.source == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_validate_paper_not_found_externally(self, db):
        """Test validating paper that doesn't exist in external databases."""
        paper = PaperService.create(title="Unknown Paper")

        with patch.object(
            ValidationService, '_update_paper_validation'
        ) as mock_update:
            with patch(
                'services.validation_service.ExternalSearchService'
            ) as MockService:
                mock_instance = MockService.return_value
                mock_instance.lookup_by_doi = AsyncMock(return_value=None)
                mock_instance.find_doi_by_title = AsyncMock(return_value=None)

                result = await ValidationService.validate_paper(paper["id"])

        assert result.status == "not_found"

    @pytest.mark.asyncio
    async def test_validate_paper_low_confidence(self, db):
        """Test validation with low confidence match."""
        paper = PaperService.create(title="Similar Paper")

        mock_result = PaperResult(
            title="Almost Similar Paper",
            authors=["Different Author"],
            year=2020,
            doi="10.1000/different",
            journal="Other Journal",
            source="crossref",
            confidence=0.50  # Below threshold
        )

        with patch.object(
            ValidationService, '_update_paper_validation'
        ) as mock_update:
            with patch(
                'services.validation_service.ExternalSearchService'
            ) as MockService:
                mock_instance = MockService.return_value
                mock_instance.lookup_by_doi = AsyncMock(return_value=None)
                mock_instance.find_doi_by_title = AsyncMock(return_value=mock_result)

                result = await ValidationService.validate_paper(paper["id"])

        assert result.status == "not_found"
        assert "Low confidence" in result.message


class TestValidateBatch:
    """Tests for ValidationService.validate_batch."""

    @pytest.mark.asyncio
    async def test_validate_batch_empty(self, db):
        """Test batch validation with no papers."""
        result = await ValidationService.validate_batch(paper_ids=[])

        assert result.papers_processed == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_validate_batch_from_queue(self, db):
        """Test batch validation processes from queue."""
        PaperService.create(title="Paper 1")
        PaperService.create(title="Paper 2")

        with patch.object(
            ValidationService, 'validate_paper',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = PaperValidation(
                paper_id=1,
                status="verified",
                confidence=0.95
            )

            result = await ValidationService.validate_batch(limit=2)

        assert mock_validate.call_count == 2
        assert result.papers_processed == 2

    @pytest.mark.asyncio
    async def test_validate_batch_specific_ids(self, db):
        """Test batch validation with specific paper IDs."""
        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        with patch.object(
            ValidationService, 'validate_paper',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = PaperValidation(
                paper_id=1,
                status="verified",
                confidence=0.95
            )

            result = await ValidationService.validate_batch(
                paper_ids=[p1["id"], p2["id"]]
            )

        assert result.papers_processed == 2


class TestResetValidation:
    """Tests for ValidationService.reset_validation."""

    def test_reset_specific_papers(self, db):
        """Test resetting validation for specific papers."""
        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        # Set validation status
        with get_session() as session:
            for pid in [p1["id"], p2["id"]]:
                paper = session.query(Paper).filter(Paper.id == pid).first()
                paper.validation_status = "verified"
            session.commit()

        count = ValidationService.reset_validation(paper_ids=[p1["id"]])

        assert count == 1

        # Check only p1 was reset
        with get_session() as session:
            paper1 = session.query(Paper).filter(Paper.id == p1["id"]).first()
            paper2 = session.query(Paper).filter(Paper.id == p2["id"]).first()
            assert paper1.validation_status == "unvalidated"
            assert paper2.validation_status == "verified"

    def test_reset_all_papers(self, db):
        """Test resetting validation for all papers."""
        for i in range(3):
            p = PaperService.create(title=f"Paper {i}")
            with get_session() as session:
                paper = session.query(Paper).filter(Paper.id == p["id"]).first()
                paper.validation_status = "verified"
                session.commit()

        count = ValidationService.reset_validation(paper_ids=None)

        assert count == 3

        # Check all were reset
        status = ValidationService.get_validation_status()
        assert status.unvalidated_papers == 3
        assert status.verified_papers == 0
