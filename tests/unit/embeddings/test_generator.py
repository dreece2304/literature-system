"""Unit tests for EmbeddingGenerator."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from tests.fixtures.mocks import MockEmbeddingGenerator


class TestMockEmbeddingGenerator:
    """Tests for MockEmbeddingGenerator (used in tests)."""

    def test_init_defaults(self):
        """Test default initialization."""
        gen = MockEmbeddingGenerator()

        assert gen.dimension == 384
        assert gen.normalize is True
        assert gen.device == "cpu"

    def test_init_custom_dimension(self):
        """Test initialization with custom dimension."""
        gen = MockEmbeddingGenerator(dimension=768)

        assert gen.dimension == 768

    def test_generate_single_text(self):
        """Test generating embedding for single text."""
        gen = MockEmbeddingGenerator()

        embedding = gen.generate("test text")

        assert embedding.shape == (384,)
        assert embedding.dtype == np.float32

    def test_generate_multiple_texts(self):
        """Test generating embeddings for multiple texts."""
        gen = MockEmbeddingGenerator()

        embeddings = gen.generate(["text1", "text2", "text3"])

        assert embeddings.shape == (3, 384)

    def test_generate_deterministic(self):
        """Test that same text produces same embedding."""
        gen = MockEmbeddingGenerator()

        emb1 = gen.generate("same text")
        emb2 = gen.generate("same text")

        np.testing.assert_array_almost_equal(emb1, emb2)

    def test_generate_different_texts_different_embeddings(self):
        """Test that different texts produce different embeddings."""
        gen = MockEmbeddingGenerator()

        emb1 = gen.generate("text one")
        emb2 = gen.generate("text two")

        assert not np.allclose(emb1, emb2)

    def test_generate_normalized(self):
        """Test that embeddings are L2 normalized."""
        gen = MockEmbeddingGenerator()

        embedding = gen.generate("test text")
        norm = np.linalg.norm(embedding)

        assert np.isclose(norm, 1.0)

    def test_generate_for_paper(self):
        """Test generating embedding for paper dict."""
        gen = MockEmbeddingGenerator()

        paper = {
            "title": "Test Paper",
            "abstract": "This is the abstract"
        }
        embedding = gen.generate_for_paper(paper)

        assert embedding.shape == (384,)

    def test_compute_similarity_identical(self):
        """Test similarity of identical embeddings is 1.0."""
        gen = MockEmbeddingGenerator()

        emb = gen.generate("test")
        similarity = gen.compute_similarity(emb, emb)

        assert np.isclose(similarity, 1.0)

    def test_compute_similarity_different(self):
        """Test similarity of different embeddings."""
        gen = MockEmbeddingGenerator()

        emb1 = gen.generate("cats are pets")
        emb2 = gen.generate("quantum physics equations")
        similarity = gen.compute_similarity(emb1, emb2)

        assert similarity < 1.0
        assert similarity > -1.0

    def test_compute_similarity_batch(self):
        """Test batch similarity computation."""
        gen = MockEmbeddingGenerator()

        query = gen.generate("query text")
        embeddings = gen.generate(["doc1", "doc2", "doc3"])
        similarities = gen.compute_similarity_batch(query, embeddings)

        assert similarities.shape == (3,)


class TestEmbeddingGeneratorMocking:
    """Tests for mocking the real EmbeddingGenerator."""

    def test_mock_embedding_generator_fixture(self, mock_embedding_generator):
        """Test the mock_embedding_generator fixture."""
        embedding = mock_embedding_generator.generate("test")

        assert embedding.shape == (384,)
        assert mock_embedding_generator.dimension == 384

    def test_mock_produces_consistent_results(self, mock_embedding_generator):
        """Test that mocked generator produces consistent results."""
        emb1 = mock_embedding_generator.generate("hello world")
        emb2 = mock_embedding_generator.generate("hello world")

        np.testing.assert_array_almost_equal(emb1, emb2)


class TestTextChunking:
    """Tests for text chunking functionality."""

    def test_chunk_short_text(self):
        """Test chunking text shorter than chunk size."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk_text("Short text", source_id="test")

        assert len(chunks) == 1
        assert chunks[0].text == "Short text"

    def test_chunk_long_text(self):
        """Test chunking text longer than chunk size."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        long_text = "This is a longer text. " * 10
        chunks = chunker.chunk_text(long_text, source_id="test")

        assert len(chunks) > 1

    def test_chunks_have_correct_metadata(self):
        """Test that chunks have correct metadata."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk_text(
            "Test text",
            source_id="paper_123",
            metadata={"title": "Test Paper"}
        )

        assert chunks[0].source_id == "paper_123"
        assert chunks[0].chunk_index == 0

    def test_chunks_have_positions(self):
        """Test that chunks have start/end positions."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 100
        chunks = chunker.chunk_text(text, source_id="test")

        for chunk in chunks:
            assert hasattr(chunk, 'start_pos')
            assert hasattr(chunk, 'end_pos')
            assert chunk.start_pos >= 0
            assert chunk.end_pos <= len(text)
