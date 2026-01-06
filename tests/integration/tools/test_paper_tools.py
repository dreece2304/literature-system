"""Integration tests for Paper MCP tools.

Tests cover:
- Tool schema correctness
- CRUD operations via tools
- Error handling and response format
- Batch operations
"""
import pytest
import json
from unittest.mock import patch

# Import the tool module
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import papers


class TestPaperToolSchemas:
    """Tests for paper tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_paper_tools(self):
        """Test that list_tools returns all expected paper tools."""
        tools = await papers.list_tools()

        tool_names = [t.name for t in tools]
        # Note: search_papers was moved to unified search tool in search.py
        expected = [
            "list_papers",
            "get_paper",
            "add_paper",
            "update_paper",
            "get_paper_content",
            "store_extraction",
            "get_extraction_queue",
            "batch_update_papers",
            "batch_delete_papers",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_tool_schemas_have_required_fields(self):
        """Test that all tool schemas have proper structure."""
        tools = await papers.list_tools()

        for tool in tools:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.inputSchema is not None
            assert "type" in tool.inputSchema
            assert "properties" in tool.inputSchema

    @pytest.mark.asyncio
    async def test_add_paper_requires_title(self):
        """Test that add_paper schema requires title."""
        tools = await papers.list_tools()
        add_paper = next(t for t in tools if t.name == "add_paper")

        assert "required" in add_paper.inputSchema
        assert "title" in add_paper.inputSchema["required"]


class TestListPapersTool:
    """Tests for list_papers tool."""

    @pytest.mark.asyncio
    async def test_list_papers_empty_db(self, db):
        """Test listing papers from empty database."""
        result = await papers.call_tool("list_papers", {})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["pagination"]["total"] == 0
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_papers_with_data(self, db):
        """Test listing papers with data in database."""
        from services import PaperService

        PaperService.create(title="Paper 1")
        PaperService.create(title="Paper 2")

        result = await papers.call_tool("list_papers", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["pagination"]["total"] == 2
        assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_list_papers_with_limit(self, db):
        """Test list_papers respects limit parameter."""
        from services import PaperService

        for i in range(10):
            PaperService.create(title=f"Paper {i}")

        result = await papers.call_tool("list_papers", {"limit": 5})

        data = json.loads(result[0].text)
        assert len(data["data"]) == 5
        assert data["pagination"]["total"] == 10

    @pytest.mark.asyncio
    async def test_list_papers_with_offset(self, db):
        """Test list_papers with pagination offset."""
        from services import PaperService

        for i in range(10):
            PaperService.create(title=f"Paper {i}")

        result = await papers.call_tool("list_papers", {"offset": 5, "limit": 20})

        data = json.loads(result[0].text)
        assert len(data["data"]) == 5  # 5 remaining after offset

    @pytest.mark.asyncio
    async def test_list_papers_filter_by_year(self, db):
        """Test list_papers filtered by year."""
        from services import PaperService

        PaperService.create(title="Paper 2020", year=2020)
        PaperService.create(title="Paper 2023", year=2023)

        result = await papers.call_tool("list_papers", {"year": 2023})

        data = json.loads(result[0].text)
        assert data["pagination"]["total"] == 1
        assert data["data"][0]["year"] == 2023

    @pytest.mark.asyncio
    async def test_list_papers_filter_by_tag(self, db):
        """Test list_papers filtered by tag."""
        from services import PaperService

        PaperService.create(title="ALD Paper", tags=["ALD"])
        PaperService.create(title="CVD Paper", tags=["CVD"])

        result = await papers.call_tool("list_papers", {"tag": "ALD"})

        data = json.loads(result[0].text)
        assert data["pagination"]["total"] == 1
        assert data["data"][0]["title"] == "ALD Paper"

    @pytest.mark.asyncio
    async def test_list_papers_filter_by_read_status(self, db):
        """Test list_papers filtered by read status."""
        from services import PaperService

        paper = PaperService.create(title="Paper")
        PaperService.update(paper["id"], read_status="read")
        PaperService.create(title="Unread Paper")

        result = await papers.call_tool("list_papers", {"read_status": "read"})

        data = json.loads(result[0].text)
        assert data["pagination"]["total"] == 1


class TestGetPaperTool:
    """Tests for get_paper tool."""

    @pytest.mark.asyncio
    async def test_get_paper_success(self, db):
        """Test getting a paper by ID."""
        from services import PaperService

        paper = PaperService.create(
            title="Test Paper",
            abstract="Test abstract",
            year=2023
        )

        result = await papers.call_tool("get_paper", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["title"] == "Test Paper"
        assert data["data"]["abstract"] == "Test abstract"
        assert data["data"]["year"] == 2023

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self, db):
        """Test getting non-existent paper."""
        result = await papers.call_tool("get_paper", {"paper_id": 99999})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "PAPER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_paper_includes_authors(self, db):
        """Test that get_paper includes author information."""
        from services import PaperService

        paper = PaperService.create(
            title="Test Paper",
            authors=["John Smith", "Jane Doe"]
        )

        result = await papers.call_tool("get_paper", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert "authors" in data["data"]
        assert len(data["data"]["authors"]) == 2

    @pytest.mark.asyncio
    async def test_get_paper_includes_tags(self, db):
        """Test that get_paper includes tag information."""
        from services import PaperService

        paper = PaperService.create(
            title="Test Paper",
            tags=["ALD", "materials"]
        )

        result = await papers.call_tool("get_paper", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert "tags" in data["data"]


class TestAddPaperTool:
    """Tests for add_paper tool."""

    @pytest.mark.asyncio
    async def test_add_paper_minimal(self, db):
        """Test adding paper with minimal fields."""
        result = await papers.call_tool("add_paper", {"title": "New Paper"})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["title"] == "New Paper"

    @pytest.mark.asyncio
    async def test_add_paper_full(self, db):
        """Test adding paper with all fields."""
        result = await papers.call_tool("add_paper", {
            "title": "Full Paper",
            "abstract": "Test abstract",
            "year": 2023,
            "doi": "10.1234/test",
            "arxiv_id": "2301.12345",
            "authors": ["John Smith"],
            "tags": ["ALD"],
            "journal": "Test Journal"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["doi"] == "10.1234/test"
        assert data["data"]["year"] == 2023

    @pytest.mark.asyncio
    async def test_add_paper_duplicate_doi(self, db):
        """Test adding paper with duplicate DOI fails."""
        await papers.call_tool("add_paper", {
            "title": "Paper 1",
            "doi": "10.1234/unique"
        })

        result = await papers.call_tool("add_paper", {
            "title": "Paper 2",
            "doi": "10.1234/unique"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestUpdatePaperTool:
    """Tests for update_paper tool."""

    @pytest.mark.asyncio
    async def test_update_paper_title(self, db):
        """Test updating paper title."""
        from services import PaperService

        paper = PaperService.create(title="Original Title")

        result = await papers.call_tool("update_paper", {
            "paper_id": paper["id"],
            "title": "Updated Title"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_paper_read_status(self, db):
        """Test updating paper read status."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await papers.call_tool("update_paper", {
            "paper_id": paper["id"],
            "read_status": "read"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["read_status"] == "read"

    @pytest.mark.asyncio
    async def test_update_paper_rating(self, db):
        """Test updating paper rating."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await papers.call_tool("update_paper", {
            "paper_id": paper["id"],
            "rating": 5
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["rating"] == 5

    @pytest.mark.asyncio
    async def test_update_paper_invalid_rating(self, db):
        """Test updating paper with invalid rating fails."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await papers.call_tool("update_paper", {
            "paper_id": paper["id"],
            "rating": 10
        })

        data = json.loads(result[0].text)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_paper_not_found(self, db):
        """Test updating non-existent paper."""
        result = await papers.call_tool("update_paper", {
            "paper_id": 99999,
            "title": "New Title"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "PAPER_NOT_FOUND"


class TestSearchPapersTool:
    """Tests for search tool (moved to search.py, testing via unified search)."""

    @pytest.mark.asyncio
    async def test_search_papers_by_title(self, db):
        """Test searching papers by title using unified search tool."""
        from services import PaperService
        from mcp_server.tools import search

        PaperService.create(title="Machine Learning Paper")
        PaperService.create(title="Chemistry Paper")

        result = await search.call_tool("search", {"query": "Machine", "mode": "keyword"})

        data = json.loads(result[0].text)
        assert data["search_type"] == "keyword"
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_papers_respects_limit(self, db):
        """Test that search respects limit using unified search tool."""
        from services import PaperService
        from mcp_server.tools import search

        for i in range(10):
            PaperService.create(title=f"Test Paper {i}")

        result = await search.call_tool("search", {
            "query": "Test",
            "mode": "keyword",
            "limit": 3
        })

        data = json.loads(result[0].text)
        assert len(data["results"]) <= 3


class TestGetPaperContentTool:
    """Tests for get_paper_content tool."""

    @pytest.mark.asyncio
    async def test_get_paper_content_success(self, db):
        """Test getting paper content."""
        from services import PaperService

        paper = PaperService.create(
            title="Test Paper",
            abstract="Test abstract"
        )

        result = await papers.call_tool("get_paper_content", {
            "paper_id": paper["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "title" in data["data"]
        assert "abstract" in data["data"]

    @pytest.mark.asyncio
    async def test_get_paper_content_not_found(self, db):
        """Test getting content for non-existent paper."""
        result = await papers.call_tool("get_paper_content", {
            "paper_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestStoreExtractionTool:
    """Tests for store_extraction tool."""

    @pytest.mark.asyncio
    async def test_store_extraction_success(self, db):
        """Test storing AI extraction."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await papers.call_tool("store_extraction", {
            "paper_id": paper["id"],
            "paper_type": "research_article",
            "topics": ["machine learning", "materials"],
            "one_sentence_summary": "A study about ML in materials science.",
            "key_findings": ["Finding 1", "Finding 2"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_store_extraction_not_found(self, db):
        """Test storing extraction for non-existent paper."""
        result = await papers.call_tool("store_extraction", {
            "paper_id": 99999,
            "paper_type": "research_article"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestGetExtractionQueueTool:
    """Tests for get_extraction_queue tool."""

    @pytest.mark.asyncio
    async def test_get_extraction_queue_empty(self, db):
        """Test extraction queue when all papers have extractions."""
        result = await papers.call_tool("get_extraction_queue", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "papers" in data["data"]

    @pytest.mark.asyncio
    async def test_get_extraction_queue_with_pending(self, db):
        """Test extraction queue with papers needing extraction.

        Note: Papers only appear in extraction queue if they have
        abstract or full_text (content to extract from).
        """
        from services import PaperService

        # Paper needs abstract or full_text to appear in queue
        PaperService.create(
            title="Paper with abstract needing extraction",
            abstract="This paper discusses important findings."
        )

        result = await papers.call_tool("get_extraction_queue", {"limit": 10})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] >= 1


class TestBatchUpdatePapersTool:
    """Tests for batch_update_papers tool."""

    @pytest.mark.asyncio
    async def test_batch_update_tags(self, db):
        """Test batch adding tags to papers."""
        from services import PaperService

        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        result = await papers.call_tool("batch_update_papers", {
            "paper_ids": [p1["id"], p2["id"]],
            "tags_to_add": ["batch-tag"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert len(data["details"]["processed"]) == 2

    @pytest.mark.asyncio
    async def test_batch_update_read_status(self, db):
        """Test batch updating read status."""
        from services import PaperService

        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        result = await papers.call_tool("batch_update_papers", {
            "paper_ids": [p1["id"], p2["id"]],
            "read_status": "read"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_batch_update_partial_failure(self, db):
        """Test batch update with some invalid IDs."""
        from services import PaperService

        p1 = PaperService.create(title="Paper 1")

        result = await papers.call_tool("batch_update_papers", {
            "paper_ids": [p1["id"], 99999],
            "read_status": "read"
        })

        data = json.loads(result[0].text)
        # Should process valid ones and report failures
        details = data.get("details", {})
        assert len(details.get("processed", [])) >= 1 or len(details.get("failed", [])) >= 1


class TestBatchDeletePapersTool:
    """Tests for batch_delete_papers tool."""

    @pytest.mark.asyncio
    async def test_batch_delete_without_confirm(self, db):
        """Test batch delete requires confirmation."""
        from services import PaperService

        p1 = PaperService.create(title="Paper 1")

        result = await papers.call_tool("batch_delete_papers", {
            "paper_ids": [p1["id"]],
            "confirm": False
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "CONFIRMATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_batch_delete_with_confirm(self, db):
        """Test batch delete with confirmation."""
        from services import PaperService

        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        result = await papers.call_tool("batch_delete_papers", {
            "paper_ids": [p1["id"], p2["id"]],
            "confirm": True
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert len(data["details"]["processed"]) == 2


class TestUnknownTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db):
        """Test that unknown tool returns proper error."""
        result = await papers.call_tool("unknown_tool", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
