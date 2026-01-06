"""Integration tests for MCP Server.

Tests the full MCP server functionality:
- Server initialization
- Tool registration
- Tool routing and dispatch
- Error handling
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestToolRegistration:
    """Tests for tool registration."""

    @pytest.mark.asyncio
    async def test_all_paper_tools_registered(self, db):
        """Test all paper tools are registered."""
        from mcp_server.tools.papers import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        expected_tools = [
            "add_paper",
            "get_paper",
            "list_papers",
            "update_paper",
            "batch_update_papers",
            "batch_delete_papers"
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

    @pytest.mark.asyncio
    async def test_all_search_tools_registered(self, db):
        """Test all search tools are registered."""
        from mcp_server.tools.search import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        expected_tools = [
            "search",
            "search_by_author",
            "search_by_tag",
            "get_search_status"
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

    @pytest.mark.asyncio
    async def test_all_collection_tools_registered(self, db):
        """Test all collection tools are registered."""
        from mcp_server.tools.collections import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        expected_tools = [
            "create_collection",
            "get_collection",
            "list_collections",
            "add_papers_to_collection",
            "remove_papers_from_collection"
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

    @pytest.mark.asyncio
    async def test_all_note_tools_registered(self, db):
        """Test all note tools are registered."""
        from mcp_server.tools.notes import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        expected_tools = [
            "create_note",
            "get_note",
            "list_notes",
            "update_note",
            "delete_note"
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"


class TestToolSchemas:
    """Tests for tool schema definitions."""

    @pytest.mark.asyncio
    async def test_paper_tools_have_schemas(self, db):
        """Test paper tools have input schemas."""
        from mcp_server.tools.papers import list_tools

        tools = await list_tools()

        for tool in tools:
            assert hasattr(tool, 'inputSchema') or hasattr(tool, 'input_schema')

    @pytest.mark.asyncio
    async def test_add_paper_schema(self, db):
        """Test add_paper has correct schema."""
        from mcp_server.tools.papers import list_tools

        tools = await list_tools()
        add_paper = next((t for t in tools if t.name == "add_paper"), None)

        assert add_paper is not None
        schema = getattr(add_paper, 'inputSchema', None) or getattr(
            add_paper, 'input_schema', None
        )
        assert schema is not None

        # Should have title as required
        properties = schema.get("properties", {})
        assert "title" in properties

    @pytest.mark.asyncio
    async def test_search_schema(self, db):
        """Test search tools have query parameter."""
        from mcp_server.tools.search import list_tools

        tools = await list_tools()
        search_tool = next(
            (t for t in tools if t.name == "search"), None
        )

        assert search_tool is not None
        schema = getattr(search_tool, 'inputSchema', None) or getattr(
            search_tool, 'input_schema', None
        )

        properties = schema.get("properties", {})
        assert "query" in properties
        assert "mode" in properties


class TestToolRouting:
    """Tests for tool call routing."""

    @pytest.mark.asyncio
    async def test_route_to_paper_tool(self, db):
        """Test routing to paper tools."""
        from mcp_server.tools.papers import call_tool

        result = await call_tool("list_papers", {"limit": 10})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "data" in data or "pagination" in data

    @pytest.mark.asyncio
    async def test_route_to_search_tool(self, db):
        """Test routing to search tools."""
        from mcp_server.tools.search import call_tool
        from services import PaperService

        # Create paper first
        PaperService.create(title="Searchable Paper", year=2023)

        result = await call_tool("search", {"query": "Searchable", "mode": "keyword"})

        data = json.loads(result[0].text)
        assert "results" in data or "search_type" in data

    @pytest.mark.asyncio
    async def test_route_to_collection_tool(self, db):
        """Test routing to collection tools."""
        from mcp_server.tools.collections import call_tool

        result = await call_tool("list_collections", {})

        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_route_unknown_tool(self, db):
        """Test routing to unknown tool returns error."""
        from mcp_server.tools.papers import call_tool

        result = await call_tool("nonexistent_tool", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_missing_required_param(self, db):
        """Test error when missing required parameter."""
        from mcp_server.tools.papers import call_tool

        # add_paper requires title
        result = await call_tool("add_paper", {})

        data = json.loads(result[0].text)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_not_found_error(self, db):
        """Test not found error."""
        from mcp_server.tools.papers import call_tool

        result = await call_tool("get_paper", {"paper_id": 99999})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "NOT_FOUND" in data["code"]

    @pytest.mark.asyncio
    async def test_validation_error(self, db):
        """Test validation error."""
        from mcp_server.tools.papers import call_tool

        # Empty title should fail
        result = await call_tool("add_paper", {"title": ""})

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestEndToEndWorkflows:
    """Tests for complete workflows through MCP."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_paper(self, db):
        """Test creating and then retrieving a paper."""
        from mcp_server.tools.papers import call_tool

        # Create paper
        result = await call_tool("add_paper", {
            "title": "E2E Test Paper",
            "year": 2023,
            "authors": ["Test Author"]
        })

        created = json.loads(result[0].text)
        assert created["success"] is True
        paper_id = created["data"]["id"]

        # Retrieve paper
        result = await call_tool("get_paper", {"paper_id": paper_id})

        retrieved = json.loads(result[0].text)
        assert retrieved["success"] is True
        assert retrieved["data"]["title"] == "E2E Test Paper"
        assert retrieved["data"]["year"] == 2023

    @pytest.mark.asyncio
    async def test_create_collection_add_papers(self, db):
        """Test creating collection and adding papers."""
        from mcp_server.tools.papers import call_tool as paper_call
        from mcp_server.tools.collections import call_tool as coll_call

        # Create papers
        result1 = await paper_call("add_paper", {"title": "Paper 1"})
        paper1 = json.loads(result1[0].text)["data"]

        result2 = await paper_call("add_paper", {"title": "Paper 2"})
        paper2 = json.loads(result2[0].text)["data"]

        # Create collection
        result = await coll_call("create_collection", {"name": "Test Collection"})
        collection = json.loads(result[0].text)["data"]

        # Add papers to collection
        await coll_call("add_papers_to_collection", {
            "collection_id": collection["id"],
            "paper_ids": [paper1["id"], paper2["id"]]
        })

        # Verify collection contents
        result = await coll_call("get_collection", {
            "collection_id": collection["id"]
        })
        coll_data = json.loads(result[0].text)["data"]

        assert coll_data["paper_count"] == 2 or len(coll_data.get("paper_ids", [])) == 2

    @pytest.mark.asyncio
    async def test_paper_note_workflow(self, db):
        """Test creating paper with notes."""
        from mcp_server.tools.papers import call_tool as paper_call
        from mcp_server.tools.notes import call_tool as note_call

        # Create paper
        result = await paper_call("add_paper", {"title": "Paper with Notes"})
        paper = json.loads(result[0].text)["data"]

        # Add notes
        await note_call("create_note", {
            "paper_id": paper["id"],
            "content": "First note"
        })
        await note_call("create_note", {
            "paper_id": paper["id"],
            "content": "Second note"
        })

        # List notes for paper
        result = await note_call("get_paper_notes", {"paper_id": paper["id"]})
        notes = json.loads(result[0].text)

        assert notes["success"] is True
        assert notes["data"]["count"] == 2

    @pytest.mark.asyncio
    async def test_search_after_create(self, db):
        """Test searching for newly created paper."""
        from mcp_server.tools.papers import call_tool as paper_call
        from mcp_server.tools.search import call_tool as search_call

        # Create paper with unique term
        unique_term = "UniqueSearchTerm2024"
        await paper_call("add_paper", {
            "title": f"Paper about {unique_term}",
            "year": 2024
        })

        # Search for it using unified search tool
        result = await search_call("search", {"query": unique_term, "mode": "keyword"})
        data = json.loads(result[0].text)

        assert data["count"] >= 1


