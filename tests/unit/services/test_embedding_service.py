"""Unit tests for EmbeddingService.

Tests cover:
- Embedding status reporting
- Queue processing for papers needing embeddings
- Single paper embedding generation
"""
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from services.embedding_service import EmbeddingService, EmbeddingStatus, EmbeddingResult
from services.paper_service import PaperService
from literature_core import get_session, Paper


class TestEmbeddingStatus:
    """Tests for EmbeddingStatus dataclass."""

    def test_status_defaults(self):
        """Test default values for EmbeddingStatus."""
        status = EmbeddingStatus()

        assert status.total_papers == 0
        assert status.papers_with_abstract == 0
        assert status.papers_with_full_text == 0
        assert status.paper_embeddings_count == 0
        assert status.chunk_embeddings_count == 0
        assert status.papers_needing_paper_embedding == 0
        assert status.papers_needing_chunk_embedding == 0

    def test_paper_coverage_percent_empty(self):
        """Test coverage percent with no papers."""
        status = EmbeddingStatus()
        # No papers with abstract means 100% coverage
        assert status.paper_coverage_percent == 100.0

    def test_paper_coverage_percent_calculation(self):
        """Test coverage percent calculation."""
        status = EmbeddingStatus(
            papers_with_abstract=100,
            paper_embeddings_count=75,
        )
        assert status.paper_coverage_percent == 75.0

    def test_chunk_coverage_percent_empty(self):
        """Test chunk coverage with no full text papers."""
        status = EmbeddingStatus()
        assert status.chunk_coverage_percent == 100.0

    def test_chunk_coverage_percent_calculation(self):
        """Test chunk coverage percent calculation."""
        status = EmbeddingStatus(
            papers_with_full_text=50,
            papers_with_chunks=40,
        )
        assert status.chunk_coverage_percent == 80.0


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_result_defaults(self):
        """Test default values for EmbeddingResult."""
        result = EmbeddingResult()

        assert result.papers_processed == 0
        assert result.chunks_created == 0
        assert result.paper_embeddings_created == 0
        assert result.errors == []

    def test_success_with_no_errors(self):
        """Test success is True when no errors."""
        result = EmbeddingResult(papers_processed=5)
        assert result.success is True

    def test_success_with_errors_but_progress(self):
        """Test success is True when there are errors but also progress."""
        result = EmbeddingResult(
            papers_processed=3,
            errors=["Error on paper 1"]
        )
        assert result.success is True

    def test_success_false_when_only_errors(self):
        """Test success is False when only errors and no progress."""
        result = EmbeddingResult(
            papers_processed=0,
            errors=["Error 1", "Error 2"]
        )
        assert result.success is False


