"""Unit tests for ExtractionService.

Tests cover:
- Extraction status reporting
- Queue management for papers needing extraction
- LLM client availability
- Single paper extraction
- Batch extraction processing
"""
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from services.extraction_service import (
    ExtractionService,
    ExtractionStatus,
    ExtractionResult,
    PaperExtraction,
    OllamaClient,
    ClaudeClient,
)
from services.paper_service import PaperService
from literature_core import get_session, Paper, PaperContent


class TestExtractionStatus:
    """Tests for ExtractionStatus dataclass."""

    def test_status_defaults(self):
        """Test default values for ExtractionStatus."""
        status = ExtractionStatus()

        assert status.total_papers == 0
        assert status.papers_with_extraction == 0
        assert status.papers_needing_extraction == 0

    def test_extraction_coverage_empty(self):
        """Test coverage percent with no papers."""
        status = ExtractionStatus()
        assert status.extraction_coverage_percent == 100.0

    def test_extraction_coverage_calculation(self):
        """Test coverage percent calculation."""
        status = ExtractionStatus(
            papers_with_full_text=100,
            papers_with_extraction=75,
        )
        assert status.extraction_coverage_percent == 75.0


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_result_defaults(self):
        """Test default values for ExtractionResult."""
        result = ExtractionResult()

        assert result.papers_processed == 0
        assert result.papers_extracted == 0
        assert result.papers_skipped == 0
        assert result.papers_error == 0
        assert result.errors == []

    def test_success_with_no_errors(self):
        """Test success is True when no errors."""
        result = ExtractionResult(papers_processed=5)
        assert result.success is True

    def test_success_false_when_only_errors(self):
        """Test success is False when only errors and no progress."""
        result = ExtractionResult(
            papers_processed=0,
            errors=["Error 1"]
        )
        assert result.success is False


class TestGetExtractionStatus:
    """Tests for ExtractionService.get_extraction_status."""

    def test_get_status_empty_database(self, db):
        """Test status with empty database."""
        status = ExtractionService.get_extraction_status()

        assert status.total_papers == 0
        assert status.papers_with_extraction == 0

    def test_get_status_with_papers(self, db):
        """Test status counts papers correctly."""
        # Create papers with different content
        p1 = PaperService.create(title="Paper 1", abstract="Abstract 1")
        p2 = PaperService.create(title="Paper 2", abstract="Abstract 2")
        PaperService.create(title="Paper 3")  # No abstract

        # Add full text to one paper
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == p1["id"]).first()
            paper.full_text = "Full text content"
            session.commit()

        # Add extraction to one paper
        with get_session() as session:
            content = PaperContent(
                paper_id=p2["id"],
                one_sentence_summary="Test summary"
            )
            session.add(content)
            session.commit()

        status = ExtractionService.get_extraction_status()

        assert status.total_papers == 3
        assert status.papers_with_full_text == 1
        assert status.papers_with_abstract == 2
        assert status.papers_with_extraction == 1


class TestGetPapersNeedingExtraction:
    """Tests for ExtractionService.get_papers_needing_extraction."""

    def test_get_queue_empty(self, db):
        """Test empty queue when all papers have extractions."""
        p = PaperService.create(title="Paper", abstract="Abstract")

        with get_session() as session:
            content = PaperContent(paper_id=p["id"], one_sentence_summary="Summary")
            session.add(content)
            session.commit()

        queue = ExtractionService.get_papers_needing_extraction()
        assert len(queue) == 0

    def test_get_queue_returns_papers_with_content(self, db):
        """Test queue returns papers with abstract or full text."""
        p1 = PaperService.create(title="With Abstract", abstract="Abstract")
        PaperService.create(title="No Content")  # Should not appear

        queue = ExtractionService.get_papers_needing_extraction()

        assert len(queue) == 1
        assert queue[0]["id"] == p1["id"]

    def test_get_queue_prioritizes_full_text(self, db):
        """Test queue prioritizes papers with full text."""
        p_abstract = PaperService.create(title="Abstract Only", abstract="Abstract")
        p_full = PaperService.create(title="Full Text", abstract="Abstract")

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == p_full["id"]).first()
            paper.full_text = "Full text content"
            session.commit()

        queue = ExtractionService.get_papers_needing_extraction(prioritize_full_text=True)

        # Paper with full text should be first
        assert queue[0]["has_full_text"] is True

    def test_get_queue_respects_limit(self, db):
        """Test queue respects limit parameter."""
        for i in range(10):
            PaperService.create(title=f"Paper {i}", abstract=f"Abstract {i}")

        queue = ExtractionService.get_papers_needing_extraction(limit=3)
        assert len(queue) == 3


class TestGetLlmStatus:
    """Tests for ExtractionService.get_llm_status."""

    def test_get_llm_status_format(self, db):
        """Test LLM status returns expected format."""
        with patch.object(OllamaClient, 'is_available', return_value=True):
            with patch.object(ClaudeClient, 'is_available', return_value=False):
                status = ExtractionService.get_llm_status()

        assert "ollama" in status
        assert "claude" in status
        assert "recommended" in status
        assert status["ollama"]["available"] is True
        assert status["claude"]["available"] is False
        assert status["recommended"] == "ollama"

    def test_get_llm_status_no_backends(self, db):
        """Test status when no backends available."""
        with patch.object(OllamaClient, 'is_available', return_value=False):
            with patch.object(ClaudeClient, 'is_available', return_value=False):
                status = ExtractionService.get_llm_status()

        assert status["recommended"] is None


