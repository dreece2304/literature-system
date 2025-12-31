"""Unit tests for PDFService.

Tests cover:
- PDF status checking
- Duplicate detection by hash
- PDF path management
"""
import pytest

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestPDFStatus:
    """Tests for PDF status operations."""

    def test_get_pdf_status_all(self, db):
        """Test getting PDF status for all papers."""
        from services import PaperService, PDFService

        # Create papers with and without PDFs
        paper1 = PaperService.create(title="Paper with PDF")
        paper2 = PaperService.create(title="Paper without PDF")

        # Simulate PDF path for paper1
        PaperService.update(paper1["id"], pdf_path="/fake/path/paper1.pdf")

        result = PDFService.get_status(filter="all")

        assert "papers" in result
        assert len(result["papers"]) == 2

    def test_get_pdf_status_has_pdf(self, db):
        """Test filtering papers that have PDFs."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper with PDF")
        paper2 = PaperService.create(title="Paper without PDF")

        PaperService.update(paper1["id"], pdf_path="/fake/path/paper1.pdf")

        result = PDFService.get_status(filter="has_pdf")

        assert len(result["papers"]) == 1
        assert result["papers"][0]["id"] == paper1["id"]

    def test_get_pdf_status_needs_pdf(self, db):
        """Test filtering papers that need PDFs."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper with PDF")
        paper2 = PaperService.create(title="Paper without PDF")

        PaperService.update(paper1["id"], pdf_path="/fake/path/paper1.pdf")

        result = PDFService.get_status(filter="needs_pdf")

        assert len(result["papers"]) == 1
        assert result["papers"][0]["id"] == paper2["id"]

    def test_get_pdf_status_with_limit(self, db):
        """Test PDF status with limit."""
        from services import PaperService, PDFService

        for i in range(10):
            PaperService.create(title=f"Paper {i}")

        result = PDFService.get_status(filter="all", limit=5)

        assert len(result["papers"]) == 5


class TestDuplicateDetection:
    """Tests for duplicate PDF detection."""

    def test_find_duplicates_by_hash_no_duplicates(self, db):
        """Test finding duplicates when none exist."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2")

        # Set different hashes
        PaperService.update(paper1["id"], file_hash="hash1")
        PaperService.update(paper2["id"], file_hash="hash2")

        result = PDFService.find_duplicates(method="hash")

        assert result["duplicates"] == []

    def test_find_duplicates_by_hash_with_duplicates(self, db):
        """Test finding duplicates by file hash."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2 - Duplicate")

        # Set same hash for both
        same_hash = "abc123def456"
        PaperService.update(paper1["id"], file_hash=same_hash)
        PaperService.update(paper2["id"], file_hash=same_hash)

        result = PDFService.find_duplicates(method="hash")

        assert len(result["duplicates"]) > 0

    def test_find_duplicates_by_title(self, db):
        """Test finding duplicates by similar titles."""
        from services import PaperService, PDFService

        PaperService.create(title="Machine Learning for Materials Science")
        PaperService.create(title="Machine Learning for Materials Science: A Review")

        result = PDFService.find_duplicates(method="title", threshold=0.8)

        # Should find potential duplicates due to similar titles
        assert "duplicates" in result

    def test_find_duplicates_by_title_no_match(self, db):
        """Test no duplicates found with different titles."""
        from services import PaperService, PDFService

        PaperService.create(title="Quantum Computing Fundamentals")
        PaperService.create(title="Organic Chemistry Methods")

        result = PDFService.find_duplicates(method="title", threshold=0.9)

        # Completely different titles should not match
        assert result["duplicates"] == []


class TestPDFAcquisition:
    """Tests for PDF acquisition operations."""

    def test_acquire_pdf_success(self, db, mock_external_apis):
        """Test successful PDF acquisition."""
        from services import PaperService, PDFService

        paper = PaperService.create(
            title="Test Paper",
            doi="10.1234/test.2023"
        )

        # Mock would handle actual download
        result = PDFService.acquire(paper["id"])

        assert "status" in result

    def test_acquire_pdf_no_doi(self, db):
        """Test PDF acquisition without DOI."""
        from services import PaperService, PDFService

        paper = PaperService.create(title="Paper without DOI")

        result = PDFService.acquire(paper["id"])

        # Should indicate no DOI available
        assert result.get("status") in ["error", "no_doi", "not_found"]

    def test_acquire_pdf_paper_not_found(self, db):
        """Test PDF acquisition for non-existent paper."""
        from services import PDFService

        with pytest.raises(Exception):
            PDFService.acquire(99999)


class TestPDFPathManagement:
    """Tests for PDF path operations."""

    def test_update_pdf_path(self, db):
        """Test updating PDF path."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")
        pdf_path = "/storage/pdfs/test_paper.pdf"

        updated = PaperService.update(paper["id"], pdf_path=pdf_path)

        assert updated["pdf_path"] == pdf_path

    def test_clear_pdf_path(self, db):
        """Test clearing PDF path."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")
        PaperService.update(paper["id"], pdf_path="/some/path.pdf")

        updated = PaperService.update(paper["id"], pdf_path=None)

        assert updated["pdf_path"] is None

    def test_update_file_hash(self, db):
        """Test updating file hash."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")
        file_hash = "sha256:abc123def456"

        updated = PaperService.update(paper["id"], file_hash=file_hash)

        assert updated["file_hash"] == file_hash
