"""FastAPI application for literature database."""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from pathlib import Path

from src.database import get_session
from src.models import Paper, Author, Tag, Collection
from src.api.schemas import (
    PaperCreate, PaperResponse, PaperUpdate,
    AuthorResponse, TagResponse, CollectionResponse,
    SearchRequest, SearchResponse
)
from src.services.paper_service import PaperService
from src.services.search_service import SearchService
from src.extractors.zotero_sync import ZoteroSync


app = FastAPI(
    title="Literature Database API",
    description="Core API for academic paper management",
    version="1.0.0"
)

# Initialize services
paper_service = PaperService()
search_service = SearchService()
zotero_sync = ZoteroSync()


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Literature Database API",
        "version": "1.0.0",
        "docs": "/docs"
    }


# Paper endpoints
@app.get("/papers", response_model=List[PaperResponse])
async def list_papers(
    skip: int = 0,
    limit: int = 100,
    author: Optional[str] = None,
    tag: Optional[str] = None,
    year: Optional[int] = None,
    journal: Optional[str] = None,
    db: Session = Depends(get_session)
):
    """List papers with optional filtering."""
    try:
        filters = {}
        if author:
            filters['author'] = author
        if tag:
            filters['tag'] = tag
        if year:
            filters['year'] = year
        if journal:
            filters['journal'] = journal
            
        papers = paper_service.list_papers(db, skip=skip, limit=limit, filters=filters)
        return papers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/papers/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: int, db: Session = Depends(get_session)):
    """Get a single paper by ID."""
    try:
        paper = paper_service.get_paper(db, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        return paper
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/papers", response_model=PaperResponse)
async def create_paper(
    paper: PaperCreate,
    db: Session = Depends(get_session)
):
    """Create a new paper."""
    try:
        new_paper = paper_service.create_paper(db, paper)
        return new_paper
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/papers/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: int,
    paper_update: PaperUpdate,
    db: Session = Depends(get_session)
):
    """Update an existing paper."""
    try:
        updated_paper = paper_service.update_paper(db, paper_id, paper_update)
        if not updated_paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        return updated_paper
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/papers/{paper_id}")
async def delete_paper(paper_id: int, db: Session = Depends(get_session)):
    """Delete a paper."""
    try:
        success = paper_service.delete_paper(db, paper_id)
        if not success:
            raise HTTPException(status_code=404, detail="Paper not found")
        return {"message": "Paper deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# File upload endpoint
@app.post("/papers/upload")
async def upload_paper(
    file: UploadFile = File(...),
    db: Session = Depends(get_session)
):
    """Upload and process a PDF paper."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Save uploaded file
        upload_dir = Path("data/pdfs")
        upload_dir.mkdir(exist_ok=True)
        
        file_path = upload_dir / file.filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process the file
        paper = paper_service.add_paper_from_file(db, file_path)
        return paper
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


# Search endpoints
@app.post("/search", response_model=SearchResponse)
async def search_papers(search_request: SearchRequest):
    """Search papers by text query."""
    try:
        results = search_service.search(
            query=search_request.query,
            limit=search_request.limit,
            filters=search_request.filters
        )
        return SearchResponse(
            query=search_request.query,
            total_results=len(results),
            papers=results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search/reindex")
async def reindex_search():
    """Reindex all papers for search."""
    try:
        db = next(get_session())
        count = search_service.reindex_all_papers(db)
        return {"message": f"Reindexed {count} papers"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Zotero sync endpoints
@app.post("/sync/zotero")
async def sync_zotero():
    """Trigger Zotero synchronization."""
    try:
        if zotero_sync.is_api_available():
            added, updated = zotero_sync.sync_from_api()
            return {
                "message": "Zotero sync completed",
                "papers_added": added,
                "papers_updated": updated
            }
        else:
            # Try local sync
            added, updated = zotero_sync.sync_from_local_library()
            return {
                "message": "Local Zotero sync completed",
                "papers_added": added,
                "papers_updated": updated
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Statistics endpoint
@app.get("/stats")
async def get_stats(db: Session = Depends(get_session)):
    """Get database statistics."""
    try:
        stats = {
            "total_papers": db.query(Paper).count(),
            "total_authors": db.query(Author).count(),
            "total_tags": db.query(Tag).count(),
            "total_collections": db.query(Collection).count(),
        }
        
        # Papers by year
        year_counts = db.query(Paper.year, db.func.count(Paper.id)).group_by(Paper.year).all()
        stats["papers_by_year"] = {str(year): count for year, count in year_counts if year}
        
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Authors endpoint
@app.get("/authors", response_model=List[AuthorResponse])
async def list_authors(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_session)
):
    """List authors."""
    try:
        authors = db.query(Author).offset(skip).limit(limit).all()
        return authors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Tags endpoint
@app.get("/tags", response_model=List[TagResponse])
async def list_tags(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_session)
):
    """List tags."""
    try:
        tags = db.query(Tag).offset(skip).limit(limit).all()
        return tags
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Collections endpoint
@app.get("/collections", response_model=List[CollectionResponse])
async def list_collections(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_session)
):
    """List collections."""
    try:
        collections = db.query(Collection).offset(skip).limit(limit).all()
        return collections
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)