class TestOllamaClient:
    """Tests for OllamaClient."""

    def test_parse_extraction_valid_json(self):
        """Test parsing valid JSON extraction."""
        client = OllamaClient()
        json_text = '''
        {
            "paper_type": "research_article",
            "topics": ["machine learning", "NLP"],
            "one_sentence_summary": "A study on NLP.",
            "key_findings": ["Finding 1", "Finding 2"],
            "methodology_summary": "Used transformers."
        }
        '''

        result = client._parse_extraction(json_text, paper_id=1)

        assert result.success is True
        assert result.paper_type == "research_article"
        assert len(result.topics) == 2
        assert result.one_sentence_summary == "A study on NLP."

    def test_parse_extraction_with_code_blocks(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        client = OllamaClient()
        json_text = '''```json
        {
            "paper_type": "review",
            "topics": ["AI"],
            "one_sentence_summary": "A review.",
            "key_findings": [],
            "methodology_summary": "Literature review."
        }
        ```'''

        result = client._parse_extraction(json_text, paper_id=1)

        assert result.success is True
        assert result.paper_type == "review"

    def test_parse_extraction_invalid_json(self):
        """Test parsing invalid JSON returns error."""
        client = OllamaClient()
        invalid_text = "This is not JSON"

        result = client._parse_extraction(invalid_text, paper_id=1)

        assert result.success is False
        assert "JSON parse error" in result.error


class TestExtractPaper:
    """Tests for ExtractionService.extract_paper."""

    @pytest.mark.asyncio
    async def test_extract_paper_not_found(self, db):
        """Test extracting non-existent paper."""
        result = await ExtractionService.extract_paper(99999)

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_extract_paper_no_content(self, db):
        """Test extracting paper without abstract or full text."""
        paper = PaperService.create(title="Empty Paper")

        result = await ExtractionService.extract_paper(paper["id"])

        assert result.success is False
        assert "no abstract or full text" in result.error

    @pytest.mark.asyncio
    async def test_extract_paper_already_extracted(self, db):
        """Test extracting paper that already has extraction."""
        paper = PaperService.create(title="Paper", abstract="Abstract")

        with get_session() as session:
            content = PaperContent(
                paper_id=paper["id"],
                one_sentence_summary="Existing summary",
                extractor_model="test"
            )
            session.add(content)
            session.commit()

        result = await ExtractionService.extract_paper(paper["id"])

        assert result.success is True
        assert "Already extracted" in result.error

    @pytest.mark.asyncio
    async def test_extract_paper_force_reextract(self, db):
        """Test force re-extraction."""
        paper = PaperService.create(title="Paper", abstract="Test abstract")

        with get_session() as session:
            content = PaperContent(
                paper_id=paper["id"],
                one_sentence_summary="Old summary"
            )
            session.add(content)
            session.commit()

        mock_extraction = PaperExtraction(
            paper_id=paper["id"],
            paper_type="research_article",
            topics=["test"],
            one_sentence_summary="New summary",
            success=True
        )

        with patch.object(OllamaClient, 'is_available', return_value=True):
            with patch.object(
                OllamaClient, 'extract',
                new_callable=AsyncMock,
                return_value=mock_extraction
            ):
                result = await ExtractionService.extract_paper(
                    paper["id"],
                    force=True
                )

        assert result.success is True
        assert result.one_sentence_summary == "New summary"

    @pytest.mark.asyncio
    async def test_extract_paper_no_backend(self, db):
        """Test extraction when no LLM backend available."""
        paper = PaperService.create(title="Paper", abstract="Abstract")

        with patch.object(OllamaClient, 'is_available', return_value=False):
            with patch.object(ClaudeClient, 'is_available', return_value=False):
                result = await ExtractionService.extract_paper(paper["id"])

        assert result.success is False
        assert "No LLM backend" in result.error


class TestExtractBatch:
    """Tests for ExtractionService.extract_batch."""

    @pytest.mark.asyncio
    async def test_extract_batch_empty(self, db):
        """Test batch extraction with no papers."""
        result = await ExtractionService.extract_batch(paper_ids=[])

        assert result.papers_processed == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_extract_batch_from_queue(self, db):
        """Test batch extraction processes from queue."""
        PaperService.create(title="Paper 1", abstract="Abstract 1")
        PaperService.create(title="Paper 2", abstract="Abstract 2")

        mock_extraction = PaperExtraction(
            paper_id=1,
            success=True,
            one_sentence_summary="Summary"
        )

        with patch.object(
            ExtractionService, 'extract_paper',
            new_callable=AsyncMock,
            return_value=mock_extraction
        ):
            result = await ExtractionService.extract_batch(limit=2, delay=0)

        assert result.papers_processed == 2


class TestDeleteExtraction:
    """Tests for ExtractionService.delete_extraction."""

    def test_delete_extraction_success(self, db):
        """Test deleting existing extraction."""
        paper = PaperService.create(title="Paper", abstract="Abstract")

        with get_session() as session:
            content = PaperContent(
                paper_id=paper["id"],
                one_sentence_summary="Summary"
            )
            session.add(content)
            session.commit()

        result = ExtractionService.delete_extraction(paper["id"])

        assert result is True

        # Verify deleted
        with get_session() as session:
            content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper["id"]
            ).first()
            assert content is None

    def test_delete_extraction_not_found(self, db):
        """Test deleting non-existent extraction."""
        paper = PaperService.create(title="Paper")

        result = ExtractionService.delete_extraction(paper["id"])

        assert result is False
