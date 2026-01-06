"""Unit tests for PaperService.

Tests cover:
- CRUD operations (create, get, list, update, delete)
- Search operations
- Content operations (get_content, store_extraction, extraction_queue)
- Batch operations (batch_update, batch_delete)
- Validation and error handling
"""
import pytest

from services.paper_service import PaperService, PaperListResult, BatchResult
from literature_core import PaperNotFoundError, ValidationError


class TestPaperServiceCreate:
    """Tests for paper creation."""

    def test_create_paper_minimal(self, db):
        """Test creating a paper with only required fields."""
        result = PaperService.create(title="Test Paper")

        assert result["id"] is not None
        assert result["title"] == "Test Paper"
        assert result["read_status"] == "unread"
        assert result["rating"] is None
        assert result["authors"] == []
        assert result["tags"] == []

    def test_create_paper_full(self, db):
        """Test creating a paper with all fields."""
        result = PaperService.create(
            title="Full Paper",
            abstract="This is the abstract",
            year=2023,
            doi="10.1234/test",
            arxiv_id="2301.12345",
            journal="Test Journal",
            authors=["John Smith", "Jane Doe"],
            tags=["ALD", "review"],
        )

        assert result["title"] == "Full Paper"
        assert result["abstract"] == "This is the abstract"
        assert result["year"] == 2023
        assert result["doi"] == "10.1234/test"
        assert result["arxiv_id"] == "2301.12345"
        assert result["journal"] == "Test Journal"
        assert len(result["authors"]) == 2
        assert result["authors"][0]["name"] == "John Smith"
        assert len(result["tags"]) == 2

    def test_create_paper_empty_title_fails(self, db):
        """Test that empty title raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PaperService.create(title="")

        assert "title" in str(exc_info.value).lower()

    def test_create_paper_none_title_fails(self, db):
        """Test that None title raises ValidationError."""
        with pytest.raises(ValidationError):
            PaperService.create(title=None)

    def test_create_paper_reuses_existing_authors(self, db):
        """Test that same author is reused across papers."""
        result1 = PaperService.create(
            title="Paper 1",
            authors=["John Smith"]
        )
        result2 = PaperService.create(
            title="Paper 2",
            authors=["John Smith"]
        )

        # Author ID should be the same
        assert result1["authors"][0]["id"] == result2["authors"][0]["id"]

    def test_create_paper_reuses_existing_tags(self, db):
        """Test that same tag is reused across papers."""
        result1 = PaperService.create(
            title="Paper 1",
            tags=["ALD"]
        )
        result2 = PaperService.create(
            title="Paper 2",
            tags=["ALD"]
        )

        # Tag ID should be the same
        assert result1["tags"][0]["id"] == result2["tags"][0]["id"]


class TestPaperServiceGet:
    """Tests for paper retrieval."""

    def test_get_paper_success(self, db):
        """Test getting an existing paper."""
        created = PaperService.create(title="Get Test Paper")

        result = PaperService.get(created["id"])

        assert result["id"] == created["id"]
        assert result["title"] == "Get Test Paper"

    def test_get_paper_not_found(self, db):
        """Test getting non-existent paper raises error."""
        with pytest.raises(PaperNotFoundError) as exc_info:
            PaperService.get(99999)

        assert exc_info.value.paper_id == 99999

    def test_get_paper_includes_relationships(self, db):
        """Test that get includes authors and tags."""
        created = PaperService.create(
            title="Paper with Relations",
            authors=["John Smith"],
            tags=["ALD"]
        )

        result = PaperService.get(created["id"])

        assert len(result["authors"]) == 1
        assert result["authors"][0]["name"] == "John Smith"
        assert len(result["tags"]) == 1
        assert result["tags"][0]["name"] == "ALD"


class TestPaperServiceList:
    """Tests for paper listing."""

    def test_list_papers_empty(self, db):
        """Test listing when no papers exist."""
        result = PaperService.list()

        assert isinstance(result, PaperListResult)
        assert result.total == 0
        assert result.papers == []

    def test_list_papers_basic(self, db):
        """Test basic paper listing."""
        PaperService.create(title="Paper 1")
        PaperService.create(title="Paper 2")
        PaperService.create(title="Paper 3")

        result = PaperService.list()

        assert result.total == 3
        assert len(result.papers) == 3

    def test_list_papers_filter_by_year(self, db):
        """Test filtering papers by year."""
        PaperService.create(title="Paper 2023", year=2023)
        PaperService.create(title="Paper 2022", year=2022)
        PaperService.create(title="Paper 2021", year=2021)

        result = PaperService.list(year=2023)

        assert result.total == 1
        assert result.papers[0]["year"] == 2023

    def test_list_papers_filter_by_tag(self, db):
        """Test filtering papers by tag."""
        PaperService.create(title="ALD Paper", tags=["ALD"])
        PaperService.create(title="CVD Paper", tags=["CVD"])

        result = PaperService.list(tag="ALD")

        assert result.total == 1
        assert result.papers[0]["title"] == "ALD Paper"

    def test_list_papers_filter_by_author(self, db):
        """Test filtering papers by author (partial match)."""
        PaperService.create(title="Paper 1", authors=["John Smith"])
        PaperService.create(title="Paper 2", authors=["Jane Doe"])

        result = PaperService.list(author="Smith")

        assert result.total == 1
        assert "John Smith" in result.papers[0]["authors"]

    def test_list_papers_filter_by_read_status(self, db):
        """Test filtering papers by read status."""
        p1 = PaperService.create(title="Paper 1")
        PaperService.update(p1["id"], read_status="read")
        PaperService.create(title="Paper 2")  # Default: unread

        result = PaperService.list(read_status="read")

        assert result.total == 1
        assert result.papers[0]["read_status"] == "read"

    def test_list_papers_invalid_read_status(self, db):
        """Test that invalid read_status raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PaperService.list(read_status="invalid")

        assert "read_status" in str(exc_info.value).lower()

    def test_list_papers_pagination(self, db):
        """Test pagination works correctly."""
        for i in range(15):
            PaperService.create(title=f"Paper {i}")

        # First page
        result1 = PaperService.list(limit=10, offset=0)
        assert len(result1.papers) == 10
        assert result1.total == 15
        assert result1.limit == 10
        assert result1.offset == 0

        # Second page
        result2 = PaperService.list(limit=10, offset=10)
        assert len(result2.papers) == 5
        assert result2.offset == 10

    def test_list_papers_limit_capped_at_max(self, db):
        """Test that limit is capped at MAX_SEARCH_LIMIT."""
        result = PaperService.list(limit=1000)

        # Should be capped at 500 (MAX_SEARCH_LIMIT)
        assert result.limit <= 500