class TestConcurrentOperations:
    """Tests for concurrent/batch operations."""

    @pytest.mark.asyncio
    async def test_batch_update_multiple_papers(self, db):
        """Test batch updating multiple papers."""
        from mcp_server.tools.papers import call_tool

        # Create papers
        paper_ids = []
        for i in range(5):
            result = await call_tool("add_paper", {"title": f"Batch Paper {i}"})
            paper = json.loads(result[0].text)["data"]
            paper_ids.append(paper["id"])

        # Batch update
        await call_tool("batch_update_papers", {
            "paper_ids": paper_ids,
            "tags_to_add": ["batch-updated"]
        })

        # Verify updates
        for paper_id in paper_ids:
            result = await call_tool("get_paper", {"paper_id": paper_id})
            paper = json.loads(result[0].text)["data"]
            # Tags may be returned as objects with 'name' field or as strings
            tag_names = [
                t["name"] if isinstance(t, dict) else t
                for t in paper["tags"]
            ]
            assert "batch-updated" in tag_names

    @pytest.mark.asyncio
    async def test_batch_delete_papers(self, db):
        """Test batch deleting papers."""
        from mcp_server.tools.papers import call_tool

        # Create papers
        paper_ids = []
        for i in range(3):
            result = await call_tool("add_paper", {"title": f"Delete Me {i}"})
            paper = json.loads(result[0].text)["data"]
            paper_ids.append(paper["id"])

        # Batch delete
        await call_tool("batch_delete_papers", {
            "paper_ids": paper_ids,
            "confirm": True
        })

        # Verify deletion
        for paper_id in paper_ids:
            result = await call_tool("get_paper", {"paper_id": paper_id})
            data = json.loads(result[0].text)
            assert data["success"] is False
            assert "NOT_FOUND" in data["code"]
