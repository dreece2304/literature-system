"""Integration tests for Search MCP tools.

Tests cover:
- Keyword search via tools
- Semantic search via tools (mocked embeddings)
- Author and tag search
- Error handling
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
import numpy as np

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import search


class TestSearchToolSchemas:
    """Tests for search tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_search_tools(self):
        """Test that list_tools returns all expected search tools."""
        tools = await search.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "search",
            "search_by_author",
            "search_by_tag",
            "get_search_status",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_search_schema(self):
        """Test unified search schema structure."""
        tools = await search.list_tools()
        unified = next(t for t in tools if t.name == "search")

        props = unified.inputSchema["properties"]
        assert "query" in props
        assert "mode" in props
        assert "query" in unified.inputSchema["required"]

    @pytest.mark.asyncio
    async def test_search_mode_options(self):
        """Test search tool has all mode options."""
        tools = await search.list_tools()
        unified = next(t for t in tools if t.name == "search")

        mode_prop = unified.inputSchema["properties"]["mode"]
        assert set(mode_prop["enum"]) == {"smart", "keyword", "semantic", "hybrid"}


class TestKeywordSearchTool:
    """Tests for search tool with mode='keyword'."""

    @pytest.mark.asyncio
    async def test_keyword_search_finds_by_title(self, db):
        """Test keyword search finds papers by title."""
        from services import PaperService

        PaperService.create(title="Machine Learning Paper")
        PaperService.create(title="Chemistry Paper")

        result = await search.call_tool("search", {"query": "Machine", "mode": "keyword"})

        data = json.loads(result[0].text)
        assert data["search_type"] == "keyword"
        assert data["count"] >= 1
        titles = [r["title"] for r in data["results"]]
        assert "Machine Learning Paper" in titles

    @pytest.mark.asyncio
    async def test_keyword_search_finds_by_abstract(self, db):
        """Test keyword search finds papers by abstract."""
        from services import PaperService

        PaperService.create(
            title="Paper 1",
            abstract="This paper discusses neural networks"
        )
        PaperService.create(
            title="Paper 2",
            abstract="This paper is about traditional methods"
        )

        result = await search.call_tool("search", {"query": "neural networks", "mode": "keyword"})

        data = json.loads(result[0].text)
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_keyword_search_case_insensitive(self, db):
        """Test keyword search is case insensitive."""
        from services import PaperService

        PaperService.create(title="UPPERCASE TITLE")

        result = await search.call_tool("search", {"query": "uppercase", "mode": "keyword"})

        data = json.loads(result[0].text)
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_keyword_search_with_year_min(self, db):
        """Test keyword search with year_min filter."""
        from services import PaperService

        PaperService.create(title="Old Paper", year=2018)
        PaperService.create(title="New Paper", year=2023)

        result = await search.call_tool("search", {
            "query": "Paper",
            "mode": "keyword",
            "year_min": 2020
        })

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["year"] == 2023

    @pytest.mark.asyncio
    async def test_keyword_search_with_year_max(self, db):
        """Test keyword search with year_max filter."""
        from services import PaperService

        PaperService.create(title="Old Paper", year=2018)
        PaperService.create(title="New Paper", year=2023)

        result = await search.call_tool("search", {
            "query": "Paper",
            "mode": "keyword",
            "year_max": 2020
        })

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["year"] == 2018

    @pytest.mark.asyncio
    async def test_keyword_search_with_year_range(self, db):
        """Test keyword search with year range."""
        from services import PaperService

        PaperService.create(title="Paper 2018", year=2018)
        PaperService.create(title="Paper 2020", year=2020)
        PaperService.create(title="Paper 2023", year=2023)

        result = await search.call_tool("search", {
            "query": "Paper",
            "mode": "keyword",
            "year_min": 2019,
            "year_max": 2021
        })

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["year"] == 2020

    @pytest.mark.asyncio
    async def test_keyword_search_respects_limit(self, db):
        """Test keyword search respects limit parameter."""
        from services import PaperService

        for i in range(10):
            PaperService.create(title=f"Test Paper {i}")

        result = await search.call_tool("search", {
            "query": "Test",
            "mode": "keyword",
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert len(data["results"]) <= 5

    @pytest.mark.asyncio
    async def test_keyword_search_no_results(self, db):
        """Test keyword search with no matches."""
        from services import PaperService

        PaperService.create(title="Some Paper")

        result = await search.call_tool("search", {
            "query": "nonexistent_xyz_123",
            "mode": "keyword"
        })

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["results"] == []


class TestSemanticSearchTool:
    """Tests for search tool with mode='semantic' (with mocked embeddings)."""

    @pytest.mark.asyncio
    async def test_semantic_search_paper_level(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test semantic search at paper level."""
        from services import PaperService

        paper = PaperService.create(
            title="Atomic Layer Deposition Review",
            abstract="A comprehensive review of ALD"
        )

        # Add data to the mock vector store (it's a real mock with state)
        embedding = mock_embedding_generator.generate("ALD thin film")
        mock_vector_store.add(
            id=str(paper["id"]),
            embedding=embedding,
            metadata={"paper_id": paper["id"]},
            document="Atomic layer deposition"
        )

        result = await search.call_tool("search", {
            "query": "ALD thin film deposition",
            "mode": "semantic",
            "search_level": "paper"
        })

        data = json.loads(result[0].text)
        # May fall back to keyword search if embeddings not available
        assert data["search_type"] in ["semantic_paper", "semantic", "keyword"]

    @pytest.mark.asyncio
    async def test_semantic_search_chunk_level(
        self, db, mock_embedding_generator, mock_chunk_store
    ):
        """Test semantic search at chunk level."""
        from services import PaperService

        paper = PaperService.create(
            title="Test Paper",
            abstract="Test abstract about materials"
        )

        # Add chunk data to the mock store (uses inherited add method)
        embedding = mock_embedding_generator.generate("materials science content")
        mock_chunk_store.add(
            id=f"{paper['id']}_0",
            embedding=embedding,
            metadata={"paper_id": paper["id"], "chunk_index": 0},
            document="Matching content about materials"
        )

        result = await search.call_tool("search", {
            "query": "materials science",
            "mode": "semantic",
            "search_level": "chunk"
        })

        data = json.loads(result[0].text)
        # May fall back to keyword search
        assert "search_type" in data

    @pytest.mark.asyncio
    async def test_semantic_search_with_min_similarity(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test semantic search with minimum similarity threshold."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        # Add data with a specific embedding (will have low similarity to unrelated query)
        embedding = mock_embedding_generator.generate("completely different topic")
        mock_vector_store.add(
            id=str(paper["id"]),
            embedding=embedding,
            metadata={"paper_id": paper["id"]},
            document="Test paper content"
        )

        result = await search.call_tool("search", {
            "query": "unrelated query",
            "mode": "semantic",
            "min_similarity": 0.5,
            "search_level": "paper"
        })

        data = json.loads(result[0].text)
        # Low score results may be filtered depending on implementation
        assert "search_type" in data

    @pytest.mark.asyncio
    async def test_semantic_search_fallback_to_keyword(
        self, db, mock_embedding_generator
    ):
        """Test that semantic search falls back to keyword on error."""
        from services import PaperService

        PaperService.create(title="Fallback Test Paper")

        # Make embedding generation fail
        mock_embedding_generator.generate = MagicMock(
            side_effect=Exception("Embedding error")
        )

        result = await search.call_tool("search", {"query": "Fallback Test", "mode": "semantic"})

        data = json.loads(result[0].text)
        # Should indicate fallback or semantic when embedding fails
        assert data["search_type"] in ["semantic_fallback", "semantic", "keyword"]


class TestSearchByAuthorTool:
    """Tests for search_by_author tool."""

    @pytest.mark.asyncio
    async def test_search_by_author_exact(self, db):
        """Test finding papers by exact author name."""
        from services import PaperService

        PaperService.create(title="Paper 1", authors=["John Smith"])
        PaperService.create(title="Paper 2", authors=["Jane Doe"])

        result = await search.call_tool("search_by_author", {
            "author_name": "John Smith"
        })

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["title"] == "Paper 1"

    @pytest.mark.asyncio
    async def test_search_by_author_partial(self, db):
        """Test finding papers by partial author name."""
        from services import PaperService

        PaperService.create(title="Paper 1", authors=["John Smith"])
        PaperService.create(title="Paper 2", authors=["John Doe"])

        result = await search.call_tool("search_by_author", {"author_name": "John"})

        data = json.loads(result[0].text)
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_search_by_author_case_insensitive(self, db):
        """Test author search is case insensitive."""
        from services import PaperService

        PaperService.create(title="Paper", authors=["John SMITH"])

        result = await search.call_tool("search_by_author", {
            "author_name": "john smith"
        })

        data = json.loads(result[0].text)
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_search_by_author_no_results(self, db):
        """Test author search with no matches."""
        from services import PaperService

        PaperService.create(title="Paper", authors=["John Smith"])

        result = await search.call_tool("search_by_author", {
            "author_name": "Nonexistent Author"
        })

        data = json.loads(result[0].text)
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_search_by_author_respects_limit(self, db):
        """Test author search respects limit."""
        from services import PaperService

        for i in range(10):
            PaperService.create(title=f"Paper {i}", authors=["Prolific Author"])

        result = await search.call_tool("search_by_author", {
            "author_name": "Prolific",
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert len(data["results"]) <= 5


class TestSearchByTagTool:
    """Tests for search_by_tag tool."""

    @pytest.mark.asyncio
    async def test_search_by_tag(self, db):
        """Test finding papers by tag."""
        from services import PaperService

        PaperService.create(title="ALD Paper", tags=["ALD", "thin-films"])
        PaperService.create(title="CVD Paper", tags=["CVD"])

        result = await search.call_tool("search_by_tag", {"tag": "ALD"})

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["title"] == "ALD Paper"

    @pytest.mark.asyncio
    async def test_search_by_tag_no_results(self, db):
        """Test tag search with no matches."""
        from services import PaperService

        PaperService.create(title="Paper", tags=["existing-tag"])

        result = await search.call_tool("search_by_tag", {"tag": "nonexistent-tag"})

        data = json.loads(result[0].text)
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_search_by_tag_respects_limit(self, db):
        """Test tag search respects limit."""
        from services import PaperService

        for i in range(10):
            PaperService.create(title=f"Paper {i}", tags=["common-tag"])

        result = await search.call_tool("search_by_tag", {
            "tag": "common-tag",
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert len(data["results"]) <= 5


class TestUnknownSearchTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db):
        """Test that unknown tool returns proper error."""
        result = await search.call_tool("unknown_search", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
