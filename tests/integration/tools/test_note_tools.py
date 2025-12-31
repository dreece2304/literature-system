"""Integration tests for Notes MCP tools.

Tests cover:
- Note CRUD operations
- Paper-note relationships
- Filtering by type
- Error handling
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import notes


class TestNoteToolSchemas:
    """Tests for note tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_note_tools(self):
        """Test that list_tools returns all expected note tools."""
        tools = await notes.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "list_notes",
            "get_note",
            "create_note",
            "update_note",
            "delete_note",
            "get_paper_notes",
            "delete_paper_notes",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_create_note_requires_paper_id_and_content(self):
        """Test that create_note schema requires paper_id and content."""
        tools = await notes.list_tools()
        create = next(t for t in tools if t.name == "create_note")

        assert "required" in create.inputSchema
        assert "paper_id" in create.inputSchema["required"]
        assert "content" in create.inputSchema["required"]


class TestListNotesTool:
    """Tests for list_notes tool."""

    @pytest.mark.asyncio
    async def test_list_notes_empty(self, db):
        """Test listing notes from empty database."""
        result = await notes.call_tool("list_notes", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["pagination"]["total"] == 0
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_notes_with_data(self, db):
        """Test listing notes with data."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1")
        NoteService.create(paper_id=paper["id"], content="Note 2")

        result = await notes.call_tool("list_notes", {})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_paper_id(self, db):
        """Test listing notes filtered by paper ID."""
        from services import PaperService, NoteService

        paper1 = PaperService.create(title="Paper 1")
        paper2 = PaperService.create(title="Paper 2")
        NoteService.create(paper_id=paper1["id"], content="Note for Paper 1")
        NoteService.create(paper_id=paper2["id"], content="Note for Paper 2")

        result = await notes.call_tool("list_notes", {"paper_id": paper1["id"]})

        data = json.loads(result[0].text)
        assert data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_type(self, db):
        """Test listing notes filtered by type."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Comment", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="Highlight", note_type="highlight")

        result = await notes.call_tool("list_notes", {"note_type": "highlight"})

        data = json.loads(result[0].text)
        assert data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_list_notes_with_pagination(self, db):
        """Test listing notes with pagination."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        for i in range(10):
            NoteService.create(paper_id=paper["id"], content=f"Note {i}")

        result = await notes.call_tool("list_notes", {"limit": 5, "offset": 0})

        data = json.loads(result[0].text)
        assert len(data["data"]) == 5
        assert data["pagination"]["total"] == 10


class TestGetNoteTool:
    """Tests for get_note tool."""

    @pytest.mark.asyncio
    async def test_get_note_success(self, db):
        """Test getting a note by ID."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        note = NoteService.create(
            paper_id=paper["id"],
            content="Test content",
            note_type="comment"
        )

        result = await notes.call_tool("get_note", {"note_id": note["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["content"] == "Test content"
        assert data["data"]["note_type"] == "comment"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, db):
        """Test getting non-existent note."""
        result = await notes.call_tool("get_note", {"note_id": 99999})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "NOTE_NOT_FOUND"


class TestCreateNoteTool:
    """Tests for create_note tool."""

    @pytest.mark.asyncio
    async def test_create_note_minimal(self, db):
        """Test creating note with minimal fields."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await notes.call_tool("create_note", {
            "paper_id": paper["id"],
            "content": "New note content"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["content"] == "New note content"
        assert data["data"]["note_type"] == "comment"  # Default

    @pytest.mark.asyncio
    async def test_create_note_with_type(self, db):
        """Test creating note with specific type."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await notes.call_tool("create_note", {
            "paper_id": paper["id"],
            "content": "Highlighted text",
            "note_type": "highlight"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["note_type"] == "highlight"

    @pytest.mark.asyncio
    async def test_create_note_with_page_number(self, db):
        """Test creating note with page number."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await notes.call_tool("create_note", {
            "paper_id": paper["id"],
            "content": "Note on page 5",
            "page_number": 5
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["page_number"] == 5

    @pytest.mark.asyncio
    async def test_create_note_invalid_paper(self, db):
        """Test creating note for non-existent paper."""
        result = await notes.call_tool("create_note", {
            "paper_id": 99999,
            "content": "Orphan note"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "PAPER_NOT_FOUND"


class TestUpdateNoteTool:
    """Tests for update_note tool."""

    @pytest.mark.asyncio
    async def test_update_note_content(self, db):
        """Test updating note content."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        note = NoteService.create(paper_id=paper["id"], content="Original")

        result = await notes.call_tool("update_note", {
            "note_id": note["id"],
            "content": "Updated content"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_update_note_type(self, db):
        """Test updating note type."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        note = NoteService.create(
            paper_id=paper["id"],
            content="Note",
            note_type="comment"
        )

        result = await notes.call_tool("update_note", {
            "note_id": note["id"],
            "note_type": "summary"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["note_type"] == "summary"

    @pytest.mark.asyncio
    async def test_update_note_page_number(self, db):
        """Test updating note page number."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        note = NoteService.create(paper_id=paper["id"], content="Note")

        result = await notes.call_tool("update_note", {
            "note_id": note["id"],
            "page_number": 10
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["page_number"] == 10

    @pytest.mark.asyncio
    async def test_update_note_not_found(self, db):
        """Test updating non-existent note."""
        result = await notes.call_tool("update_note", {
            "note_id": 99999,
            "content": "New content"
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "NOTE_NOT_FOUND"


class TestDeleteNoteTool:
    """Tests for delete_note tool."""

    @pytest.mark.asyncio
    async def test_delete_note_success(self, db):
        """Test deleting a note."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        note = NoteService.create(paper_id=paper["id"], content="To Delete")

        result = await notes.call_tool("delete_note", {"note_id": note["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, db):
        """Test deleting non-existent note."""
        result = await notes.call_tool("delete_note", {"note_id": 99999})

        data = json.loads(result[0].text)
        assert data["success"] is False


class TestGetPaperNotesTool:
    """Tests for get_paper_notes tool."""

    @pytest.mark.asyncio
    async def test_get_paper_notes_success(self, db):
        """Test getting all notes for a paper."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1")
        NoteService.create(paper_id=paper["id"], content="Note 2")

        result = await notes.call_tool("get_paper_notes", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 2
        assert len(data["data"]["notes"]) == 2

    @pytest.mark.asyncio
    async def test_get_paper_notes_with_type_filter(self, db):
        """Test getting paper notes filtered by type."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Comment", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="Highlight", note_type="highlight")

        result = await notes.call_tool("get_paper_notes", {
            "paper_id": paper["id"],
            "note_type": "comment"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 1

    @pytest.mark.asyncio
    async def test_get_paper_notes_empty(self, db):
        """Test getting notes for paper with no notes."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await notes.call_tool("get_paper_notes", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_get_paper_notes_paper_not_found(self, db):
        """Test getting notes for non-existent paper.

        Note: get_paper_notes returns success=True with count=0
        for non-existent papers (doesn't validate paper exists).
        """
        result = await notes.call_tool("get_paper_notes", {"paper_id": 99999})

        data = json.loads(result[0].text)
        # Returns empty list for non-existent paper
        assert data["success"] is True
        assert data["data"]["count"] == 0


class TestDeletePaperNotesTool:
    """Tests for delete_paper_notes tool."""

    @pytest.mark.asyncio
    async def test_delete_paper_notes_all(self, db):
        """Test deleting all notes for a paper."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Note 1")
        NoteService.create(paper_id=paper["id"], content="Note 2")
        NoteService.create(paper_id=paper["id"], content="Note 3")

        result = await notes.call_tool("delete_paper_notes", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["deleted_count"] == 3

    @pytest.mark.asyncio
    async def test_delete_paper_notes_by_type(self, db):
        """Test deleting paper notes filtered by type."""
        from services import PaperService, NoteService

        paper = PaperService.create(title="Test Paper")
        NoteService.create(paper_id=paper["id"], content="Comment 1", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="Comment 2", note_type="comment")
        NoteService.create(paper_id=paper["id"], content="Highlight", note_type="highlight")

        result = await notes.call_tool("delete_paper_notes", {
            "paper_id": paper["id"],
            "note_type": "comment"
        })

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["deleted_count"] == 2

    @pytest.mark.asyncio
    async def test_delete_paper_notes_empty(self, db):
        """Test deleting notes when paper has no notes."""
        from services import PaperService

        paper = PaperService.create(title="Test Paper")

        result = await notes.call_tool("delete_paper_notes", {"paper_id": paper["id"]})

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["data"]["deleted_count"] == 0


class TestUnknownNoteTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db):
        """Test that unknown tool returns proper error."""
        result = await notes.call_tool("unknown_note_tool", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