class TestPaperServiceUpdate:
    """Tests for paper updates."""

    def test_update_paper_title(self, db):
        """Test updating paper title."""
        created = PaperService.create(title="Original Title")

        result = PaperService.update(created["id"], title="Updated Title")

        assert result["title"] == "Updated Title"

    def test_update_paper_rating(self, db):
        """Test updating paper rating."""
        created = PaperService.create(title="Test Paper")

        result = PaperService.update(created["id"], rating=5)

        assert result["rating"] == 5

    def test_update_paper_invalid_rating_high(self, db):
        """Test that rating above 5 raises ValidationError."""
        created = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError) as exc_info:
            PaperService.update(created["id"], rating=10)

        assert "rating" in str(exc_info.value).lower()

    def test_update_paper_invalid_rating_low(self, db):
        """Test that rating below 1 raises ValidationError."""
        created = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError) as exc_info:
            PaperService.update(created["id"], rating=0)

        assert "rating" in str(exc_info.value).lower()

    def test_update_paper_read_status(self, db):
        """Test updating paper read status."""
        created = PaperService.create(title="Test Paper")

        result = PaperService.update(created["id"], read_status="read")

        assert result["read_status"] == "read"

    def test_update_paper_invalid_read_status(self, db):
        """Test that invalid read_status raises ValidationError."""
        created = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError) as exc_info:
            PaperService.update(created["id"], read_status="invalid")

        assert "read_status" in str(exc_info.value).lower()

    def test_update_paper_replaces_tags(self, db):
        """Test that updating tags replaces all existing tags."""
        created = PaperService.create(title="Test Paper", tags=["tag1", "tag2"])

        result = PaperService.update(created["id"], tags=["tag3"])

        assert len(result["tags"]) == 1
        assert result["tags"][0]["name"] == "tag3"

    def test_update_paper_not_found(self, db):
        """Test updating non-existent paper raises error."""
        with pytest.raises(PaperNotFoundError):
            PaperService.update(99999, title="New Title")

    def test_update_paper_preserves_unmodified_fields(self, db):
        """Test that update only changes specified fields."""
        created = PaperService.create(
            title="Original Title",
            abstract="Original Abstract",
            year=2023
        )

        result = PaperService.update(created["id"], title="New Title")

        assert result["title"] == "New Title"
        assert result["abstract"] == "Original Abstract"
        assert result["year"] == 2023


