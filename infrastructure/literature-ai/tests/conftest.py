"""
Pytest fixtures and configuration for literature-ai tests.

This file contains shared fixtures used across all tests.
"""

import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# =============================================================================
# Module-level patches to prevent ChromaDB initialization during imports
# =============================================================================

# Create mock VectorStore before any imports that might trigger it
_mock_vectorstore = MagicMock()
_mock_vectorstore.search.return_value = []
_mock_vectorstore.get_stats.return_value = {"count": 0, "collection_name": "test"}
_mock_vectorstore.count.return_value = 0

# Create mock search service
_mock_search_service_instance = MagicMock()
_mock_search_service_instance.search.return_value = []
_mock_search_service_instance.get_stats.return_value = {"papers_indexed": 0}
_mock_search_service_instance.vectorstore = _mock_vectorstore

# Patch before imports
sys.modules['src.embeddings.vectorstore'] = MagicMock()
sys.modules['src.embeddings.vectorstore'].VectorStore = MagicMock(return_value=_mock_vectorstore)
sys.modules['src.embeddings.vectorstore'].get_vector_store = MagicMock(return_value=_mock_vectorstore)

# Test data constants
MOCK_PAPER_1 = {
    "paper_id": "mock-001",
    "title": "Deep Learning for Natural Language Processing",
    "authors": "Smith, J., Johnson, A.",
    "year": 2023,
    "abstract": "This paper explores deep learning techniques for NLP tasks.",
    "preview": "Deep learning has revolutionized NLP...",
    "venue": "NeurIPS 2023",
    "citation_count": 42,
    "num_chunks": 5,
}

MOCK_PAPER_2 = {
    "paper_id": "mock-002",
    "title": "Reinforcement Learning in Robotics",
    "authors": "Chen, L., Williams, K.",
    "year": 2024,
    "abstract": "Application of RL algorithms to robotic manipulation tasks.",
    "preview": "Reinforcement learning enables robots...",
    "venue": "ICRA 2024",
    "citation_count": 15,
    "num_chunks": 3,
}

MOCK_PAPER_3 = {
    "paper_id": "mock-003",
    "title": "Attention Mechanisms in Computer Vision",
    "authors": "Davis, R., Thompson, M.",
    "year": 2023,
    "abstract": "Survey of attention mechanisms for vision tasks.",
    "preview": "Attention has become crucial for computer vision...",
    "venue": "CVPR 2023",
    "citation_count": 128,
    "num_chunks": 8,
}


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary database path for testing."""
    db_path = tmp_path / "test_scores.db"
    yield db_path
    # Cleanup happens automatically with tmp_path


@pytest.fixture
def temp_vectorstore_path(tmp_path):
    """Provide a temporary vectorstore path for testing."""
    vs_path = tmp_path / "test_vectorstore"
    vs_path.mkdir(exist_ok=True)
    yield vs_path
    # Cleanup happens automatically with tmp_path


# =============================================================================
# Mock Service Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_service():
    """Mock LLM service for testing agents without real API calls."""
    mock = AsyncMock()

    # Default response for generate
    mock.generate.return_value = "This is a test response from the LLM."

    # Default response for generate_json
    mock.generate_json.return_value = {
        "score": 8,
        "justification": "Highly relevant to research interests",
        "dimensions": {
            "relevance": 0.9,
            "novelty": 0.7,
            "methodology": 0.8,
        },
        "key_takeaways": [
            "Novel approach to problem",
            "Strong experimental results",
        ],
        "action": "must_read",
    }

    # Default response for generate_stream
    async def mock_stream():
        chunks = ["This ", "is ", "a ", "streamed ", "response."]
        for chunk in chunks:
            yield chunk

    mock.generate_stream.return_value = mock_stream()

    return mock


@pytest.fixture
def mock_search_service():
    """Mock search service for testing without ChromaDB."""
    mock = Mock()

    # Mock search results
    from dataclasses import dataclass

    @dataclass
    class MockSearchResult:
        paper_id: str
        chunk_id: str
        score: float
        text: str
        title: str
        authors: str
        year: int

    mock.search.return_value = [
        MockSearchResult(
            paper_id="mock-001",
            chunk_id="chunk-1",
            score=0.92,
            text="Deep learning has revolutionized natural language processing...",
            title=MOCK_PAPER_1["title"],
            authors=MOCK_PAPER_1["authors"],
            year=MOCK_PAPER_1["year"],
        ),
        MockSearchResult(
            paper_id="mock-003",
            chunk_id="chunk-2",
            score=0.85,
            text="Attention mechanisms enable models to focus on relevant parts...",
            title=MOCK_PAPER_3["title"],
            authors=MOCK_PAPER_3["authors"],
            year=MOCK_PAPER_3["year"],
        ),
    ]

    # Mock get_paper_summary
    mock.get_paper_summary.return_value = MOCK_PAPER_1

    # Mock find_similar_papers
    mock.find_similar_papers.return_value = [
        MockSearchResult(
            paper_id="mock-003",
            chunk_id="chunk-3",
            score=0.88,
            text="Attention in vision...",
            title=MOCK_PAPER_3["title"],
            authors=MOCK_PAPER_3["authors"],
            year=MOCK_PAPER_3["year"],
        ),
    ]

    # Mock stats
    mock.get_stats.return_value = {
        "total_chunks": 16,
        "estimated_papers": 3,
        "embedding_dimension": 384,
    }

    return mock


@pytest.fixture
def mock_citation_service():
    """Mock citation service for testing."""
    mock = Mock()

    mock.format_citation.return_value = "Smith, J., & Johnson, A. (2023). Deep Learning for Natural Language Processing. NeurIPS 2023."

    mock.format_inline_citation.return_value = "(Smith & Johnson, 2023)"

    mock.generate_bibliography.return_value = """Smith, J., & Johnson, A. (2023). Deep Learning for Natural Language Processing. NeurIPS 2023.

