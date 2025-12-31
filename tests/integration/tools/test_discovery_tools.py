"""Integration tests for Discovery MCP tools.

Tests for find_similar_papers, suggest_citations_for_text, get_reading_queue,
and other discovery/recommendation tools.
"""
import json
import pytest


class TestFindSimilarPapers:
    """Tests for find_similar_papers tool."""

    @pytest.mark.asyncio
    async def test_find_similar_papers_basic(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test finding similar papers for a given paper."""
        from mcp_server.tools import discovery
        from services import PaperService
        import numpy as np

        # Create source paper and similar papers
        source = PaperService.create(
            title="Atomic Layer Deposition of Thin Films",
            abstract="A review of ALD techniques for semiconductor manufacturing"
        )
        similar1 = PaperService.create(
            title="ALD Precursor Chemistry",
            abstract="Chemical precursors for atomic layer deposition"
        )
        similar2 = PaperService.create(
            title="Thin Film Growth Mechanisms",
            abstract="Understanding thin film nucleation and growth"
        )

        # Add embeddings to mock vector store
        for paper in [source, similar1, similar2]:
            embedding = mock_embedding_generator.generate(
                f"{paper['title']} {paper.get('abstract', '')}"
            )
            mock_vector_store.add(
                id=str(paper["id"]),
                embedding=embedding,
                metadata={"paper_id": paper["id"]},
                document=paper["title"]
            )

        result = await discovery.call_tool("find_similar_papers", {
            "paper_id": source["id"],
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert data["search_type"] == "similar"
        # Should not include the source paper itself
        result_ids = [r["id"] for r in data["results"]]
        assert source["id"] not in result_ids

    @pytest.mark.asyncio
    async def test_find_similar_papers_not_found(self, db):
        """Test finding similar papers for non-existent paper."""
        from mcp_server.tools import discovery

        result = await discovery.call_tool("find_similar_papers", {
            "paper_id": 99999,
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["results"] == []


class TestFindPapersLikeText:
    """Tests for find_papers_like_text tool."""

    @pytest.mark.asyncio
    async def test_find_papers_like_text(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test finding papers matching free-form text."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create papers
        paper = PaperService.create(
            title="Machine Learning for Materials Science",
            abstract="Using neural networks to predict material properties"
        )

        # Add to vector store
        embedding = mock_embedding_generator.generate(paper["title"])
        mock_vector_store.add(
            id=str(paper["id"]),
            embedding=embedding,
            metadata={"paper_id": paper["id"]},
            document=paper["title"]
        )

        result = await discovery.call_tool("find_papers_like_text", {
            "text": "How can deep learning help predict material behavior?",
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert data["search_type"] == "text_similarity"
        assert "count" in data


class TestSuggestCitationsForText:
    """Tests for suggest_citations_for_text tool."""

    @pytest.mark.asyncio
    async def test_suggest_citations_basic(
        self, db, mock_embedding_generator, mock_chunk_store
    ):
        """Test suggesting citations for text."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create paper with full text
        paper = PaperService.create(
            title="Review of Catalyst Synthesis Methods",
            abstract="Comprehensive review of catalyst preparation techniques"
        )

        # Add chunk to mock store using correct API
        embedding = mock_embedding_generator.generate("catalyst synthesis")
        mock_chunk_store.add(
            id=f"{paper['id']}_0",
            embedding=embedding,
            metadata={"paper_id": paper["id"], "section": "introduction"},
            document="Various catalyst synthesis methods including..."
        )

        result = await discovery.call_tool("suggest_citations_for_text", {
            "text": "Catalyst preparation involves multiple synthesis steps",
            "limit": 3
        })

        data = json.loads(result[0].text)
        assert data["search_type"] == "citation_suggestion"


class TestGetReadingQueue:
    """Tests for get_reading_queue tool."""

    @pytest.mark.asyncio
    async def test_get_reading_queue_basic(self, db):
        """Test getting reading queue with unread papers."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create papers with different ratings
        high = PaperService.create(title="High Rating Paper")
        PaperService.update(high["id"], rating=5, read_status="unread")

        medium = PaperService.create(title="Medium Rating Paper")
        PaperService.update(medium["id"], rating=3, read_status="unread")

        low = PaperService.create(title="Low Rating Paper")
        PaperService.update(low["id"], rating=1, read_status="unread")

        # Create a read paper (should not appear)
        read_paper = PaperService.create(title="Already Read Paper")
        PaperService.update(read_paper["id"], read_status="read")

        result = await discovery.call_tool("get_reading_queue", {
            "limit": 10
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 3

        # Check ordering (highest rating first)
        papers = data["data"]["papers"]
        ratings = [p.get("rating") for p in papers]
        assert ratings[0] == 5

    @pytest.mark.asyncio
    async def test_get_reading_queue_filter_min_rating(self, db):
        """Test filtering reading queue by minimum rating."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create papers with different ratings
        high = PaperService.create(title="High Rating")
        PaperService.update(high["id"], rating=5, read_status="unread")

        low = PaperService.create(title="Low Rating")
        PaperService.update(low["id"], rating=2, read_status="unread")

        result = await discovery.call_tool("get_reading_queue", {
            "min_rating": 4
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 1
        assert data["data"]["papers"][0]["title"] == "High Rating"

    @pytest.mark.asyncio
    async def test_get_reading_queue_empty(self, db):
        """Test reading queue when all papers are read."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create only read papers
        paper = PaperService.create(title="Read Paper")
        PaperService.update(paper["id"], read_status="read")

        result = await discovery.call_tool("get_reading_queue", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 0


class TestSuggestPaperTags:
    """Tests for suggest_paper_tags tool."""

    @pytest.mark.asyncio
    async def test_suggest_tags_returns_success(
        self, db, mock_embedding_generator, mock_vector_store
    ):
        """Test that suggest_paper_tags returns a valid response."""
        from mcp_server.tools import discovery
        from services import PaperService

        # Create source paper
        source = PaperService.create(
            title="Novel ALD Precursor Development",
            abstract="New chemical precursors for atomic layer deposition"
        )

        # Create similar papers with tags
        similar1 = PaperService.create(
            title="ALD Chemistry Review",
            abstract="Chemical aspects of ALD",
            tags=["ald", "chemistry"]
        )

        # Add to vector store
        for paper in [source, similar1]:
            embedding = mock_embedding_generator.generate(paper["title"])
            mock_vector_store.add(
                id=str(paper["id"]),
                embedding=embedding,
                metadata={"paper_id": paper["id"]},
                document=paper["title"]
            )

        result = await discovery.call_tool("suggest_paper_tags", {
            "paper_id": source["id"],
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        # Response should have suggestions structure (may be empty if no matches)
        assert "suggestions" in data["data"]
        assert "paper_id" in data["data"]

    @pytest.mark.asyncio
    async def test_suggest_tags_no_similar_papers(self, db):
        """Test tag suggestions when no similar papers found."""
        from mcp_server.tools import discovery
        from services import PaperService

        paper = PaperService.create(title="Unique Paper")

        result = await discovery.call_tool("suggest_paper_tags", {
            "paper_id": paper["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["suggestions"] == []
