"""Note Service - Business logic for note operations.

This service provides all note-related operations including CRUD
and paper-specific note management.

Usage:
    from services import NoteService

    # Get notes for a paper
    notes = NoteService.get_for_paper(paper_id=123)

    # Create a note
    note = NoteService.create(paper_id=123, content="Important finding")

    # Delete all highlights for a paper
    count = NoteService.delete_for_paper(paper_id=123, note_type="highlight")
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from literature_core import (
    get_session,
    get_logger,
    Note,
    Paper,
    NoteNotFoundError,
    PaperNotFoundError,
    ValidationError,
    NoteType,
)

logger = get_logger(__name__)


@dataclass
class NoteListResult:
    """Result of a note list operation."""
    notes: list[dict]
    total: int


class NoteService:
    """Service for note-related operations."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def note_to_dict(note: Note) -> dict:
        """Convert Note model to dictionary.

        Args:
            note: Note ORM instance

        Returns:
            Dictionary representation of the note
        """
        return {
            "id": note.id,
            "paper_id": note.paper_id,
            "content": note.content,
            "note_type": note.note_type,
            "page_number": note.page_number,
            "position": note.position,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "modified_at": note.modified_at.isoformat() if note.modified_at else None,
        }

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    @classmethod
    def get(cls, note_id: int) -> dict:
        """Get a note by ID.

        Args:
            note_id: The note's database ID

        Returns:
            Dictionary representation of the note

        Raises:
            NoteNotFoundError: If note doesn't exist
        """
        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).first()
            if not note:
                raise NoteNotFoundError(note_id)
            return cls.note_to_dict(note)

    @classmethod
    def list(
        cls,
        paper_id: int | None = None,
        note_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NoteListResult:
        """List notes with optional filtering.

        Args:
            paper_id: Filter by paper ID
            note_type: Filter by note type (highlight, comment, summary)
            limit: Maximum notes to return
            offset: Skip first N notes

        Returns:
            NoteListResult with notes and total count
        """
        # Validate note_type if provided
        if note_type and not NoteType.is_valid(note_type):
            raise ValidationError("note_type", f"Must be one of: {NoteType.ALL}")

        with get_session() as session:
            query = session.query(Note)

            if paper_id:
                query = query.filter(Note.paper_id == paper_id)
            if note_type:
                query = query.filter(Note.note_type == note_type)

            total = query.count()
            notes = (
                query.order_by(Note.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            return NoteListResult(
                notes=[cls.note_to_dict(n) for n in notes],
                total=total,
            )

    @classmethod
    def create(
        cls,
        paper_id: int,
        content: str,
        note_type: str = "comment",
        page_number: int | None = None,
        position: str | None = None,
    ) -> dict:
        """Create a new note on a paper.

        Args:
            paper_id: The paper ID to attach note to
            content: Note content (required)
            note_type: Type of note (highlight, comment, summary)
            page_number: Page number in PDF
            position: Position coordinates (JSON string)

        Returns:
            Dictionary representation of the created note

        Raises:
            PaperNotFoundError: If paper doesn't exist
            ValidationError: If content is empty or note_type is invalid
        """
        if not content or not content.strip():
            raise ValidationError("content", "Note content is required")

        if note_type and not NoteType.is_valid(note_type):
            raise ValidationError("note_type", f"Must be one of: {NoteType.ALL}")

        with get_session() as session:
            # Verify paper exists
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            note = Note(
                paper_id=paper_id,
                content=content.strip(),
                note_type=note_type,
                page_number=page_number,
                position=position,
            )
            session.add(note)
            session.flush()

            logger.info(f"Created {note_type} note {note.id} for paper {paper_id}")
            return cls.note_to_dict(note)

    @classmethod
    def update(
        cls,
        note_id: int,
        content: str | None = None,
        note_type: str | None = None,
        page_number: int | None = None,
        position: str | None = None,
    ) -> dict:
        """Update an existing note.

        Args:
            note_id: Note ID to update
            content: New content
            note_type: New note type
            page_number: New page number
            position: New position

        Returns:
            Updated note dictionary

        Raises:
            NoteNotFoundError: If note doesn't exist
            ValidationError: If note_type is invalid
        """
        if note_type and not NoteType.is_valid(note_type):
            raise ValidationError("note_type", f"Must be one of: {NoteType.ALL}")

        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).first()
            if not note:
                raise NoteNotFoundError(note_id)

            if content is not None:
                note.content = content.strip()
            if note_type is not None:
                note.note_type = note_type
            if page_number is not None:
                note.page_number = page_number
            if position is not None:
                note.position = position

            note.modified_at = datetime.utcnow()

            logger.info(f"Updated note {note_id}")
            return cls.note_to_dict(note)

    @classmethod
    def delete(cls, note_id: int) -> dict:
        """Delete a note.

        Args:
            note_id: Note ID to delete

        Returns:
            Dict with deleted note ID

        Raises:
            NoteNotFoundError: If note doesn't exist
        """
        with get_session() as session:
            note = session.query(Note).filter(Note.id == note_id).first()
            if not note:
                raise NoteNotFoundError(note_id)

            session.delete(note)

            logger.info(f"Deleted note {note_id}")
            return {"id": note_id}

    # =========================================================================
    # Paper-Specific Operations
    # =========================================================================

    @classmethod
    def get_for_paper(
        cls,
        paper_id: int,
        note_type: str | None = None,
    ) -> list[dict]:
        """Get all notes for a specific paper.

        Args:
            paper_id: Paper ID
            note_type: Optional filter by note type

        Returns:
            List of note dicts ordered by page then creation time
        """
        if note_type and not NoteType.is_valid(note_type):
            raise ValidationError("note_type", f"Must be one of: {NoteType.ALL}")

        with get_session() as session:
            query = session.query(Note).filter(Note.paper_id == paper_id)

            if note_type:
                query = query.filter(Note.note_type == note_type)

            notes = query.order_by(Note.page_number, Note.created_at).all()

            return [cls.note_to_dict(n) for n in notes]

    @classmethod
    def delete_for_paper(
        cls,
        paper_id: int,
        note_type: str | None = None,
    ) -> int:
        """Delete all notes for a paper.

        Args:
            paper_id: Paper ID
            note_type: Optional filter - only delete notes of this type

        Returns:
            Number of notes deleted
        """
        if note_type and not NoteType.is_valid(note_type):
            raise ValidationError("note_type", f"Must be one of: {NoteType.ALL}")

        with get_session() as session:
            query = session.query(Note).filter(Note.paper_id == paper_id)

            if note_type:
                query = query.filter(Note.note_type == note_type)

            count = query.count()
            query.delete(synchronize_session=False)

            logger.info(f"Deleted {count} notes for paper {paper_id}")
            return count
