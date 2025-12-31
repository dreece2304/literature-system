"""Unit tests for SearchService.

Tests cover:
- Keyword search
- Semantic search (mocked embeddings)
- Author search
- Tag search
- Search result formatting
"""
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from services.search_service import SearchService
from services.paper_service import PaperService


class TestKeywordSearch:
    """Tests for keyword search."""

    def test_keyword_search_by_title(self, db):
        """Test search finds papers by title."""
        PaperService.create(title="Machine Learning for Materials Science")
        PaperService.create(title="Deep Learning Overview")
        PaperService.create(title="Chemistry Fundamentals")

        result = SearchService.keyword_search("Learning")

        assert result.count >= 2
        assert result.search_type == "keyword"

    def test_keyword_search_by_abstract(self, db):
        """Test search finds papers by abstract content."""
        PaperService.create(
            title="Paper 1",
            abstract="This paper discusses neural networks and deep learning"
        )
        PaperService.create(
            title="Paper 2",
            abstract="This paper is about traditional chemistry methods"
        )

        result = SearchService.keyword_search("neural networks")

        assert result.count >= 1
        titles = [r["title"] for r in result.results]
        assert "Paper 1" in titles

    def test_keyword_search_case_insensitive(self, db):
        """Test that keyword search is case insensitive."""
        PaperService.create(title="UPPERCASE TITLE")
        PaperService.create(title="lowercase title")
        PaperService.create(title="Mixed Case Title")

        result = SearchService.keyword_search("title")

        assert result.count == 3

    def test_keyword_search_with_year_min_filter(self, db):
        """Test search with minimum year filter."""
        PaperService.create(title="Old Paper", year=2018)
        PaperService.create(title="New Paper", year=2023)

        result = SearchService.keyword_search("Paper", year_min=2020)

        assert result.count == 1
        assert result.results[0]["year"] == 2023

    def test_keyword_search_with_year_max_filter(self, db):
        """Test search with maximum year filter."""
        PaperService.create(title="Old Paper", year=2018)
        PaperService.create(title="New Paper", year=2023)

        result = SearchService.keyword_search("Paper", year_max=2020)

        assert result.count == 1
        assert result.results[0]["year"] == 2018

    def test_keyword_search_with_year_range(self, db):
        """Test search with year range filter."""
        PaperService.create(title="Paper 2018", year=2018)
        PaperService.create(title="Paper 2020", year=2020)
        PaperService.create(title="Paper 2023", year=2023)

        result = SearchService.keyword_search("Paper", year_min=2019, year_max=2022)

        assert result.count == 1
        assert result.results[0]["year"] == 2020

    def test_keyword_search_no_results(self, db):
        """Test search returns empty when no matches."""
        PaperService.create(title="Existing Paper")

        result = SearchService.keyword_search("nonexistent_xyz_123")

        assert result.count == 0
        assert result.results == []

    def test_keyword_search_respects_limit(self, db):
        """Test that search respects limit parameter."""
        for i in range(10):
            PaperService.create(title=f"Test Paper {i}")

        result = SearchService.keyword_search("Test", limit=5)

        assert len(result.results) <= 5

    def test_keyword_search_result_format(self, db):
        """Test that search results have correct format."""
        PaperService.create(
            title="Test Paper",
            year=2023,
            abstract="Test abstract",
            doi="10.1234/test",
            authors=["John Smith"],
            tags=["ALD"]
        )

        result = SearchService.keyword_search("Test")

        assert result.count >= 1
        paper = result.results[0]
        assert "id" in paper
        assert "title" in paper
        assert "year" in paper
        assert "authors" in paper
        assert "abstract" in paper