class TestPaperServiceDelete:
    """Tests for paper deletion."""

    def test_delete_paper_success(self, db):
        """Test deleting a paper."""
        created = PaperService.create(title="Delete Me")

        PaperService.delete(created["id"])

        with pytest.raises(PaperNotFoundError):
            PaperService.get(created["id"])

    def test_delete_paper_not_found(self, db):
        """Test deleting non-existent paper raises error."""
        with pytest.raises(PaperNotFoundError):
            PaperService.delete(99999)


class TestPaperServiceSearch:
    """Tests for paper search."""

    def test_search_by_title(self, db):
        """Test searching papers by title."""
        PaperService.create(title="Machine Learning for Materials")
        PaperService.create(title="Deep Learning Overview")
        PaperService.create(title="Chemistry Fundamentals")

        results = PaperService.search("Learning")

        assert len(results) == 2

    def test_search_by_abstract(self, db):
        """Test searching papers by abstract."""
        PaperService.create(
            title="Paper 1",
            abstract="This paper discusses neural networks"
        )
        PaperService.create(
            title="Paper 2",
            abstract="This paper is about chemistry"
        )

        results = PaperService.search("neural")

        assert len(results) == 1
        assert results[0]["title"] == "Paper 1"

    def test_search_no_results(self, db):
        """Test search with no matches returns empty list."""
        PaperService.create(title="Test Paper")

        results = PaperService.search("nonexistent_xyz_123")

        assert results == []

    def test_search_respects_limit(self, db):
        """Test that search respects limit parameter."""
        for i in range(10):
            PaperService.create(title=f"ML Paper {i}")

        results = PaperService.search("ML", limit=5)

        assert len(results) == 5


class TestPaperServiceContent:
    """Tests for content operations."""

    def test_get_content_basic(self, db):
        """Test getting paper content."""
        created = PaperService.create(
            title="Test Paper",
            abstract="Test Abstract"
        )

        result = PaperService.get_content(created["id"])

        assert result["id"] == created["id"]
        assert result["title"] == "Test Paper"
        assert result["abstract"] == "Test Abstract"
        # full_text not included by default (token efficiency)
        assert "full_text" not in result

    def test_get_content_with_full_text(self, db):
        """Test get_content with full_text explicitly requested."""
        created = PaperService.create(
            title="Test Paper",
            abstract="Test Abstract"
        )

        result = PaperService.get_content(created["id"], include_full_text=True)

        assert result["id"] == created["id"]
        assert result["title"] == "Test Paper"
        # full_text included when requested (None if no chunks)
        assert "full_text" in result
        assert result["full_text"] is None  # No chunks added

    def test_get_content_not_found(self, db):
        """Test get_content for non-existent paper."""
        with pytest.raises(PaperNotFoundError):
            PaperService.get_content(99999)

    def test_store_extraction(self, db):
        """Test storing AI extraction results."""
        created = PaperService.create(title="Test Paper")

        PaperService.store_extraction(
            paper_id=created["id"],
            paper_type="research_article",
            topics=["ALD", "thin films"],
            one_sentence_summary="A study of ALD processes.",
            key_findings=["Finding 1", "Finding 2"],
            methodology_summary="We used XPS and TEM."
        )

        content = PaperService.get_content(created["id"])

        assert "extraction" in content
        assert content["extraction"]["paper_type"] == "research_article"
        assert content["extraction"]["topics"] == ["ALD", "thin films"]

    def test_store_extraction_not_found(self, db):
        """Test store_extraction for non-existent paper."""
        with pytest.raises(PaperNotFoundError):
            PaperService.store_extraction(99999, paper_type="article")

    def test_get_extraction_queue(self, db):
        """Test getting papers needing extraction."""
        # Paper with abstract but no extraction
        p1 = PaperService.create(title="Paper 1", abstract="Has abstract")

        # Paper without abstract or full_text (should not appear)
        PaperService.create(title="Paper 2")

        # Paper with extraction already done
        p3 = PaperService.create(title="Paper 3", abstract="Also has abstract")
        PaperService.store_extraction(p3["id"], paper_type="article")

        queue = PaperService.get_extraction_queue()

        assert len(queue) == 1
        assert queue[0]["id"] == p1["id"]
        assert queue[0]["has_abstract"] is True


