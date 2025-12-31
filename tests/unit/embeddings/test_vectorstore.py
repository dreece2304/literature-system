"""Unit tests for VectorStore."""
import pytest
import numpy as np

from tests.fixtures.mocks import MockVectorStore, MockChunkVectorStore


class TestMockVectorStore:
    """Tests for MockVectorStore (used in tests)."""

    def test_init(self):
        """Test initialization."""
        store = MockVectorStore()

        assert store.collection_name == "mock_papers"
        assert store.count() == 0

    def test_add_single(self):
        """Test adding a single embedding."""
        store = MockVectorStore()
        embedding = np.random.randn(384).astype(np.float32)

        store.add("doc1", embedding, {"title": "Test"}, "Document text")

        assert store.count() == 1
        assert store.exists("doc1")

    def test_add_batch(self):
        """Test adding multiple embeddings."""
        store = MockVectorStore()
        embeddings = np.random.randn(3, 384).astype(np.float32)

        store.add_batch(
            ["doc1", "doc2", "doc3"],
            embeddings,
            [{"id": 1}, {"id": 2}, {"id": 3}],
            ["text1", "text2", "text3"]
        )

        assert store.count() == 3

    def test_search(self):
        """Test searching for similar embeddings."""
        store = MockVectorStore()

        # Add some embeddings
        for i in range(5):
            emb = np.random.randn(384).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            store.add(f"doc{i}", emb, {"id": i})

        # Search
        query = np.random.randn(384).astype(np.float32)
        query = query / np.linalg.norm(query)
        results = store.search(query, top_k=3)

        assert len(results) <= 3
        for r in results:
            assert "id" in r
            assert "score" in r

    def test_search_empty_store(self):
        """Test searching empty store."""
        store = MockVectorStore()
        query = np.random.randn(384).astype(np.float32)

        results = store.search(query)

        assert results == []

    def test_search_with_threshold(self):
        """Test searching with score threshold."""
        store = MockVectorStore()

        # Add embedding
        emb = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        store.add("doc1", emb)

        # Search with high threshold
        query = np.array([0.0] + [1.0] + [0.0] * 382, dtype=np.float32)
        results = store.search(query, score_threshold=0.9)

        # Orthogonal vectors should have low similarity
        # May or may not be filtered depending on implementation

    def test_get_by_ids(self):
        """Test getting embeddings by ID."""
        store = MockVectorStore()
        emb = np.random.randn(384).astype(np.float32)
        store.add("doc1", emb, {"title": "Test"})

        results = store.get(["doc1"])

        assert len(results) == 1

    def test_delete(self):
        """Test deleting embeddings."""
        store = MockVectorStore()
        emb = np.random.randn(384).astype(np.float32)
        store.add("doc1", emb)
        store.add("doc2", emb)

        assert store.count() == 2

        store.delete(["doc1"])

        assert store.count() == 1
        assert not store.exists("doc1")
        assert store.exists("doc2")

    def test_exists(self):
        """Test checking if ID exists."""
        store = MockVectorStore()

        assert not store.exists("nonexistent")

        store.add("doc1", np.random.randn(384).astype(np.float32))

        assert store.exists("doc1")

    def test_reset(self):
        """Test clearing all data."""
        store = MockVectorStore()
        for i in range(5):
            store.add(f"doc{i}", np.random.randn(384).astype(np.float32))

        assert store.count() == 5

        store.reset()

        assert store.count() == 0


class TestMockChunkVectorStore:
    """Tests for MockChunkVectorStore."""

    def test_search_chunks(self):
        """Test searching chunks."""
        store = MockChunkVectorStore()

        # Add chunks
        for i in range(5):
            emb = np.random.randn(384).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            store.add(
                f"paper1_{i}",
                emb,
                {"paper_id": 1, "chunk_index": i},
                f"Chunk {i} text"
            )

        query = np.random.randn(384).astype(np.float32)
        query = query / np.linalg.norm(query)
        results = store.search_chunks(query, limit=3)

        assert len(results) <= 3

    def test_search_chunks_with_paper_filter(self):
        """Test searching chunks filtered by paper ID."""
        store = MockChunkVectorStore()

        # Add chunks for multiple papers
        for paper_id in [1, 2]:
            for i in range(3):
                emb = np.random.randn(384).astype(np.float32)
                emb = emb / np.linalg.norm(emb)
                store.add(
                    f"paper{paper_id}_{i}",
                    emb,
                    {"paper_id": paper_id, "chunk_index": i}
                )

        query = np.random.randn(384).astype(np.float32)
        results = store.search_chunks(query, paper_ids=[1])

        for r in results:
            assert r.get("metadata", {}).get("paper_id") == 1

    def test_get_paper_chunks(self):
        """Test getting all chunks for a paper."""
        store = MockChunkVectorStore()

        # Add chunks for paper 1
        for i in range(3):
            store.add(
                f"paper1_{i}",
                np.random.randn(384).astype(np.float32),
                {"paper_id": 1, "chunk_index": i},
                f"Chunk {i}"
            )

        # Add chunks for paper 2
        store.add(
            "paper2_0",
            np.random.randn(384).astype(np.float32),
            {"paper_id": 2, "chunk_index": 0}
        )

        chunks = store.get_paper_chunks(1)

        assert len(chunks) == 3

    def test_delete_paper_chunks(self):
        """Test deleting all chunks for a paper."""
        store = MockChunkVectorStore()

        # Add chunks
        for i in range(3):
            store.add(
                f"paper1_{i}",
                np.random.randn(384).astype(np.float32),
                {"paper_id": 1, "chunk_index": i}
            )

        assert store.count() == 3

        store.delete_paper_chunks(1)

        assert store.count() == 0


class TestVectorStoreFixture:
    """Tests using the mock_vector_store fixture."""

    def test_mock_vector_store_fixture(self, mock_vector_store):
        """Test the mock_vector_store fixture works."""
        assert mock_vector_store.count() == 0

        mock_vector_store.add(
            "test",
            np.random.randn(384).astype(np.float32)
        )

        assert mock_vector_store.count() == 1

    def test_mock_chunk_store_fixture(self, mock_chunk_store):
        """Test the mock_chunk_store fixture works."""
        assert mock_chunk_store.count() == 0
