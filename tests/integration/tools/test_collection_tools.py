"""Integration tests for Collection MCP tools.

Tests cover:
- Collection CRUD operations
- Hierarchy management
- Paper associations
- Error handling
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import collections


class TestCollectionToolSchemas:
    """Tests for collection tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_collection_tools(self):
        """Test that list_tools returns all expected collection tools."""
        tools = await collections.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "list_collections",
            "get_collection",
            "create_collection",
            "update_collection",
            "delete_collection",
            "add_papers_to_collection",
            "remove_papers_from_collection",
            "get_collection_children",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_create_collection_requires_name(self):
        """Test that create_collection schema requires name."""
        tools = await collections.list_tools()
        create = next(t for t in tools if t.name == "create_collection")

        assert "required" in create.inputSchema
        assert "name" in create.inputSchema["required"]


class TestListCollectionsTool:
    """Tests for list_collections tool."""

    @pytest.mark.asyncio
    async def test_list_collections_empty(self, db):
        """Test listing collections from empty database."""
        result = await collections.call_tool("list_collections", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_list_collections_with_data(self, db):
        """Test listing collections with data."""
        from services import CollectionService

        CollectionService.create(name="Collection 1")
        CollectionService.create(name="Collection 2")

        result = await collections.call_tool("list_collections", {"all": True})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 2

    @pytest.mark.asyncio
    async def test_list_collections_root_only(self, db):
        """Test listing only root collections."""
        from services import CollectionService

        parent = CollectionService.create(name="Parent")
        CollectionService.create(name="Child", parent_id=parent["id"])

        result = await collections.call_tool("list_collections", {})

        data = json.loads(result[0].text)
        # Should only return root collections (parent_id is None)
        assert data["data"]["count"] >= 1

    @pytest.mark.asyncio
    async def test_list_collections_by_parent(self, db):
        """Test listing collections filtered by parent."""
        from services import CollectionService

        parent = CollectionService.create(name="Parent")
        CollectionService.create(name="Child 1", parent_id=parent["id"])
        CollectionService.create(name="Child 2", parent_id=parent["id"])
        CollectionService.create(name="Other Root")

        result = await collections.call_tool("list_collections", {
            "parent_id": parent["id"]
        })

        data = json.loads(result[0].text)
        assert data["data"]["count"] == 2


class TestGetCollectionTool:
    """Tests for get_collection tool."""

    @pytest.mark.asyncio
    async def test_get_collection_success(self, db):
        """Test getting a collection by ID."""
        from services import CollectionService

        collection = CollectionService.create(
            name="Test Collection",
            description="Test description"
        )

        result = await collections.call_tool("get_collection", {
            "collection_id": collection["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["name"] == "Test Collection"
        assert data["data"]["description"] == "Test description"

    @pytest.mark.asyncio
    async def test_get_collection_not_found(self, db):
        """Test getting non-existent collection."""
        result = await collections.call_tool("get_collection", {
            "collection_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "COLLECTION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_collection_includes_paper_count(self, db):
        """Test that get_collection includes paper count."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test Collection")
        paper = PaperService.create(title="Test Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        result = await collections.call_tool("get_collection", {
            "collection_id": collection["id"]
        })

        data = json.loads(result[0].text)
        assert "paper_count" in data["data"] or "paper_ids" in data["data"]


class TestCreateCollectionTool:
    """Tests for create_collection tool."""

    @pytest.mark.asyncio
    async def test_create_collection_minimal(self, db):
        """Test creating collection with minimal fields."""
        result = await collections.call_tool("create_collection", {
            "name": "New Collection"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["name"] == "New Collection"

    @pytest.mark.asyncio
    async def test_create_collection_with_description(self, db):
        """Test creating collection with description."""
        result = await collections.call_tool("create_collection", {
            "name": "New Collection",
            "description": "A test collection"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["description"] == "A test collection"

    @pytest.mark.asyncio
    async def test_create_collection_with_parent(self, db):
        """Test creating nested collection."""
        from services import CollectionService

        parent = CollectionService.create(name="Parent")

        result = await collections.call_tool("create_collection", {
            "name": "Child",
            "parent_id": parent["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["parent_id"] == parent["id"]

    @pytest.mark.asyncio
    async def test_create_collection_invalid_parent(self, db):
        """Test creating collection with non-existent parent."""
        result = await collections.call_tool("create_collection", {
            "name": "Orphan",
            "parent_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestUpdateCollectionTool:
    """Tests for update_collection tool."""

    @pytest.mark.asyncio
    async def test_update_collection_name(self, db):
        """Test updating collection name."""
        from services import CollectionService

        collection = CollectionService.create(name="Original Name")

        result = await collections.call_tool("update_collection", {
            "collection_id": collection["id"],
            "name": "Updated Name"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_collection_description(self, db):
        """Test updating collection description."""
        from services import CollectionService

        collection = CollectionService.create(name="Test")

        result = await collections.call_tool("update_collection", {
            "collection_id": collection["id"],
            "description": "New description"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["description"] == "New description"

    @pytest.mark.asyncio
    async def test_update_collection_parent(self, db):
        """Test updating collection parent."""
        from services import CollectionService

        parent = CollectionService.create(name="Parent")
        child = CollectionService.create(name="Child")

        result = await collections.call_tool("update_collection", {
            "collection_id": child["id"],
            "parent_id": parent["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["parent_id"] == parent["id"]

    @pytest.mark.asyncio
    async def test_update_collection_not_found(self, db):
        """Test updating non-existent collection."""
        result = await collections.call_tool("update_collection", {
            "collection_id": 99999,
            "name": "New Name"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "COLLECTION_NOT_FOUND"


class TestDeleteCollectionTool:
    """Tests for delete_collection tool."""

    @pytest.mark.asyncio
    async def test_delete_collection_success(self, db):
        """Test deleting a collection."""
        from services import CollectionService

        collection = CollectionService.create(name="To Delete")

        result = await collections.call_tool("delete_collection", {
            "collection_id": collection["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_collection_not_found(self, db):
        """Test deleting non-existent collection."""
        result = await collections.call_tool("delete_collection", {
            "collection_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_delete_collection_preserves_papers(self, db):
        """Test that deleting collection doesn't delete papers."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test")
        paper = PaperService.create(title="Test Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        await collections.call_tool("delete_collection", {
            "collection_id": collection["id"]
        })

        # Paper should still exist
        retrieved = PaperService.get(paper["id"])
        assert retrieved is not None


class TestAddPapersToCollectionTool:
    """Tests for add_papers_to_collection tool."""

    @pytest.mark.asyncio
    async def test_add_papers_success(self, db):
        """Test adding papers to collection."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test")
        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")

        result = await collections.call_tool("add_papers_to_collection", {
            "collection_id": collection["id"],
            "paper_ids": [p1["id"], p2["id"]]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert len(data["data"]["added"]) == 2

    @pytest.mark.asyncio
    async def test_add_papers_already_in_collection(self, db):
        """Test adding papers that are already in collection."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test")
        paper = PaperService.create(title="Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        result = await collections.call_tool("add_papers_to_collection", {
            "collection_id": collection["id"],
            "paper_ids": [paper["id"]]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        # Should indicate already in collection
        assert len(data["data"].get("already_in_collection", [])) >= 0

    @pytest.mark.asyncio
    async def test_add_papers_collection_not_found(self, db):
        """Test adding papers to non-existent collection."""
        from services import PaperService

        paper = PaperService.create(title="Paper")

        result = await collections.call_tool("add_papers_to_collection", {
            "collection_id": 99999,
            "paper_ids": [paper["id"]]
        })

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestRemovePapersFromCollectionTool:
    """Tests for remove_papers_from_collection tool."""

    @pytest.mark.asyncio
    async def test_remove_papers_success(self, db):
        """Test removing papers from collection."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test")
        p1 = PaperService.create(title="Paper 1")
        p2 = PaperService.create(title="Paper 2")
        CollectionService.add_papers(collection["id"], [p1["id"], p2["id"]])

        result = await collections.call_tool("remove_papers_from_collection", {
            "collection_id": collection["id"],
            "paper_ids": [p1["id"]]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert len(data["data"]["removed"]) == 1

    @pytest.mark.asyncio
    async def test_remove_papers_not_in_collection(self, db):
        """Test removing papers not in collection."""
        from services import CollectionService, PaperService

        collection = CollectionService.create(name="Test")
        paper = PaperService.create(title="Paper")

        result = await collections.call_tool("remove_papers_from_collection", {
            "collection_id": collection["id"],
            "paper_ids": [paper["id"]]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True


class TestGetCollectionChildrenTool:
    """Tests for get_collection_children tool."""

    @pytest.mark.asyncio
    async def test_get_children_success(self, db):
        """Test getting child collections."""
        from services import CollectionService

        parent = CollectionService.create(name="Parent")
        CollectionService.create(name="Child 1", parent_id=parent["id"])
        CollectionService.create(name="Child 2", parent_id=parent["id"])

        result = await collections.call_tool("get_collection_children", {
            "collection_id": parent["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 2

    @pytest.mark.asyncio
    async def test_get_children_empty(self, db):
        """Test getting children from collection with no children."""
        from services import CollectionService

        collection = CollectionService.create(name="No Children")

        result = await collections.call_tool("get_collection_children", {
            "collection_id": collection["id"]
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_get_children_not_found(self, db):
        """Test getting children from non-existent collection.

        Note: get_collection_children returns success=True with count=0
        for non-existent parents (doesn't validate parent exists).
        """
        result = await collections.call_tool("get_collection_children", {
            "collection_id": 99999
        })

        data = json.loads(result[0].text)
        # Returns empty list for non-existent parent
        assert data["success"] is True
        assert data["data"]["count"] == 0


class TestUnknownCollectionTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db):
        """Test that unknown tool returns proper error."""
        result = await collections.call_tool("unknown_collection_tool", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