class TestGetEmbeddingStatus:
    """Tests for EmbeddingService.get_embedding_status."""

    def test_get_status_empty_database(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test status with empty database."""
        status = EmbeddingService.get_embedding_status()

        assert status.total_papers == 0
        assert status.papers_with_abstract == 0
        assert status.papers_with_full_text == 0

    def test_get_status_with_papers(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test status counts papers correctly."""
        # Create papers with varying content
        PaperService.create(title="Paper 1", abstract="Abstract 1")
        paper2 = PaperService.create(title="Paper 2", abstract="Abstract 2")
        PaperService.create(title="Paper 3")  # No abstract or full text

        # Add chunks for paper2 (Paper.full_text column is deprecated)
        with get_session() as session:
            from literature_core import PaperChunk
            chunk = PaperChunk(
                paper_id=paper2["id"],
                chunk_order=0,
                content="Full text content chunk",
            )
            session.add(chunk)
            session.commit()

        status = EmbeddingService.get_embedding_status()

        assert status.total_papers == 3
        assert status.papers_with_abstract == 2
        assert status.papers_with_full_text == 1  # Paper with chunks

    def test_get_status_with_ids(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test status includes paper IDs when requested."""
        paper1 = PaperService.create(title="Paper 1", abstract="Abstract")
        paper2 = PaperService.create(title="Paper 2", abstract="Abstract")

        status = EmbeddingService.get_embedding_status(include_ids=True)

        # Papers need embeddings since mock store is empty
        assert len(status.paper_ids_needing_paper_embedding) == 2
        assert paper1["id"] in status.paper_ids_needing_paper_embedding
        assert paper2["id"] in status.paper_ids_needing_paper_embedding

    def test_get_status_counts_existing_embeddings(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test status counts existing embeddings."""
        paper = PaperService.create(title="Paper", abstract="Abstract")

        # Add embedding to mock store
        mock_vector_store.add(
            id=str(paper["id"]),
            embedding=np.ones(384),
            metadata={"paper_id": paper["id"]},
            document="Test"
        )

        status = EmbeddingService.get_embedding_status()

        assert status.paper_embeddings_count == 1
        assert status.papers_needing_paper_embedding == 0


class TestProcessQueue:
    """Tests for EmbeddingService.process_queue."""

    @pytest.mark.asyncio
    async def test_process_queue_empty(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test processing empty queue."""
        result = await EmbeddingService.process_queue()

        assert result.papers_processed == 0
        assert result.paper_embeddings_created == 0
        assert result.chunks_created == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_process_queue_creates_paper_embeddings(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test processing creates paper-level embeddings."""
        PaperService.create(title="Paper 1", abstract="Abstract about ALD")
        PaperService.create(title="Paper 2", abstract="Abstract about CVD")

        result = await EmbeddingService.process_queue(
            include_paper_embeddings=True,
            include_chunk_embeddings=False,
        )

        assert result.papers_processed == 2
        assert result.paper_embeddings_created == 2
        assert result.success is True

    @pytest.mark.asyncio
    async def test_process_queue_creates_chunk_embeddings(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test processing creates chunk-level embeddings."""
        paper = PaperService.create(
            title="Paper with full text",
            abstract="Short abstract",
        )

        # Add chunks for paper (Paper.full_text column is deprecated)
        with get_session() as session:
            from literature_core import PaperChunk
            full_text = "This is a longer full text that should be chunked. " * 20
            chunk = PaperChunk(
                paper_id=paper["id"],
                chunk_order=0,
                content=full_text,
            )
            session.add(chunk)
            session.commit()

        result = await EmbeddingService.process_queue(
            include_paper_embeddings=False,
            include_chunk_embeddings=True,
        )

        assert result.papers_processed >= 1
        assert result.chunks_created >= 1
        assert result.success is True

    @pytest.mark.asyncio
    async def test_process_queue_respects_limit(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test processing respects limit parameter."""
        for i in range(10):
            PaperService.create(title=f"Paper {i}", abstract=f"Abstract {i}")

        result = await EmbeddingService.process_queue(limit=3)

        assert result.papers_processed <= 3

    @pytest.mark.asyncio
    async def test_process_queue_skips_papers_with_embeddings(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test processing skips papers that already have embeddings."""
        paper1 = PaperService.create(title="Paper 1", abstract="Abstract 1")
        PaperService.create(title="Paper 2", abstract="Abstract 2")

        # Add embedding for paper1
        mock_vector_store.add(
            id=str(paper1["id"]),
            embedding=np.ones(384),
            metadata={"paper_id": paper1["id"]},
            document="Test"
        )

        result = await EmbeddingService.process_queue(
            include_paper_embeddings=True,
            include_chunk_embeddings=False,
        )

        # Only paper2 should be processed
        assert result.papers_processed == 1
        assert result.paper_embeddings_created == 1

    @pytest.mark.asyncio
    async def test_process_queue_handles_errors(
        self, db, mock_vector_store, mock_chunk_store
    ):
        """Test processing handles errors gracefully."""
        PaperService.create(title="Paper", abstract="Abstract")

        # Make embedding generation fail
        with patch('embeddings.generator.get_embedding_generator') as mock_gen:
            mock_gen.return_value.generate = MagicMock(
                side_effect=Exception("Embedding failed")
            )

            result = await EmbeddingService.process_queue()

        assert len(result.errors) >= 1
        assert "Embedding failed" in result.errors[0]


class TestEmbedPaper:
    """Tests for EmbeddingService.embed_paper."""

    @pytest.mark.asyncio
    async def test_embed_paper_not_found(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test embedding non-existent paper."""
        result = await EmbeddingService.embed_paper(paper_id=99999)

        assert result.papers_processed == 0
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_embed_paper_creates_paper_embedding(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test embedding creates paper-level embedding."""
        paper = PaperService.create(
            title="Test Paper",
            abstract="Test abstract about materials science"
        )

        result = await EmbeddingService.embed_paper(
            paper_id=paper["id"],
            include_paper_embedding=True,
            include_chunk_embedding=False,
        )

        assert result.papers_processed == 1
        assert result.paper_embeddings_created == 1
        assert result.success is True

    @pytest.mark.asyncio
    async def test_embed_paper_creates_chunk_embeddings(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test embedding creates chunk embeddings when full text available."""
        paper = PaperService.create(
            title="Test Paper",
            abstract="Short abstract",
        )

        # Add chunks for paper (Paper.full_text column is deprecated)
        with get_session() as session:
            from literature_core import PaperChunk
            full_text = "This is the full text of the paper. " * 50
            chunk = PaperChunk(
                paper_id=paper["id"],
                chunk_order=0,
                content=full_text,
            )
            session.add(chunk)
            session.commit()

        result = await EmbeddingService.embed_paper(
            paper_id=paper["id"],
            include_paper_embedding=False,
            include_chunk_embedding=True,
        )

        assert result.papers_processed == 1
        assert result.chunks_created >= 1
        assert result.success is True

    @pytest.mark.asyncio
    async def test_embed_paper_skips_without_abstract(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test paper embedding is skipped without abstract."""
        paper = PaperService.create(title="Paper without abstract")

        result = await EmbeddingService.embed_paper(
            paper_id=paper["id"],
            include_paper_embedding=True,
            include_chunk_embedding=False,
        )

        # Paper embedding skipped because no abstract
        assert result.paper_embeddings_created == 0

    @pytest.mark.asyncio
    async def test_embed_paper_skips_without_full_text(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test chunk embedding is skipped without full text."""
        paper = PaperService.create(
            title="Paper",
            abstract="Has abstract but no full text"
        )

        result = await EmbeddingService.embed_paper(
            paper_id=paper["id"],
            include_paper_embedding=False,
            include_chunk_embedding=True,
        )

        # Chunk embedding skipped because no full text
        assert result.chunks_created == 0

    @pytest.mark.asyncio
    async def test_embed_paper_both_types(
        self, db, mock_embedding_generator, mock_vector_store, mock_chunk_store
    ):
        """Test embedding creates both paper and chunk embeddings."""
        paper = PaperService.create(
            title="Complete Paper",
            abstract="Comprehensive abstract about the research",
        )

        # Add chunks for paper (Paper.full_text column is deprecated)
        with get_session() as session:
            from literature_core import PaperChunk
            full_text = "Full text content " * 100
            chunk = PaperChunk(
                paper_id=paper["id"],
                chunk_order=0,
                content=full_text,
            )
            session.add(chunk)
            session.commit()

        result = await EmbeddingService.embed_paper(
            paper_id=paper["id"],
            include_paper_embedding=True,
            include_chunk_embedding=True,
        )

        assert result.papers_processed == 1
        assert result.paper_embeddings_created == 1
        assert result.chunks_created >= 1
        assert result.success is True