class TestPaperServiceBatchOperations:
    """Tests for batch operations."""

    def test_batch_update_success(self, db):
        """Test batch update applies changes to all papers."""
        papers = [
            PaperService.create(title=f"Paper {i}")
            for i in range(5)
        ]
        paper_ids = [p["id"] for p in papers]

        result = PaperService.batch_update(
            paper_ids=paper_ids,
            tags_to_add=["batch-tag"],
            read_status="reading",
        )

        assert isinstance(result, BatchResult)
        assert len(result.processed) == 5
        assert len(result.failed) == 0

        # Verify changes
        for pid in paper_ids:
            paper = PaperService.get(pid)
            assert paper["read_status"] == "reading"
            assert any(t["name"] == "batch-tag" for t in paper["tags"])

    def test_batch_update_partial_failure(self, db):
        """Test batch update handles missing papers gracefully."""
        created = PaperService.create(title="Exists")

        result = PaperService.batch_update(
            paper_ids=[created["id"], 99999],
            read_status="read",
        )

        assert len(result.processed) == 1
        assert len(result.failed) == 1
        assert result.failed[0]["id"] == 99999

    def test_batch_update_add_and_remove_tags(self, db):
        """Test batch update can add and remove tags."""
        paper = PaperService.create(title="Paper", tags=["old-tag"])

        result = PaperService.batch_update(
            paper_ids=[paper["id"]],
            tags_to_add=["new-tag"],
            tags_to_remove=["old-tag"],
        )

        assert len(result.processed) == 1
        updated = PaperService.get(paper["id"])
        tag_names = [t["name"] for t in updated["tags"]]
        assert "new-tag" in tag_names
        assert "old-tag" not in tag_names

    def test_batch_update_invalid_rating(self, db):
        """Test batch update validates rating."""
        with pytest.raises(ValidationError):
            PaperService.batch_update(
                paper_ids=[1],
                rating=10
            )

    def test_batch_delete_success(self, db):
        """Test batch delete removes all specified papers."""
        papers = [
            PaperService.create(title=f"Paper {i}")
            for i in range(5)
        ]
        paper_ids = [p["id"] for p in papers]

        result = PaperService.batch_delete(paper_ids)

        assert len(result.processed) == 5
        assert len(result.failed) == 0

        # Verify papers are gone
        for pid in paper_ids:
            with pytest.raises(PaperNotFoundError):
                PaperService.get(pid)

    def test_batch_delete_partial_failure(self, db):
        """Test batch delete handles missing papers gracefully."""
        created = PaperService.create(title="Exists")

        result = PaperService.batch_delete([created["id"], 99999])

        assert len(result.processed) == 1
        assert len(result.failed) == 1

    def test_batch_delete_empty_list(self, db):
        """Test batch delete with empty list."""
        result = PaperService.batch_delete([])

        assert len(result.processed) == 0
        assert len(result.failed) == 0
