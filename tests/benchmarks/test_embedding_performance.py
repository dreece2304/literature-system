"""Performance benchmarks for embedding operations.

Tests measure:
- Embedding generation time
- Batch vs single embedding
- Vector similarity computation
"""
import pytest
import time
import numpy as np
from typing import Callable

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class Timer:
    """Simple context manager for timing operations."""

    def __init__(self):
        self.elapsed = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start


def measure_time(func: Callable, iterations: int = 1) -> float:
    """Measure average execution time over multiple iterations."""
    total = 0
    for _ in range(iterations):
        with Timer() as t:
            func()
        total += t.elapsed
    return total / iterations


@pytest.mark.slow
class TestMockEmbeddingGeneration:
    """Benchmark mock embedding generation (CPU-based)."""

    def test_single_embedding_generation(self, mock_embedding_generator):
        """Benchmark single text embedding generation."""
        text = "This is a test sentence for embedding generation."

        avg_time = measure_time(
            lambda: mock_embedding_generator.generate(text),
            iterations=100
        )

        print(f"\nSingle embedding generation: {avg_time*1000:.3f}ms")
        assert avg_time < 0.1  # Mock should be fast

    def test_batch_embedding_generation(self, mock_embedding_generator):
        """Benchmark batch embedding generation."""
        texts = [f"Test sentence number {i} for batch embedding." for i in range(10)]

        avg_time = measure_time(
            lambda: mock_embedding_generator.generate(texts),
            iterations=20
        )

        print(f"\nBatch embedding (10 texts): {avg_time*1000:.3f}ms")
        assert avg_time < 0.5

    def test_large_batch_embedding(self, mock_embedding_generator):
        """Benchmark large batch embedding generation."""
        texts = [f"Test sentence {i} with more content for larger batches." for i in range(100)]

        avg_time = measure_time(
            lambda: mock_embedding_generator.generate(texts),
            iterations=5
        )

        print(f"\nLarge batch embedding (100 texts): {avg_time*1000:.3f}ms")
        assert avg_time < 2.0

    def test_paper_embedding_generation(self, mock_embedding_generator):
        """Benchmark paper embedding generation."""
        paper = {
            "title": "Machine Learning for Materials Science",
            "abstract": "This paper presents a novel approach to materials discovery using neural networks. " * 5
        }

        avg_time = measure_time(
            lambda: mock_embedding_generator.generate_for_paper(paper),
            iterations=50
        )

        print(f"\nPaper embedding generation: {avg_time*1000:.3f}ms")
        assert avg_time < 0.1


@pytest.mark.slow
class TestSimilarityComputation:
    """Benchmark similarity computation."""

    def test_pairwise_similarity(self, mock_embedding_generator):
        """Benchmark pairwise similarity computation."""
        emb1 = mock_embedding_generator.generate("First text")
        emb2 = mock_embedding_generator.generate("Second text")

        avg_time = measure_time(
            lambda: mock_embedding_generator.compute_similarity(emb1, emb2),
            iterations=1000
        )

        print(f"\nPairwise similarity: {avg_time*1000000:.3f}us")
        assert avg_time < 0.001  # Should be microseconds

    def test_batch_similarity(self, mock_embedding_generator):
        """Benchmark batch similarity computation."""
        query = mock_embedding_generator.generate("Query text")
        corpus = mock_embedding_generator.generate([f"Document {i}" for i in range(100)])

        avg_time = measure_time(
            lambda: mock_embedding_generator.compute_similarity_batch(query, corpus),
            iterations=100
        )

        print(f"\nBatch similarity (100 docs): {avg_time*1000:.3f}ms")
        assert avg_time < 0.1


