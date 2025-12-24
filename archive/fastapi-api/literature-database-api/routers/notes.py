"""Note management API router."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from src.database import get_session
from src.models import Note, Paper
from src.api.schemas import NoteCreate, NoteResponse, NoteBase

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


def get_db():
    """Dependency to get database session."""
    return next(get_session())


@router.get("", response_model=List[NoteResponse])
async def list_notes(
    paper_id: Optional[int] = Query(None, description="Filter by paper ID"),
    note_type: Optional[str] = Query(None, description="Filter by note type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List notes with optional filtering."""
    try:
        query = db.query(Note)

        if paper_id is not None:
            query = query.filter(Note.paper_id == paper_id)
        if note_type:
            query = query.filter(Note.note_type == note_type)

        query = query.order_by(Note.created_at.desc())
        notes = query.offset(offset).limit(limit).all()
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: int, db: Session = Depends(get_db)):
    """Get a note by ID."""
    try:
        note = db.query(Note).filter_by(id=note_id).first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return note
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=NoteResponse)
async def create_note(note: NoteCreate, db: Session = Depends(get_db)):
    """Create a new note."""
    try:
        # Validate paper exists
        paper = db.query(Paper).filter_by(id=note.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        db_note = Note(
            paper_id=note.paper_id,
            content=note.content,
            note_type=note.note_type,
            page_number=note.page_number,
            position=note.position
        )
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        return db_note
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: int, note_update: NoteBase, db: Session = Depends(get_db)):
    """Update a note."""
    try:
        note = db.query(Note).filter_by(id=note_id).first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        update_data = note_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(note, key, value)

        db.commit()
        db.refresh(note)
        return note
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{note_id}")
async def delete_note(note_id: int, db: Session = Depends(get_db)):
    """Delete a note."""
    try:
        note = db.query(Note).filter_by(id=note_id).first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        db.delete(note)
        db.commit()
        return {"message": "Note deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ========== Paper-specific Note Endpoints ==========

@router.get("/paper/{paper_id}", response_model=List[NoteResponse])
async def get_paper_notes(
    paper_id: int,
    note_type: Optional[str] = Query(None, description="Filter by note type"),
    db: Session = Depends(get_db)
):
    """Get all notes for a specific paper."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        query = db.query(Note).filter(Note.paper_id == paper_id)
        if note_type:
            query = query.filter(Note.note_type == note_type)

        notes = query.order_by(Note.page_number, Note.created_at).all()
        return notes
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/paper/{paper_id}")
async def delete_paper_notes(
    paper_id: int,
    note_type: Optional[str] = Query(None, description="Only delete notes of this type"),
    db: Session = Depends(get_db)
):
    """Delete all notes for a paper (optionally filtered by type)."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        query = db.query(Note).filter(Note.paper_id == paper_id)
        if note_type:
            query = query.filter(Note.note_type == note_type)

        count = query.count()
        query.delete()
        db.commit()
        return {"message": f"Deleted {count} notes"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
