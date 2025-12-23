"""Collection management API router."""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.database import get_session
from src.models import Collection, Paper
from src.api.schemas import (
    CollectionCreate, CollectionUpdate, CollectionResponse,
    CollectionWithPapersResponse, CollectionPaperAction
)

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


def get_db():
    """Dependency to get database session."""
    return next(get_session())


@router.get("", response_model=List[CollectionWithPapersResponse])
async def list_collections(
    parent_id: int = None,
    db: Session = Depends(get_db)
):
    """List all collections, optionally filtered by parent."""
    try:
        query = db.query(Collection)
        if parent_id is not None:
            query = query.filter(Collection.parent_id == parent_id)
        else:
            # Get root collections (no parent)
            query = query.filter(Collection.parent_id.is_(None))

        collections = query.all()
        return [
            CollectionWithPapersResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                parent_id=c.parent_id,
                zotero_key=c.zotero_key,
                paper_count=len(c.papers),
                paper_ids=[p.id for p in c.papers]
            )
            for c in collections
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all", response_model=List[CollectionWithPapersResponse])
async def list_all_collections(db: Session = Depends(get_db)):
    """List all collections (flat list, ignores hierarchy)."""
    try:
        collections = db.query(Collection).all()
        return [
            CollectionWithPapersResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                parent_id=c.parent_id,
                zotero_key=c.zotero_key,
                paper_count=len(c.papers),
                paper_ids=[p.id for p in c.papers]
            )
            for c in collections
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CollectionResponse)
async def create_collection(
    collection: CollectionCreate,
    db: Session = Depends(get_db)
):
    """Create a new collection."""
    try:
        # Validate parent exists if specified
        if collection.parent_id:
            parent = db.query(Collection).filter_by(id=collection.parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent collection not found")

        db_collection = Collection(
            name=collection.name,
            description=collection.description,
            parent_id=collection.parent_id
        )
        db.add(db_collection)
        db.commit()
        db.refresh(db_collection)
        return db_collection
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{collection_id}", response_model=CollectionWithPapersResponse)
async def get_collection(collection_id: int, db: Session = Depends(get_db)):
    """Get a collection by ID."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        return CollectionWithPapersResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            parent_id=collection.parent_id,
            zotero_key=collection.zotero_key,
            paper_count=len(collection.papers),
            paper_ids=[p.id for p in collection.papers]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    collection_update: CollectionUpdate,
    db: Session = Depends(get_db)
):
    """Update a collection."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        update_data = collection_update.model_dump(exclude_unset=True)

        # Validate parent if being changed
        if "parent_id" in update_data and update_data["parent_id"]:
            if update_data["parent_id"] == collection_id:
                raise HTTPException(status_code=400, detail="Collection cannot be its own parent")
            parent = db.query(Collection).filter_by(id=update_data["parent_id"]).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent collection not found")

        for key, value in update_data.items():
            setattr(collection, key, value)

        db.commit()
        db.refresh(collection)
        return collection
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{collection_id}")
async def delete_collection(collection_id: int, db: Session = Depends(get_db)):
    """Delete a collection."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Note: Papers are NOT deleted, just the association
        db.delete(collection)
        db.commit()
        return {"message": "Collection deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ========== Paper-Collection Association Endpoints ==========

@router.post("/{collection_id}/papers")
async def add_papers_to_collection(
    collection_id: int,
    action: CollectionPaperAction,
    db: Session = Depends(get_db)
):
    """Add papers to a collection."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        papers = db.query(Paper).filter(Paper.id.in_(action.paper_ids)).all()
        found_ids = {p.id for p in papers}
        missing_ids = set(action.paper_ids) - found_ids

        added = []
        already_in = []
        for paper in papers:
            if paper not in collection.papers:
                collection.papers.append(paper)
                added.append(paper.id)
            else:
                already_in.append(paper.id)

        db.commit()
        return {
            "message": "Papers added to collection",
            "added": added,
            "already_in_collection": already_in,
            "not_found": list(missing_ids)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{collection_id}/papers")
async def remove_papers_from_collection(
    collection_id: int,
    action: CollectionPaperAction,
    db: Session = Depends(get_db)
):
    """Remove papers from a collection."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        removed = []
        not_in_collection = []
        for paper_id in action.paper_ids:
            paper = db.query(Paper).filter_by(id=paper_id).first()
            if paper and paper in collection.papers:
                collection.papers.remove(paper)
                removed.append(paper_id)
            else:
                not_in_collection.append(paper_id)

        db.commit()
        return {
            "message": "Papers removed from collection",
            "removed": removed,
            "not_in_collection": not_in_collection
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{collection_id}/children", response_model=List[CollectionWithPapersResponse])
async def get_collection_children(collection_id: int, db: Session = Depends(get_db)):
    """Get child collections of a collection."""
    try:
        collection = db.query(Collection).filter_by(id=collection_id).first()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        children = db.query(Collection).filter_by(parent_id=collection_id).all()
        return [
            CollectionWithPapersResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                parent_id=c.parent_id,
                zotero_key=c.zotero_key,
                paper_count=len(c.papers),
                paper_ids=[p.id for p in c.papers]
            )
            for c in children
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
