"""Unit tests for CollectionService.

Tests cover:
- CRUD operations (create, get, list, update, delete)
- Hierarchy operations (parent/child relationships)
- Paper association operations (add, remove, get papers)
- Validation and error handling
"""
import pytest

from services.collection_service import CollectionService, CollectionListResult, PaperOperationResult
from services.paper_service import PaperService
from literature_core import CollectionNotFoundError, ValidationError


class TestCollectionServiceCreate:
    """Tests for collection creation."""

    def test_create_collection_minimal(self, db):
        """Test creating a collection with only name."""
        result = CollectionService.create(name="My Collection")

        assert result["id"] is not None
        assert result["name"] == "My Collection"
        assert result["description"] is None
        assert result["parent_id"] is None
        assert result["paper_count"] == 0

    def test_create_collection_with_description(self, db):
        """Test creating a collection with description."""
        result = CollectionService.create(
            name="Test Collection",
            description="A test collection for papers"
        )

        assert result["name"] == "Test Collection"
        assert result["description"] == "A test collection for papers"

    def test_create_collection_with_parent(self, db):
        """Test creating a child collection."""
        parent = CollectionService.create(name="Parent Collection")
        child = CollectionService.create(
            name="Child Collection",
            parent_id=parent["id"]
        )

        assert child["parent_id"] == parent["id"]

    def test_create_collection_empty_name_fails(self, db):
        """Test that empty name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CollectionService.create(name="")

        assert "name" in str(exc_info.value).lower()

    def test_create_collection_whitespace_name_fails(self, db):
        """Test that whitespace-only name raises ValidationError."""
        with pytest.raises(ValidationError):
            CollectionService.create(name="   ")

    def test_create_collection_nonexistent_parent_fails(self, db):
        """Test that non-existent parent raises CollectionNotFoundError."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.create(name="Child", parent_id=99999)

    def test_create_collection_strips_whitespace(self, db):
        """Test that name whitespace is stripped."""
        result = CollectionService.create(name="  Trimmed Name  ")

        assert result["name"] == "Trimmed Name"


