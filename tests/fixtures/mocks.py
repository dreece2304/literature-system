"""Mock fixtures for external dependencies.

Provides mocks for:
- Embedding generator (sentence-transformers)
- Vector store (ChromaDB)
"""
from unittest.mock import MagicMock
import numpy as np


class MockEmbeddingGenerator:
    """Mock for EmbeddingGenerator that produces deterministic embeddings."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.normalize = True
        self.device = "cpu"
        self.model_name = "mock-embedding-model"

    def _deterministic_embedding(self, text: str) -> np.ndarray:
        """Generate deterministic embedding based on text hash."""
        seed = hash(str(text)) % (2**32)
        rng = np.random.default_rng(seed)
        emb = rng.standard_normal(self.dimension).astype(np.float32)
        return emb / np.linalg.norm(emb)

    def generate(self, texts, *args, **kwargs) -> np.ndarray:
        """Generate embeddings for texts."""
        if isinstance(texts, str):
            return self._deterministic_embedding(texts)
        return np.array([self._deterministic_embedding(t) for t in texts])

    def generate_for_paper(self, paper: dict, **kwargs) -> np.ndarray:
        """Generate embedding for a paper dict."""
        text = paper.get("title", "") + " " + paper.get("abstract", "")
        return self._deterministic_embedding(text)

    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between embeddings."""
        return float(np.dot(emb1, emb2))

    def compute_similarity_batch(
        self, query: np.ndarray, embeddings: np.ndarray
    ) -> np.ndarray:
        """Compute similarity between query and multiple embeddings."""
        return np.dot(embeddings, query)

    def embed_paper_chunks(
        self,
        paper_id: int,
        full_text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list:
        """Generate chunk embeddings for a paper's full text."""
        # Simple chunking for mock
        chunks = []
        text_len = len(full_text)
        start = 0
        chunk_idx = 0

        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk_text = full_text[start:end]

            # Create a mock chunk embedding object
            chunk = MagicMock()
            chunk.chunk_id = f"{paper_id}_{chunk_idx}"
            chunk.embedding = self._deterministic_embedding(chunk_text)
            chunk.text = chunk_text
            chunk.to_metadata = MagicMock(return_value={
                "paper_id": paper_id,
                "chunk_index": chunk_idx,
            })
            chunks.append(chunk)

            start = end - chunk_overlap if end < text_len else end
            chunk_idx += 1

        return chunks


class MockVectorStore:
    """Mock for VectorStore (ChromaDB wrapper)."""

    def __init__(self):
        self.collection_name = "mock_papers"
        self._data = {}  # id -> (embedding, metadata, document)
        # Mock collection for EmbeddingService compatibility
        self.collection = MagicMock()
        self.collection.get = MagicMock(return_value={"ids": [], "metadatas": []})

    def get_stats(self) -> dict:
        """Return stats about the vector store."""
        return {"count": len(self._data)}

    def add(self, id: str, embedding: np.ndarray, metadata: dict = None, document: str = None):
        """Add a single embedding."""
        self._data[id] = (embedding, metadata or {}, document or "")
        # Update mock collection.get to return current IDs
        self.collection.get = MagicMock(return_value={
            "ids": list(self._data.keys()),
            "metadatas": [d[1] for d in self._data.values()]
        })

    def add_batch(self, ids: list, embeddings: np.ndarray, metadatas: list = None, documents: list = None):
        """Add multiple embeddings."""
        metadatas = metadatas or [{}] * len(ids)
        documents = documents or [""] * len(ids)
        for i, id in enumerate(ids):
            self._data[id] = (embeddings[i], metadatas[i], documents[i])

    def search(self, query_embedding: np.ndarray, top_k: int = 10, where: dict = None, score_threshold: float = 0.0) -> list:
        """Search for similar embeddings."""
        if not self._data:
            return []

        results = []
        for id, (emb, meta, doc) in self._data.items():
            score = float(np.dot(query_embedding, emb))
            if score >= score_threshold:
                results.append({"id": id, "score": score, "metadata": meta, "document": doc})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def get(self, ids: list = None, where: dict = None, limit: int = None, include: list = None) -> list:
        """Get embeddings by ID or filter."""
        if ids:
            return [
                {"id": id, "embedding": self._data[id][0], "metadata": self._data[id][1]}
                for id in ids if id in self._data
            ]
        return list(self._data.values())[:limit] if limit else list(self._data.values())

    def delete(self, ids: list):
        """Delete embeddings by ID."""
        for id in ids:
            self._data.pop(id, None)

    def exists(self, id: str) -> bool:
        """Check if ID exists."""
        return id in self._data

    def count(self) -> int:
        """Return count of stored embeddings."""
        return len(self._data)

    def reset(self):
        """Clear all data."""
        self._data.clear()


class MockChunkVectorStore(MockVectorStore):
    """Mock for ChunkVectorStore."""

    def __init__(self):
        super().__init__()
        self.collection_name = "mock_chunks"

    def get_stats(self) -> dict:
        """Return stats about the chunk store."""
        paper_ids = set()
        for id, (emb, meta, doc) in self._data.items():
            if meta.get("paper_id"):
                paper_ids.add(meta["paper_id"])
        return {
            "total_chunks": len(self._data),
            "papers_indexed": len(paper_ids),
        }

    def add_chunks(self, chunk_ids: list, embeddings: list, texts: list, metadatas: list):
        """Add chunks to the store."""
        for i, chunk_id in enumerate(chunk_ids):
            self._data[chunk_id] = (embeddings[i], metadatas[i], texts[i])
        # Update mock collection.get
        self.collection.get = MagicMock(return_value={
            "ids": list(self._data.keys()),
            "metadatas": [d[1] for d in self._data.values()]
        })

    def search_chunks(self, query_embedding: np.ndarray, limit: int = 10, paper_ids: list = None, min_score: float = 0.0) -> list:
        """Search chunks with optional paper filter."""
        results = self.search(query_embedding, top_k=limit * 3, score_threshold=min_score)

        if paper_ids:
            results = [r for r in results if r.get("metadata", {}).get("paper_id") in paper_ids]

        return results[:limit]

    def get_paper_chunks(self, paper_id: int) -> list:
        """Get all chunks for a paper."""
        return [
            {"id": id, "embedding": data[0], "metadata": data[1], "text": data[2]}
            for id, data in self._data.items()
            if data[1].get("paper_id") == paper_id
        ]

    def delete_paper_chunks(self, paper_id: int):
        """Delete all chunks for a paper."""
        to_delete = [id for id, data in self._data.items() if data[1].get("paper_id") == paper_id]
        for id in to_delete:
            del self._data[id]