Chen, L., & Williams, K. (2024). Reinforcement Learning in Robotics. ICRA 2024.

Davis, R., & Thompson, M. (2023). Attention Mechanisms in Computer Vision. CVPR 2023."""

    return mock


# =============================================================================
# Score Storage Fixtures
# =============================================================================

@pytest.fixture
def score_storage(temp_db_path):
    """Provide a ScoreStorage instance with temporary database."""
    from src.services.score_storage import ScoreStorage

    storage = ScoreStorage(db_path=temp_db_path)
    yield storage
    # Cleanup happens automatically


@pytest.fixture
def score_storage_with_data(score_storage):
    """Provide a ScoreStorage with pre-populated test data."""
    # Add test scores
    score_storage.store_score(
        paper_id="mock-001",
        score=8,
        justification="Highly relevant",
        dimensions={"relevance": 0.9, "novelty": 0.7},
        key_takeaways=["Novel approach", "Strong results"],
        action="must_read",
        research_interests=["NLP", "deep learning"],
        title=MOCK_PAPER_1["title"],
        authors=MOCK_PAPER_1["authors"],
        year=MOCK_PAPER_1["year"],
        context_id="test-context-1",
    )

    score_storage.store_score(
        paper_id="mock-002",
        score=6,
        justification="Moderately relevant",
        dimensions={"relevance": 0.6, "novelty": 0.5},
        key_takeaways=["Interesting application"],
        action="should_read",
        research_interests=["robotics", "RL"],
        title=MOCK_PAPER_2["title"],
        authors=MOCK_PAPER_2["authors"],
        year=MOCK_PAPER_2["year"],
        context_id="test-context-1",
    )

    score_storage.store_score(
        paper_id="mock-001",
        score=4,
        justification="Less relevant to robotics",
        dimensions={"relevance": 0.4, "novelty": 0.7},
        key_takeaways=["Different domain"],
        action="skim",
        research_interests=["robotics", "control"],
        title=MOCK_PAPER_1["title"],
        authors=MOCK_PAPER_1["authors"],
        year=MOCK_PAPER_1["year"],
        context_id="test-context-2",
    )

    return score_storage


# =============================================================================
# Agent Fixtures
# =============================================================================

@pytest.fixture
def mock_writer_agent(mock_llm_service, mock_search_service):
    """Provide a WriterAgent with mocked dependencies."""
    from src.agents.writer import WriterAgent

    agent = WriterAgent()
    agent.llm_service = mock_llm_service
    agent.search_service = mock_search_service

    return agent


@pytest.fixture
def mock_triager_agent(mock_llm_service, mock_search_service, score_storage):
    """Provide a TriagerAgent with mocked dependencies."""
    from src.agents.triager import TriagerAgent

    agent = TriagerAgent()
    agent.llm_service = mock_llm_service
    agent.search_service = mock_search_service
    agent.score_storage = score_storage

    return agent


@pytest.fixture
def mock_reader_agent(mock_llm_service, mock_search_service):
    """Provide a ReaderAgent with mocked dependencies."""
    from src.agents.reader import ReaderAgent

    agent = ReaderAgent()
    agent.llm_service = mock_llm_service
    agent.search_service = mock_search_service

    return agent


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_papers():
    """Provide sample paper data for testing."""
    return [MOCK_PAPER_1, MOCK_PAPER_2, MOCK_PAPER_3]


@pytest.fixture
def sample_text_for_citations():
    """Provide sample text needing citations."""
    return """
    Deep learning has revolutionized the field of natural language processing.
    Recent advances in transformer architectures have enabled models to achieve
    human-level performance on many tasks. However, these models require massive
    amounts of training data and computational resources.
    """


@pytest.fixture
def sample_manuscript_content():
    """Provide sample LaTeX manuscript content."""
    return r"""
\documentclass{article}
\title{My Research Paper}
\author{John Doe}

\begin{document}
\maketitle

\section{Introduction}
Deep learning has transformed AI research.

\section{Methods}
We used a transformer-based approach.

\section{Results}
Our model achieved 95\% accuracy.

\section{Discussion}
These results suggest further investigation is needed.

\end{document}
"""


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, mocked dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (slower, real services)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests (LLM calls, large data)"
    )
    config.addinivalue_line(
        "markers", "requires_ollama: Tests that require Ollama running"
    )
    config.addinivalue_line(
        "markers", "requires_redis: Tests that require Redis running"
    )
    config.addinivalue_line(
        "markers", "requires_gpu: Tests that require GPU"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark integration tests."""
    for item in items:
        # Auto-mark integration tests
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

        # Auto-mark unit tests
        elif "unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)