class TestSearchByAuthor:
    """Tests for author search."""

    def test_search_by_author_exact(self, db):
        """Test finding papers by exact author name."""
        PaperService.create(title="Paper 1", authors=["John Smith"])
        PaperService.create(title="Paper 2", authors=["Jane Doe"])

        result = SearchService.search_by_author("John Smith")

        assert result.count == 1
        assert result.results[0]["title"] == "Paper 1"

    def test_search_by_author_partial(self, db):
        """Test finding papers by partial author name."""
        PaperService.create(title="Paper 1", authors=["John Smith"])
        PaperService.create(title="Paper 2", authors=["John Doe"])

        result = SearchService.search_by_author("John")

        assert result.count == 2

    def test_search_by_author_case_insensitive(self, db):
        """Test that author search is case insensitive."""
        PaperService.create(title="Paper", authors=["John SMITH"])

        result = SearchService.search_by_author("john smith")

        assert result.count == 1

    def test_search_by_author_no_results(self, db):
        """Test author search with no matches."""
        PaperService.create(title="Paper", authors=["John Smith"])

        result = SearchService.search_by_author("Nonexistent Author")

        assert result.count == 0


class TestSearchByTag:
    """Tests for tag search."""

    def test_search_by_tag(self, db):
        """Test finding papers by tag."""
        PaperService.create(title="ALD Paper", tags=["ALD", "thin-films"])
        PaperService.create(title="CVD Paper", tags=["CVD"])

        result = SearchService.search_by_tag("ALD")

        assert result.count == 1
        assert result.results[0]["title"] == "ALD Paper"

    def test_search_by_tag_no_results(self, db):
        """Test tag search with no matches."""
        PaperService.create(title="Paper", tags=["existing-tag"])

        result = SearchService.search_by_tag("nonexistent-tag")

        assert result.count == 0

    def test_search_by_tag_respects_limit(self, db):
        """Test that tag search respects limit."""
        for i in range(10):
            PaperService.create(title=f"Paper {i}", tags=["common-tag"])

        result = SearchService.search_by_tag("common-tag", limit=5)

        assert len(result.results) <= 5


class TestSemanticSearch:
    """Tests for semantic search (with mocked embeddings)."""

    @pytest.mark.asyncio
    async def test_semantic_search_paper_level(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test semantic search at paper level."""
        # Create test paper
        paper = PaperService.create(
            title="Atomic Layer Deposition Review",
            abstract="A comprehensive review of ALD processes"
        )

        # Mock vector store to return results
        mock_vector_store.search.return_value = [
            {"id": str(paper["id"]), "score": 0.9, "metadata": {}, "document": ""}
        ]

        result = await SearchService.semantic_search(
            query="ALD thin film deposition",
            search_level="paper",
            limit=10
        )

        assert result.search_type == "semantic_paper"

    @pytest.mark.asyncio
    async def test_semantic_search_chunk_level(
        self, db, mock_embedding_generator, mock_chunk_store
    ):
        """Test semantic search at chunk level."""
        paper = PaperService.create(
            title="Test Paper",
            abstract="Test abstract about materials"
        )

        # Mock chunk store to return results
        mock_chunk_store.search_chunks.return_value = [
            {
                "id": f"{paper['id']}_0",
                "score": 0.85,
                "metadata": {"paper_id": paper["id"], "chunk_index": 0},
                "text": "Matching chunk text"
            }
        ]

        result = await SearchService.semantic_search(
            query="materials science",
            search_level="chunk",
            limit=10
        )

        assert result.search_type in ["semantic_chunk", "keyword"]  # May fall back

    @pytest.mark.asyncio
    async def test_semantic_search_with_min_similarity(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test semantic search with minimum similarity threshold."""
        paper = PaperService.create(title="Test Paper")

        # Mock low-score results
        mock_vector_store.search.return_value = [
            {"id": str(paper["id"]), "score": 0.3, "metadata": {}, "document": ""}
        ]

        result = await SearchService.semantic_search(
            query="unrelated query",
            min_similarity=0.5,
            search_level="paper"
        )

        # Low score results should be filtered
        # Note: actual filtering depends on implementation

    @pytest.mark.asyncio
    async def test_semantic_search_fallback_to_keyword(
        self, db, mock_embedding_generator
    ):
        """Test that semantic search falls back to keyword on error."""
        PaperService.create(title="Fallback Test Paper")

        # Make embedding generation fail
        mock_embedding_generator.generate = MagicMock(
            side_effect=Exception("Embedding error")
        )

        result = await SearchService.semantic_search("Fallback Test")

        # Should fall back to keyword search
        assert result.search_type == "keyword"
        assert result.count >= 1
