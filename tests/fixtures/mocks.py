"""Mock fixtures for external dependencies.

Provides mocks for:
- Embedding generator (sentence-transformers)
- Vector store (ChromaDB)
- External APIs (CrossRef, Semantic Scholar, etc.)
- HTTP clients
"""
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np


@dataclass
class MockPaperResult:
    """Mock external API paper result."""
    title: str
    authors: list[str]
    year: int
    doi: Optional[str]
    journal: Optional[str]
    abstract: Optional[str] = None
    source: str = "mock"
    confidence: float = 0.95


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


class MockVectorStore:
    """Mock for VectorStore (ChromaDB wrapper)."""

    def __init__(self):
        self.collection_name = "mock_papers"
        self._data = {}  # id -> (embedding, metadata, document)

    def add(self, id: str, embedding: np.ndarray, metadata: dict = None, document: str = None):
        """Add a single embedding."""
        self._data[id] = (embedding, metadata or {}, document or "")

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


@dataclass
class MockExternalResult:
    """Mock external search result matching service expectations."""
    title: str = "Mock Paper"
    authors: list = None
    year: int = 2023
    doi: str = None
    abstract: str = None
    journal: str = None
    arxiv_id: str = None
    pdf_url: str = None
    citation_count: int = None
    is_open_access: bool = False
    confidence: float = 0.9

    def __post_init__(self):
        if self.authors is None:
            self.authors = ["Test Author"]


def create_mock_external_service():
    """Create a mock ExternalSearchService with all API methods."""
    mock = MagicMock()

    # Create default mock results
    default_result = MockExternalResult()

    # Mock all internal search methods used by external.py
    mock._search_crossref_multi = AsyncMock(return_value=[default_result])
    mock._search_openalex = AsyncMock(return_value=[default_result])
    mock._search_semantic_scholar_query = AsyncMock(return_value=[default_result])
    mock._search_arxiv = AsyncMock(return_value=[default_result])
    mock._search_unpaywall = AsyncMock(return_value=[default_result])

    # Helper method
    mock._title_similarity = MagicMock(return_value=0.9)

    # Legacy methods for compatibility
    mock.find_doi_by_title = AsyncMock(return_value=default_result)
    mock.lookup_by_doi = AsyncMock(return_value=default_result)
    mock.search_papers = AsyncMock(return_value=[default_result])
    mock.find_pdf_url = AsyncMock(return_value="https://example.com/paper.pdf")

    return mock


def create_mock_external_api_dict():
    """Create a dictionary of mock async methods for each external API.

    Returns dict with keys: crossref, openalex, semantic_scholar, arxiv, unpaywall
    Each maps to an AsyncMock that can be configured per test.
    """
    return {
        "crossref": AsyncMock(return_value=[]),
        "openalex": AsyncMock(return_value=[]),
        "semantic_scholar": AsyncMock(return_value=[]),
        "arxiv": AsyncMock(return_value=[]),
        "unpaywall": AsyncMock(return_value=[]),
    }


def create_mock_httpx_client(responses: dict = None):
    """Create a mock httpx AsyncClient with configurable responses.

    Args:
        responses: Dict mapping URL patterns to response dicts with
                   'status_code', 'json', 'text', 'content' keys.
    """
    responses = responses or {}

    mock_client = MagicMock()

    async def mock_get(url, **kwargs):
        response = MagicMock()
        matched = None
        for pattern, resp_data in responses.items():
            if pattern in str(url):
                matched = resp_data
                break

        if matched:
            response.status_code = matched.get("status_code", 200)
            response.json = MagicMock(return_value=matched.get("json", {}))
            response.text = matched.get("text", "")
            response.content = matched.get("content", b"")
        else:
            response.status_code = 200
            response.json = MagicMock(return_value={})
            response.text = ""
            response.content = b""

        return response

    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.post = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    return mock_client


# Patch helpers for use in tests
def patch_embedding_generator(mock_gen: MockEmbeddingGenerator = None):
    """Create patches for embedding generator."""
    mock_gen = mock_gen or MockEmbeddingGenerator()
    return [
        patch('embeddings.generator.get_embedding_generator', return_value=mock_gen),
        patch('embeddings.generator.EmbeddingGenerator', return_value=mock_gen),
    ]


def patch_vector_store(mock_store: MockVectorStore = None):
    """Create patches for vector store."""
    mock_store = mock_store or MockVectorStore()
    return [
        patch('embeddings.vectorstore.get_vector_store', return_value=mock_store),
        patch('embeddings.vectorstore.VectorStore', return_value=mock_store),
    ]


def patch_chunk_store(mock_store: MockChunkVectorStore = None):
    """Create patches for chunk vector store."""
    mock_store = mock_store or MockChunkVectorStore()
    return [
        patch('embeddings.vectorstore.get_chunk_store', return_value=mock_store),
        patch('embeddings.vectorstore.ChunkVectorStore', return_value=mock_store),
    ]