@pytest.mark.slow
class TestVectorStoreOperations:
    """Benchmark vector store operations."""

    def test_single_add(self, mock_vector_store, mock_embedding_generator):
        """Benchmark adding single embedding."""
        def add_one():
            emb = mock_embedding_generator.generate("Test document")
            mock_vector_store.add("test_id", emb, {"key": "value"})

        avg_time = measure_time(add_one, iterations=100)

        print(f"\nSingle add: {avg_time*1000:.3f}ms")
        assert avg_time < 0.01

    def test_batch_add(self, mock_vector_store, mock_embedding_generator):
        """Benchmark batch add."""
        def add_batch():
            texts = [f"Document {i}" for i in range(50)]
            embeddings = mock_embedding_generator.generate(texts)
            ids = [f"doc_{i}" for i in range(50)]
            metadatas = [{"index": i} for i in range(50)]
            mock_vector_store.add_batch(ids, embeddings, metadatas)

        avg_time = measure_time(add_batch, iterations=10)

        print(f"\nBatch add (50 docs): {avg_time*1000:.3f}ms")
        assert avg_time < 1.0

    def test_search(self, mock_vector_store, mock_embedding_generator):
        """Benchmark search operation."""
        # Populate store
        for i in range(100):
            emb = mock_embedding_generator.generate(f"Document {i}")
            mock_vector_store.add(f"doc_{i}", emb, {"index": i})

        query = mock_embedding_generator.generate("Query text")

        avg_time = measure_time(
            lambda: mock_vector_store.search(query, top_k=10),
            iterations=50
        )

        print(f"\nSearch (100 docs, top 10): {avg_time*1000:.3f}ms")
        assert avg_time < 0.5

    def test_search_scaling(self, mock_vector_store, mock_embedding_generator):
        """Benchmark search scaling with corpus size."""
        # Add 500 documents
        for i in range(500):
            emb = mock_embedding_generator.generate(f"Large corpus document {i}")
            mock_vector_store.add(f"doc_{i}", emb, {"index": i})

        query = mock_embedding_generator.generate("Query text for large corpus")

        avg_time = measure_time(
            lambda: mock_vector_store.search(query, top_k=10),
            iterations=20
        )

        print(f"\nSearch (500 docs, top 10): {avg_time*1000:.3f}ms")
        assert avg_time < 5.0


@pytest.mark.slow
class TestChunkStoreOperations:
    """Benchmark chunk vector store operations."""

    def test_chunk_search(self, mock_chunk_store, mock_embedding_generator):
        """Benchmark chunk search."""
        # Add chunks for multiple papers
        for paper_id in range(5):
            for chunk_idx in range(10):
                emb = mock_embedding_generator.generate(
                    f"Paper {paper_id} chunk {chunk_idx} content"
                )
                mock_chunk_store.add(
                    f"p{paper_id}_c{chunk_idx}",
                    emb,
                    {"paper_id": paper_id, "chunk_index": chunk_idx},
                    f"Chunk text {chunk_idx}"
                )

        query = mock_embedding_generator.generate("Query for chunk search")

        avg_time = measure_time(
            lambda: mock_chunk_store.search_chunks(query, limit=10),
            iterations=20
        )

        print(f"\nChunk search (50 chunks): {avg_time*1000:.3f}ms")
        assert avg_time < 1.0

    def test_chunk_search_with_paper_filter(self, mock_chunk_store, mock_embedding_generator):
        """Benchmark chunk search with paper ID filter."""
        # Add chunks
        for paper_id in range(10):
            for chunk_idx in range(10):
                emb = mock_embedding_generator.generate(
                    f"Paper {paper_id} chunk {chunk_idx}"
                )
                mock_chunk_store.add(
                    f"p{paper_id}_c{chunk_idx}",
                    emb,
                    {"paper_id": paper_id, "chunk_index": chunk_idx}
                )

        query = mock_embedding_generator.generate("Filtered query")

        avg_time = measure_time(
            lambda: mock_chunk_store.search_chunks(query, limit=10, paper_ids=[1, 2, 3]),
            iterations=20
        )

        print(f"\nFiltered chunk search: {avg_time*1000:.3f}ms")
        assert avg_time < 1.0

    def test_get_paper_chunks(self, mock_chunk_store, mock_embedding_generator):
        """Benchmark getting all chunks for a paper."""
        # Add chunks
        for paper_id in range(5):
            for chunk_idx in range(20):
                emb = mock_embedding_generator.generate(f"P{paper_id}C{chunk_idx}")
                mock_chunk_store.add(
                    f"p{paper_id}_c{chunk_idx}",
                    emb,
                    {"paper_id": paper_id, "chunk_index": chunk_idx}
                )

        avg_time = measure_time(
            lambda: mock_chunk_store.get_paper_chunks(2),
            iterations=20
        )

        print(f"\nGet paper chunks (20 chunks): {avg_time*1000:.3f}ms")
        assert avg_time < 0.5
