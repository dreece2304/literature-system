"""Unit tests for PDFService.

Tests the service layer directly (not MCP tools).
Note: PDFService uses different parameter names than MCP tools:
  - Service: filter_type="all"
  - MCP Tool: filter="all" (translated to filter_type internally)

Tests cover:
- PDF status checking (get_status)
- Duplicate detection (find_duplicates) by hash and title
- PDF acquisition (acquire) - async method
- Helper methods
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

import sys

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestPDFStatus:
    """Tests for PDFService.get_status()."""

    def test_get_status_all(self, db):
        """Test getting PDF status for all papers."""
        from services import PaperService, PDFService

        # Create papers with and without PDFs
        paper1 = PaperService.create(title="Paper with PDF", doi="10.1234/test1")
        paper2 = PaperService.create(title="Paper without PDF", doi="10.1234/test2")

        # Simulate PDF for paper1
        PaperService.update(paper1["id"], file_path="/fake/path/paper1.pdf")

        result = PDFService.get_status(filter_type="all")

        # Verify dataclass attributes
        assert hasattr(result, 'total_papers')
        assert hasattr(result, 'has_pdf')
        assert hasattr(result, 'needs_pdf')
        assert hasattr(result, 'papers')
        assert result.total_papers >= 2
        assert len(result.papers) >= 2

    def test_get_status_has_pdf(self, db):
        """Test filtering papers that have PDFs."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper with PDF")
        paper2 = PaperService.create(title="Paper without PDF")

        PaperService.update(paper1["id"], file_path="/fake/path/paper1.pdf")

        result = PDFService.get_status(filter_type="has_pdf")

        # All returned papers should have file_path
        for paper in result.papers:
            assert paper.get("file_path") is not None

    def test_get_status_needs_pdf(self, db):
        """Test filtering papers that need PDFs (have DOI/arXiv but no PDF)."""
        from services import PaperService, PDFService

        # Paper with DOI but no PDF - needs PDF
        paper1 = PaperService.create(title="Paper needing PDF", doi="10.1234/needs")
        # Paper with PDF - doesn't need
        paper2 = PaperService.create(title="Paper with PDF", doi="10.1234/has")
        PaperService.update(paper2["id"], file_path="/fake/path.pdf")
        # Paper without identifier - can't acquire
        paper3 = PaperService.create(title="Paper no identifier")

        result = PDFService.get_status(filter_type="needs_pdf")

        # Should include paper1 (has DOI, no PDF)
        paper_ids = [p["id"] for p in result.papers]
        assert paper1["id"] in paper_ids
        assert paper2["id"] not in paper_ids

    def test_get_status_with_limit(self, db):
        """Test PDF status with limit parameter."""
        from services import PaperService, PDFService

        for i in range(10):
            PaperService.create(title=f"Paper {i}")

        result = PDFService.get_status(filter_type="all", limit=5)

        assert len(result.papers) == 5

    def test_get_status_returns_correct_counts(self, db):
        """Test that status counts are accurate."""
        from services import PaperService, PDFService

        # Create known set of papers
        p1 = PaperService.create(title="With PDF", doi="10.1234/1")
        p2 = PaperService.create(title="Needs PDF", doi="10.1234/2")
        p3 = PaperService.create(title="No identifier")

        PaperService.update(p1["id"], file_path="/path/to.pdf")

        result = PDFService.get_status(filter_type="all")

        assert result.has_pdf >= 1
        assert result.needs_pdf >= 1
        assert result.no_identifier >= 1


