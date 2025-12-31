"""Unit tests for NoteService.

Tests cover:
- CRUD operations (create, get, list, update, delete)
- Paper-specific operations (get_for_paper, delete_for_paper)
- Validation and error handling
"""
import pytest

from services.note_service import NoteService, NoteListResult
from services.paper_service import PaperService
from literature_core import NoteNotFoundError, PaperNotFoundError, ValidationError


class TestNoteServiceCreate:
    """Tests for note creation."""

    def test_create_note_minimal(self, db):
        """Test creating a note with only required fields."""
        paper = PaperService.create(title="Test Paper")

        result = NoteService.create(
            paper_id=paper["id"],
            content="This is a note"
        )

        assert result["id"] is not None
        assert result["paper_id"] == paper["id"]
        assert result["content"] == "This is a note"
        assert result["note_type"] == "comment"  # default
        assert result["page_number"] is None
        assert result["created_at"] is not None

    def test_create_note_full(self, db):
        """Test creating a note with all fields."""
        paper = PaperService.create(title="Test Paper")

        result = NoteService.create(
            paper_id=paper["id"],
            content="Highlighted text",
            note_type="highlight",
            page_number=5,
            position='{"x": 100, "y": 200}'
        )

        assert result["content"] == "Highlighted text"
        assert result["note_type"] == "highlight"
        assert result["page_number"] == 5
        assert result["position"] == '{"x": 100, "y": 200}'

    def test_create_note_empty_content_fails(self, db):
        """Test that empty content raises ValidationError."""
        paper = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError) as exc_info:
            NoteService.create(paper_id=paper["id"], content="")

        assert "content" in str(exc_info.value).lower()

    def test_create_note_whitespace_content_fails(self, db):
        """Test that whitespace-only content raises ValidationError."""
        paper = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError):
            NoteService.create(paper_id=paper["id"], content="   ")

    def test_create_note_invalid_type_fails(self, db):
        """Test that invalid note_type raises ValidationError."""
        paper = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError) as exc_info:
            NoteService.create(
                paper_id=paper["id"],
                content="Note",
                note_type="invalid_type"
            )

        assert "note_type" in str(exc_info.value).lower()

    def test_create_note_paper_not_found(self, db):
        """Test creating note for non-existent paper fails."""
        with pytest.raises(PaperNotFoundError):
            NoteService.create(paper_id=99999, content="Note")

    def test_create_note_strips_whitespace(self, db):
        """Test that content whitespace is stripped."""
        paper = PaperService.create(title="Test Paper")

        result = NoteService.create(
            paper_id=paper["id"],
            content="  Trimmed content  "
        )

        assert result["content"] == "Trimmed content"

    def test_create_note_all_valid_types(self, db):
        """Test creating notes with all valid types."""
        paper = PaperService.create(title="Test Paper")

        for note_type in ["highlight", "comment", "summary"]:
            result = NoteService.create(
                paper_id=paper["id"],
                content=f"A {note_type} note",
                note_type=note_type
            )
            assert result["note_type"] == note_type


class TestNoteServiceGet:
    """Tests for note retrieval."""

    def test_get_note_success(self, db):
        """Test getting an existing note."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Test note")

        result = NoteService.get(created["id"])

        assert result["id"] == created["id"]
        assert result["content"] == "Test note"

    def test_get_note_not_found(self, db):
        """Test getting non-existent note raises error."""
        with pytest.raises(NoteNotFoundError) as exc_info:
            NoteService.get(99999)

        assert exc_info.value.note_id == 99999


class TestNoteServiceList:
    """Tests for note listing."""

    def test_list_notes_empty(self, db):
        """Test listing when no notes exist."""
        result = NoteService.list()

        assert isinstance(result, NoteListResult)
        assert result.total == 0
        assert result.notes == []

    def test_list_notes_basic(self, db):
        """Test basic note listing."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1")
        NoteService.create(paper_id=paper["id"], content="Note 2")
        NoteService.create(paper_id=paper["id"], content="Note 3")

        result = NoteService.list()

        assert result.total == 3
        assert len(result.notes) == 3

    def test_list_notes_filter_by_paper(self, db):
        """Test filtering notes by paper."""
        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2")
        NoteService.create(paper_id=paper1["id"], content="Note for P1")
        NoteService.create(paper_id=paper2["id"], content="Note for P2")

        result = NoteService.list(paper_id=paper1["id"])

        assert result.total == 1
        assert result.notes[0]["paper_id"] == paper1["id"]

    def test_list_notes_filter_by_type(self, db):
        """Test filtering notes by note_type."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Highlight", note_type="highlight")
        NoteService.create(paper_id=paper["id"], content="Comment", note_type="comment")

        result = NoteService.list(note_type="highlight")

        assert result.total == 1
        assert result.notes[0]["note_type"] == "highlight"

    def test_list_notes_invalid_type(self, db):
        """Test that invalid note_type raises ValidationError."""
        with pytest.raises(ValidationError):
            NoteService.list(note_type="invalid")

    def test_list_notes_pagination(self, db):
        """Test pagination works correctly."""
        paper = PaperService.create(title="Test Paper")
        for i in range(15):
            NoteService.create(paper_id=paper["id"], content=f"Note {i}")

        result1 = NoteService.list(limit=10, offset=0)
        assert len(result1.notes) == 10
        assert result1.total == 15

        result2 = NoteService.list(limit=10, offset=10)
        assert len(result2.notes) == 5


class TestNoteServiceUpdate:
    """Tests for note updates."""

    def test_update_note_content(self, db):
        """Test updating note content."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Original")

        result = NoteService.update(created["id"], content="Updated")

        assert result["content"] == "Updated"

    def test_update_note_type(self, db):
        """Test updating note type."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(
            paper_id=paper["id"],
            content="Note",
            note_type="comment"
        )

        result = NoteService.update(created["id"], note_type="highlight")

        assert result["note_type"] == "highlight"

    def test_update_note_page_number(self, db):
        """Test updating note page number."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Note")

        result = NoteService.update(created["id"], page_number=10)

        assert result["page_number"] == 10

    def test_update_note_invalid_type(self, db):
        """Test that invalid note_type raises ValidationError."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Note")

        with pytest.raises(ValidationError):
            NoteService.update(created["id"], note_type="invalid")

    def test_update_note_not_found(self, db):
        """Test updating non-existent note raises error."""
        with pytest.raises(NoteNotFoundError):
            NoteService.update(99999, content="New content")

    def test_update_note_sets_modified_at(self, db):
        """Test that update sets modified_at timestamp."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Note")
        assert created["modified_at"] is None

        result = NoteService.update(created["id"], content="Updated")

        assert result["modified_at"] is not None