class TestCollectionServiceGet:
    """Tests for collection retrieval."""

    def test_get_collection_success(self, db):
        """Test getting an existing collection."""
        created = CollectionService.create(name="Get Test")

        result = CollectionService.get(created["id"])

        assert result["id"] == created["id"]
        assert result["name"] == "Get Test"

    def test_get_collection_not_found(self, db):
        """Test getting non-existent collection raises error."""
        with pytest.raises(CollectionNotFoundError) as exc_info:
            CollectionService.get(99999)

        assert exc_info.value.collection_id == 99999

    def test_get_collection_includes_paper_ids(self, db):
        """Test that get includes paper IDs when requested."""
        collection = CollectionService.create(name="With Papers")
        paper = PaperService.create(title="Test Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        result = CollectionService.get(collection["id"], include_papers=True)

        assert "paper_ids" in result
        assert paper["id"] in result["paper_ids"]

    def test_get_collection_excludes_paper_ids(self, db):
        """Test that get excludes paper IDs when not requested."""
        collection = CollectionService.create(name="Without Papers")

        result = CollectionService.get(collection["id"], include_papers=False)

        assert "paper_ids" not in result


class TestCollectionServiceList:
    """Tests for collection listing."""

    def test_list_collections_empty(self, db):
        """Test listing when no collections exist."""
        result = CollectionService.list()

        assert isinstance(result, CollectionListResult)
        assert result.count == 0
        assert result.collections == []

    def test_list_collections_root_only(self, db):
        """Test listing only root collections (no parent)."""
        root1 = CollectionService.create(name="Root 1")
        root2 = CollectionService.create(name="Root 2")
        CollectionService.create(name="Child", parent_id=root1["id"])

        result = CollectionService.list()

        assert result.count == 2
        names = [c["name"] for c in result.collections]
        assert "Root 1" in names
        assert "Root 2" in names
        assert "Child" not in names

    def test_list_collections_by_parent(self, db):
        """Test listing children of a specific parent."""
        parent = CollectionService.create(name="Parent")
        child1 = CollectionService.create(name="Child 1", parent_id=parent["id"])
        child2 = CollectionService.create(name="Child 2", parent_id=parent["id"])
        CollectionService.create(name="Other Root")

        result = CollectionService.list(parent_id=parent["id"])

        assert result.count == 2
        ids = [c["id"] for c in result.collections]
        assert child1["id"] in ids
        assert child2["id"] in ids

    def test_list_collections_all(self, db):
        """Test listing all collections ignoring hierarchy."""
        parent = CollectionService.create(name="Parent")
        CollectionService.create(name="Child", parent_id=parent["id"])
        CollectionService.create(name="Root")

        result = CollectionService.list(list_all=True)

        assert result.count == 3


class TestCollectionServiceUpdate:
    """Tests for collection updates."""

    def test_update_collection_name(self, db):
        """Test updating collection name."""
        created = CollectionService.create(name="Original")

        result = CollectionService.update(created["id"], name="Updated")

        assert result["name"] == "Updated"

    def test_update_collection_description(self, db):
        """Test updating collection description."""
        created = CollectionService.create(name="Test")

        result = CollectionService.update(
            created["id"],
            description="New description"
        )

        assert result["description"] == "New description"

    def test_update_collection_parent(self, db):
        """Test moving collection to new parent."""
        parent = CollectionService.create(name="New Parent")
        collection = CollectionService.create(name="Moving Collection")

        result = CollectionService.update(
            collection["id"],
            parent_id=parent["id"]
        )

        assert result["parent_id"] == parent["id"]

    def test_update_collection_self_parent_fails(self, db):
        """Test that setting collection as its own parent fails."""
        collection = CollectionService.create(name="Self Reference")

        with pytest.raises(ValidationError) as exc_info:
            CollectionService.update(
                collection["id"],
                parent_id=collection["id"]
            )

        assert "parent" in str(exc_info.value).lower()

    def test_update_collection_nonexistent_parent_fails(self, db):
        """Test that non-existent parent raises error."""
        collection = CollectionService.create(name="Test")

        with pytest.raises(CollectionNotFoundError):
            CollectionService.update(collection["id"], parent_id=99999)

    def test_update_collection_not_found(self, db):
        """Test updating non-existent collection raises error."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.update(99999, name="New Name")


class TestCollectionServiceDelete:
    """Tests for collection deletion."""

    def test_delete_collection_success(self, db):
        """Test deleting a collection."""
        created = CollectionService.create(name="Delete Me")

        result = CollectionService.delete(created["id"])

        assert result["id"] == created["id"]
        with pytest.raises(CollectionNotFoundError):
            CollectionService.get(created["id"])

    def test_delete_collection_not_found(self, db):
        """Test deleting non-existent collection raises error."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.delete(99999)

    def test_delete_collection_papers_not_deleted(self, db):
        """Test that deleting collection does not delete papers."""
        collection = CollectionService.create(name="With Papers")
        paper = PaperService.create(title="Survives")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        CollectionService.delete(collection["id"])

        # Paper should still exist
        retrieved = PaperService.get(paper["id"])
        assert retrieved["title"] == "Survives"


class TestCollectionServiceHierarchy:
    """Tests for hierarchy operations."""

    def test_get_children(self, db):
        """Test getting child collections."""
        parent = CollectionService.create(name="Parent")
        child1 = CollectionService.create(name="Child A", parent_id=parent["id"])
        child2 = CollectionService.create(name="Child B", parent_id=parent["id"])

        result = CollectionService.get_children(parent["id"])

        assert result.count == 2
        # Should be ordered by name
        assert result.collections[0]["name"] == "Child A"
        assert result.collections[1]["name"] == "Child B"

    def test_get_children_empty(self, db):
        """Test getting children of collection with no children."""
        collection = CollectionService.create(name="No Children")

        result = CollectionService.get_children(collection["id"])

        assert result.count == 0
        assert result.collections == []


class TestCollectionServicePaperOperations:
    """Tests for paper association operations."""

    def test_add_papers_success(self, db):
        """Test adding papers to a collection."""
        collection = CollectionService.create(name="Collection")
        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2")

        result = CollectionService.add_papers(
            collection["id"],
            [paper1["id"], paper2["id"]]
        )

        assert isinstance(result, PaperOperationResult)
        assert len(result.processed) == 2
        assert len(result.skipped) == 0
        assert result.reason == "added"

    def test_add_papers_already_in_collection(self, db):
        """Test adding paper that's already in collection."""
        collection = CollectionService.create(name="Collection")
        paper = PaperService.create(title="Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        result = CollectionService.add_papers(
            collection["id"],
            [paper["id"]]
        )

        assert len(result.processed) == 0
        assert len(result.skipped) == 1
        assert result.reason == "already_in"

    def test_add_papers_collection_not_found(self, db):
        """Test adding papers to non-existent collection."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.add_papers(99999, [1, 2])

    def test_remove_papers_success(self, db):
        """Test removing papers from a collection."""
        collection = CollectionService.create(name="Collection")
        paper = PaperService.create(title="Paper")
        CollectionService.add_papers(collection["id"], [paper["id"]])

        result = CollectionService.remove_papers(
            collection["id"],
            [paper["id"]]
        )

        assert len(result.processed) == 1
        assert result.reason == "removed"

    def test_remove_papers_not_in_collection(self, db):
        """Test removing paper that's not in collection."""
        collection = CollectionService.create(name="Collection")
        paper = PaperService.create(title="Paper")

        result = CollectionService.remove_papers(
            collection["id"],
            [paper["id"]]
        )

        assert len(result.processed) == 0
        assert len(result.skipped) == 1
        assert result.reason == "not_in"

    def test_remove_papers_collection_not_found(self, db):
        """Test removing papers from non-existent collection."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.remove_papers(99999, [1, 2])

    def test_get_papers(self, db):
        """Test getting papers in a collection."""
        collection = CollectionService.create(name="Collection")
        paper1 = PaperService.create(title="Paper 1", year=2023)
        paper2 = PaperService.create(title="Paper 2", year=2022)
        CollectionService.add_papers(
            collection["id"],
            [paper1["id"], paper2["id"]]
        )

        papers = CollectionService.get_papers(collection["id"])

        assert len(papers) == 2
        titles = [p["title"] for p in papers]
        assert "Paper 1" in titles
        assert "Paper 2" in titles

    def test_get_papers_empty_collection(self, db):
        """Test getting papers from empty collection."""
        collection = CollectionService.create(name="Empty")

        papers = CollectionService.get_papers(collection["id"])

        assert papers == []

    def test_get_papers_collection_not_found(self, db):
        """Test getting papers from non-existent collection."""
        with pytest.raises(CollectionNotFoundError):
            CollectionService.get_papers(99999)