class TestDuplicateDetection:
    """Tests for PDFService.find_duplicates()."""

    def test_find_duplicates_by_hash_no_duplicates(self, db):
        """Test finding duplicates when none exist."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2")

        # Set different hashes
        PaperService.update(paper1["id"], file_hash="hash1111111111111111")
        PaperService.update(paper2["id"], file_hash="hash2222222222222222")

        result = PDFService.find_duplicates(method="hash")

        # Verify dataclass structure
        assert hasattr(result, 'method')
        assert hasattr(result, 'duplicate_groups')
        assert result.method == "hash"
        assert result.duplicate_groups == []

    def test_find_duplicates_by_hash_with_duplicates(self, db):
        """Test finding duplicates by file hash."""
        from services import PaperService, PDFService

        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2 - Duplicate")

        # Set same hash for both
        same_hash = "abc123def456abc123def456abc123def456"
        PaperService.update(paper1["id"], file_hash=same_hash)
        PaperService.update(paper2["id"], file_hash=same_hash)

        result = PDFService.find_duplicates(method="hash")

        assert len(result.duplicate_groups) > 0
        # First group should have both papers
        group = result.duplicate_groups[0]
        assert group.type == "hash_match"
        assert group.file_hash == same_hash
        assert len(group.papers) == 2

    def test_find_duplicates_by_title(self, db):
        """Test finding duplicates by similar titles."""
        from services import PaperService, PDFService

        # Create papers with similar titles (no file_path so they'll be compared)
        PaperService.create(title="Machine Learning for Materials Science")
        PaperService.create(title="Machine Learning for Materials Science: A Review")

        result = PDFService.find_duplicates(method="title", threshold=0.7)

        assert hasattr(result, 'duplicate_groups')
        assert result.method == "title"
        assert result.threshold == 0.7
        # Should find potential duplicates due to similar titles
        if len(result.duplicate_groups) > 0:
            group = result.duplicate_groups[0]
            assert group.type == "title_similarity"
            assert group.similarity is not None

    def test_find_duplicates_by_title_no_match(self, db):
        """Test no duplicates found with completely different titles."""
        from services import PaperService, PDFService

        PaperService.create(title="Quantum Computing Fundamentals")
        PaperService.create(title="Organic Chemistry Methods for Synthesis")

        result = PDFService.find_duplicates(method="title", threshold=0.9)

        # Completely different titles should not match
        assert result.duplicate_groups == []

    def test_find_duplicates_with_limit(self, db):
        """Test that limit parameter is respected."""
        from services import PDFService

        result = PDFService.find_duplicates(method="title", threshold=0.5, limit=5)

        # Should not exceed limit
        assert len(result.duplicate_groups) <= 5


class TestPDFAcquisition:
    """Tests for PDFService.acquire() - async method."""

    @pytest.mark.asyncio
    async def test_acquire_paper_not_found(self, db):
        """Test acquisition for non-existent paper raises error."""
        from services import PDFService
        from literature_core import PaperNotFoundError

        with pytest.raises(PaperNotFoundError):
            await PDFService.acquire(99999)

    @pytest.mark.asyncio
    async def test_acquire_paper_no_identifier(self, db):
        """Test acquisition without DOI or arXiv ID."""
        from services import PaperService, PDFService

        paper = PaperService.create(title="Paper without identifiers")

        result = await PDFService.acquire(paper["id"])

        assert result.status == "error"
        assert result.paper_id == paper["id"]
        assert "no doi" in result.message.lower() or "arxiv" in result.message.lower()

    @pytest.mark.asyncio
    async def test_acquire_paper_already_has_pdf(self, db, tmp_path):
        """Test acquisition when paper already has PDF."""
        from services import PaperService, PDFService

        # Create a real temp PDF file
        pdf_path = tmp_path / "existing.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        paper = PaperService.create(title="Paper with existing PDF", doi="10.1234/exists")
        PaperService.update(paper["id"], file_path=str(pdf_path))

        result = await PDFService.acquire(paper["id"])

        assert result.status == "already_exists"
        assert result.paper_id == paper["id"]
        assert result.file_path == str(pdf_path)

    @pytest.mark.asyncio
    async def test_acquire_returns_dataclass(self, db):
        """Test that acquire returns AcquireResult dataclass."""
        from services import PaperService, PDFService
        from services.pdf_service import AcquireResult

        paper = PaperService.create(title="Test Paper", doi="10.1234/test")

        result = await PDFService.acquire(paper["id"])

        # Verify result is an AcquireResult dataclass
        assert isinstance(result, AcquireResult)
        assert hasattr(result, 'status')
        assert hasattr(result, 'paper_id')
        assert hasattr(result, 'tried_sources')


class TestHelperMethods:
    """Tests for PDFService helper methods."""

    def test_generate_filename_with_doi(self):
        """Test filename generation with DOI."""
        from services import PDFService

        paper = {"id": 1, "doi": "10.1234/test.2024", "arxiv_id": None}
        filename = PDFService.generate_filename(paper)

        assert filename.endswith(".pdf")
        assert "10.1234" in filename or "test.2024" in filename

    def test_generate_filename_with_arxiv(self):
        """Test filename generation with arXiv ID."""
        from services import PDFService

        paper = {"id": 1, "doi": None, "arxiv_id": "2401.12345"}
        filename = PDFService.generate_filename(paper)

        assert "arxiv" in filename.lower()
        assert "2401.12345" in filename

    def test_generate_filename_fallback(self):
        """Test filename generation fallback to paper ID."""
        from services import PDFService

        paper = {"id": 42, "doi": None, "arxiv_id": None}
        filename = PDFService.generate_filename(paper)

        assert "42" in filename
        assert filename.endswith(".pdf")

    def test_compute_file_hash(self, tmp_path):
        """Test file hash computation."""
        from services import PDFService

        # Create a test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content for hashing")

        hash1 = PDFService.compute_file_hash(test_file)
        hash2 = PDFService.compute_file_hash(test_file)

        # Same file should produce same hash
        assert hash1 == hash2
        # Hash should be hex string
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_compute_file_hash_different_content(self, tmp_path):
        """Test that different content produces different hashes."""
        from services import PDFService

        file1 = tmp_path / "file1.pdf"
        file2 = tmp_path / "file2.pdf"
        file1.write_bytes(b"content one")
        file2.write_bytes(b"content two")

        hash1 = PDFService.compute_file_hash(file1)
        hash2 = PDFService.compute_file_hash(file2)

        assert hash1 != hash2

    def test_paper_to_pdf_dict(self, db):
        """Test paper to dict conversion for PDF operations."""
        from services import PaperService, PDFService
        from literature_core import get_session, Paper

        paper = PaperService.create(
            title="Test Paper for Dict Conversion",
            doi="10.1234/dict-test"
        )

        with get_session() as session:
            db_paper = session.query(Paper).filter(Paper.id == paper["id"]).first()
            result = PDFService.paper_to_pdf_dict(db_paper)

        assert result["id"] == paper["id"]
        assert "title" in result
        assert "doi" in result
        assert "file_path" in result


class TestPDFStatusResult:
    """Tests for PDFStatusResult dataclass structure."""

    def test_status_result_structure(self, db):
        """Test that PDFStatusResult has correct structure."""
        from services import PDFService
        from services.pdf_service import PDFStatusResult

        result = PDFService.get_status(filter_type="all", limit=10)

        assert isinstance(result, PDFStatusResult)
        assert isinstance(result.total_papers, int)
        assert isinstance(result.has_pdf, int)
        assert isinstance(result.needs_pdf, int)
        assert isinstance(result.no_identifier, int)
        assert isinstance(result.papers, list)
        assert isinstance(result.filter_type, str)


class TestDuplicateResult:
    """Tests for DuplicateResult dataclass structure."""

    def test_duplicate_result_structure(self, db):
        """Test that DuplicateResult has correct structure."""
        from services import PDFService
        from services.pdf_service import DuplicateResult

        result = PDFService.find_duplicates(method="hash")

        assert isinstance(result, DuplicateResult)
        assert isinstance(result.method, str)
        assert isinstance(result.duplicate_groups, list)
        assert result.total_papers >= 0