class TestNoteServiceDelete:
    """Tests for note deletion."""

    def test_delete_note_success(self, db):
        """Test deleting a note."""
        paper = PaperService.create(title="Test Paper")
        created = NoteService.create(paper_id=paper["id"], content="Delete me")

        result = NoteService.delete(created["id"])

        assert result["id"] == created["id"]
        with pytest.raises(NoteNotFoundError):
            NoteService.get(created["id"])

    def test_delete_note_not_found(self, db):
        """Test deleting non-existent note raises error."""
        with pytest.raises(NoteNotFoundError):
            NoteService.delete(99999)


class TestNoteServicePaperOperations:
    """Tests for paper-specific operations."""

    def test_get_for_paper(self, db):
        """Test getting all notes for a paper."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1", page_number=1)
        NoteService.create(paper_id=paper["id"], content="Note 2", page_number=5)
        NoteService.create(paper_id=paper["id"], content="Note 3", page_number=3)

        notes = NoteService.get_for_paper(paper["id"])

        assert len(notes) == 3
        # Should be ordered by page_number
        assert notes[0]["page_number"] == 1
        assert notes[1]["page_number"] == 3
        assert notes[2]["page_number"] == 5

    def test_get_for_paper_with_type_filter(self, db):
        """Test getting notes for paper filtered by type."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="H1", note_type="highlight")
        NoteService.create(paper_id=paper["id"], content="C1", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="H2", note_type="highlight")

        notes = NoteService.get_for_paper(paper["id"], note_type="highlight")

        assert len(notes) == 2
        assert all(n["note_type"] == "highlight" for n in notes)

    def test_get_for_paper_empty(self, db):
        """Test getting notes for paper with no notes."""
        paper = PaperService.create(title="Test Paper")

        notes = NoteService.get_for_paper(paper["id"])

        assert notes == []

    def test_get_for_paper_invalid_type(self, db):
        """Test that invalid note_type raises ValidationError."""
        paper = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError):
            NoteService.get_for_paper(paper["id"], note_type="invalid")

    def test_delete_for_paper_all(self, db):
        """Test deleting all notes for a paper."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1")
        NoteService.create(paper_id=paper["id"], content="Note 2")
        NoteService.create(paper_id=paper["id"], content="Note 3")

        count = NoteService.delete_for_paper(paper["id"])

        assert count == 3
        assert NoteService.get_for_paper(paper["id"]) == []

    def test_delete_for_paper_by_type(self, db):
        """Test deleting notes for paper filtered by type."""
        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="H1", note_type="highlight")
        NoteService.create(paper_id=paper["id"], content="C1", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="H2", note_type="highlight")

        count = NoteService.delete_for_paper(paper["id"], note_type="highlight")

        assert count == 2
        remaining = NoteService.get_for_paper(paper["id"])
        assert len(remaining) == 1
        assert remaining[0]["note_type"] == "comment"

    def test_delete_for_paper_none_to_delete(self, db):
        """Test deleting notes when none exist."""
        paper = PaperService.create(title="Test Paper")

        count = NoteService.delete_for_paper(paper["id"])

        assert count == 0

    def test_delete_for_paper_invalid_type(self, db):
        """Test that invalid note_type raises ValidationError."""
        paper = PaperService.create(title="Test Paper")

        with pytest.raises(ValidationError):
            NoteService.delete_for_paper(paper["id"], note_type="invalid")
