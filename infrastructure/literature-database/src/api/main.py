"""FastAPI application for literature database service."""
from src.api.routers.integration import router as integration_router
from src.api.routers.citations import router as citations_router
from src.api.routers.collections import router as collections_router
from src.api.converters import (
    db_paper_to_api,
    api_paper_create_to_db_data,
    api_paper_update_to_db_data,
    update_paper_relationships
)
from src.config import get_config
from src.models import Paper as PaperModel, Author as AuthorModel, Tag as TagModel, Collection as CollectionModel
from src.services.event_service import get_event_publisher
from src.services.search_service import SearchService
from src.database import get_session
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException, Depends, Query, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from loguru import logger

# Import shared types from monorepo
import sys
from pathlib import Path

# Calculate paths relative to current file location
current_file = Path(__file__).resolve()
# Go up from infrastructure/literature-database/src/api/main.py to repo root
repo_root = current_file.parent.parent.parent.parent.parent

# Add shared directory to path (not shared/types)
shared_path = str(repo_root / "shared")
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

# Add shared/types directory specifically for types import
shared_types_path = str(repo_root / "shared" / "types")
if shared_types_path not in sys.path:
    sys.path.insert(0, shared_types_path)

try:
    # Try importing from api_contracts module directly
    import api_contracts

    # Import all required types
    HealthResponse = api_contracts.HealthResponse
    PaginatedResponse = api_contracts.PaginatedResponse
    Paper = api_contracts.Paper
    PaperCreate = api_contracts.PaperCreate
    PaperUpdate = api_contracts.PaperUpdate
    SearchRequest = api_contracts.SearchRequest
    SearchResponse = api_contracts.SearchResponse
    SearchResult = api_contracts.SearchResult
    ZoteroSyncRequest = api_contracts.ZoteroSyncRequest
    ZoteroSyncResponse = api_contracts.ZoteroSyncResponse
    ZoteroSyncStatus = api_contracts.ZoteroSyncStatus
    DatabaseStats = api_contracts.DatabaseStats
    ContentStats = api_contracts.ContentStats
    ActivityStats = api_contracts.ActivityStats
    SearchIndexStats = api_contracts.SearchIndexStats
    ServiceStats = api_contracts.ServiceStats
    Author = api_contracts.Author
    Tag = api_contracts.Tag
    Collection = api_contracts.Collection

except ImportError:
    # Fallback to importlib with correct path
    import importlib.util
    api_contracts_file = str(repo_root / "shared" / "types" / "api_contracts.py")

    spec = importlib.util.spec_from_file_location("api_contracts", api_contracts_file)
    api_contracts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_contracts)

    # Import all required types
    HealthResponse = api_contracts.HealthResponse
    PaginatedResponse = api_contracts.PaginatedResponse
    Paper = api_contracts.Paper
    PaperCreate = api_contracts.PaperCreate
    PaperUpdate = api_contracts.PaperUpdate
    SearchRequest = api_contracts.SearchRequest
    SearchResponse = api_contracts.SearchResponse
    SearchResult = api_contracts.SearchResult
    ZoteroSyncRequest = api_contracts.ZoteroSyncRequest
    ZoteroSyncResponse = api_contracts.ZoteroSyncResponse
    ZoteroSyncStatus = api_contracts.ZoteroSyncStatus
    DatabaseStats = api_contracts.DatabaseStats
    ContentStats = api_contracts.ContentStats
    ActivityStats = api_contracts.ActivityStats
    SearchIndexStats = api_contracts.SearchIndexStats
    ServiceStats = api_contracts.ServiceStats
    Author = api_contracts.Author
    Tag = api_contracts.Tag
    Collection = api_contracts.Collection

# Import local components


# Load configuration
config = get_config()

# Request ID context variable for tracking
request_id_var: ContextVar[str] = ContextVar('request_id', default='')

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.logging.level.upper()),
    format=config.logging.format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.logging.file, encoding='utf-8')
    ]
)

# Configure loguru to use the same settings
logger.remove()  # Remove default handler


def format_with_request_id(record):
    request_id = record.get("extra", {}).get("request_id", "N/A")
    return "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {request_id} | {message}".format(
        time=record["time"],
        level=record["level"],
        name=record["name"],
        function=record["function"],
        line=record["line"],
        request_id=request_id,
        message=record["message"]
    )


logger.add(
    config.logging.file,
    level=config.logging.level,
    format=format_with_request_id,
    rotation=config.logging.max_size,
    retention=config.logging.backup_count,
    enqueue=True
)

app = FastAPI(
    title="Literature Database Service",
    description="Core document management service for research monorepo",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Include routers for citation, integration, and collection endpoints
app.include_router(citations_router)
app.include_router(integration_router)
app.include_router(collections_router)

# Configure CORS from config
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    """Add request ID to all requests for tracking."""
    request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)

    # Add to logger context
    with logger.contextualize(request_id=request_id):
        logger.info(f"Request started: {request.method} {request.url}")
        start_time = datetime.utcnow()

        response = await call_next(request)

        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(f"Request completed: {response.status_code} ({duration:.2f}ms)")

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        return response

# Service dependencies
search_service = SearchService()
event_publisher = get_event_publisher()

# In-memory storage for sync status (in production, use Redis)
sync_status_store: Dict[str, ZoteroSyncStatus] = {}


def get_db():
    """Dependency to get database session."""
    return next(get_session())


@app.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Service health check endpoint."""
    try:
        # Check database connection
        paper_count = db.query(PaperModel).count()
        collection_count = db.query(CollectionModel).count()

        # Check search index
        try:
            search_stats = search_service.get_index_stats()
            search_status = "ready"
        except Exception as e:
            search_stats = {"error": str(e)}
            search_status = "error"

        # Check event publisher (Redis)
        event_info = event_publisher.get_connection_info()

        return HealthResponse(
            status="healthy",
            service=config.service.name,
            version="1.0.0",
            timestamp=datetime.utcnow(),
            database={
                "status": "connected",
                "papers_count": paper_count,
                "collections_count": collection_count,
                "events": {
                    "status": "connected" if event_info["connected"] else "disconnected",
                    "redis_url": event_info["redis_url"],
                    "enabled": event_info["enabled"]
                }
            },
            search_index={
                "status": search_status,
                **search_stats
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service=config.service.name,
            version="1.0.0",
            timestamp=datetime.utcnow(),
            database={"status": "error", "error": str(e)}
        )


@app.get("/api/v1/papers", response_model=PaginatedResponse[Paper])
async def list_papers(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    offset: Optional[int] = Query(None, ge=0, description="Alias for skip (offset)"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    year: Optional[int] = Query(None, description="Filter by publication year"),
    journal: Optional[str] = Query(None, description="Filter by journal name"),
    collection: Optional[str] = Query(None, description="Filter by collection name"),
    db: Session = Depends(get_db)
):
    """List papers with pagination and filtering."""
    try:
        # Use offset if provided, otherwise use skip
        actual_offset = offset if offset is not None else skip

        # Build filters
        filters = {}
        if author:
            filters['author'] = author
        if tag:
            filters['tag'] = tag
        if year:
            filters['year'] = year
        if journal:
            filters['journal'] = journal
        if collection:
            filters['collection'] = collection

        # Get papers from database
        query = db.query(PaperModel)

        # Apply filters
        if 'author' in filters:
            query = query.join(PaperModel.authors).filter(
                AuthorModel.name.ilike(f"%{filters['author']}%")
            )
        if 'tag' in filters:
            query = query.join(PaperModel.tags).filter(
                TagModel.name.ilike(f"%{filters['tag']}%")
            )
        if 'year' in filters:
            query = query.filter(PaperModel.year == filters['year'])
        if 'journal' in filters:
            query = query.filter(
                PaperModel.journal.ilike(f"%{filters['journal']}%")
            )
        if 'collection' in filters:
            query = query.join(PaperModel.collections).filter(
                CollectionModel.name.ilike(f"%{filters['collection']}%")
            )

        db_papers = query.offset(actual_offset).limit(limit).all()

        # Get total count for pagination
        total_query = db.query(PaperModel)
        if filters:
            if 'author' in filters:
                total_query = total_query.join(PaperModel.authors).filter(
                    AuthorModel.name.ilike(f"%{filters['author']}%")
                )
            if 'tag' in filters:
                total_query = total_query.join(PaperModel.tags).filter(
                    TagModel.name.ilike(f"%{filters['tag']}%")
                )
            if 'year' in filters:
                total_query = total_query.filter(PaperModel.year == filters['year'])
            if 'journal' in filters:
                total_query = total_query.filter(
                    PaperModel.journal.ilike(f"%{filters['journal']}%")
                )

        total = total_query.count()

        # Convert to API models
        api_papers = [Paper(**db_paper_to_api(paper, db)) for paper in db_papers]

        return PaginatedResponse[Paper](
            items=api_papers,
            total=total,
            skip=actual_offset,
            limit=limit,
            has_next=(actual_offset + limit) < total
        )

    except Exception as e:
        logger.error(f"Error listing papers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list papers: {str(e)}"
        )


@app.get("/api/v1/papers/{paper_id}", response_model=Paper)
async def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """Get a single paper by ID."""
    try:
        db_paper = db.query(PaperModel).filter(PaperModel.id == paper_id).first()
        if not db_paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paper not found"
            )

        return Paper(**db_paper_to_api(db_paper, db))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper {paper_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get paper: {str(e)}"
        )


@app.post("/api/v1/search", response_model=SearchResponse)
async def search_papers(search_request: SearchRequest, db: Session = Depends(get_db)):
    """Perform full-text search across papers."""
    try:
        # Perform search using search service
        search_results = search_service.search(
            query=search_request.query,
            limit=search_request.limit,
            filters=search_request.filters
        )

        # Get paper details from database
        paper_ids = [result['id'] for result in search_results]
        db_papers = db.query(PaperModel).filter(PaperModel.id.in_(paper_ids)).all()

        # Create mapping for quick lookup
        papers_by_id = {paper.id: paper for paper in db_papers}

        # Build search results with scores
        results = []
        for search_result in search_results:
            paper_id = search_result['id']
            if paper_id in papers_by_id:
                api_paper = Paper(**db_paper_to_api(papers_by_id[paper_id], db))
                results.append(SearchResult(
                    paper=api_paper,
                    score=search_result.get('score', 0.0),
                    highlights=[]  # TODO: Add highlighting support
                ))

        return SearchResponse(
            query=search_request.query,
            total_results=len(results),
            papers=results,
            query_time_ms=None  # TODO: Add timing
        )

    except Exception as e:
        logger.error(f"Error searching papers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@app.post("/api/v1/sync/zotero", response_model=ZoteroSyncResponse)
async def trigger_zotero_sync(sync_request: ZoteroSyncRequest = None):
    """Trigger Zotero synchronization."""
    try:
        sync_id = f"sync_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Store sync status
        sync_status = ZoteroSyncStatus(
            sync_id=sync_id,
            status="started",
            started_at=datetime.utcnow(),
            log_messages=["Zotero synchronization initiated"]
        )
        sync_status_store[sync_id] = sync_status

        # TODO: Implement actual async Zotero sync
        # For now, simulate immediate completion
        import asyncio
        asyncio.create_task(simulate_sync(sync_id))

        return ZoteroSyncResponse(
            sync_id=sync_id,
            status="started",
            message="Zotero synchronization initiated",
            estimated_duration_minutes=5
        )

    except Exception as e:
        logger.error(f"Error triggering Zotero sync: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(e)}"
        )


@app.get("/api/v1/sync/zotero/{sync_id}", response_model=ZoteroSyncStatus)
async def get_sync_status(sync_id: str):
    """Get status of Zotero sync operation."""
    if sync_id not in sync_status_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync operation not found"
        )

    return sync_status_store[sync_id]


async def simulate_sync(sync_id: str):
    """Simulate Zotero sync operation."""
    import asyncio
    await asyncio.sleep(2)  # Simulate sync time

    # Update sync status
    if sync_id in sync_status_store:
        results = {
            "papers_processed": 0,
            "papers_added": 0,
            "papers_updated": 0,
            "papers_unchanged": 0,
            "attachments_linked": 0,
            "errors": 0
        }

        sync_status_store[sync_id].status = "completed"
        sync_status_store[sync_id].completed_at = datetime.utcnow()
        sync_status_store[sync_id].duration_seconds = 2
        sync_status_store[sync_id].results = results
        sync_status_store[sync_id].log_messages.extend([
            "Connected to Zotero library",
            "Processing completed",
            "Sync completed successfully"
        ])

        # Publish sync.completed event
        event_publisher.publish_sync_completed(
            sync_id=sync_id,
            results=results,
            duration_seconds=2,
            papers_processed=results["papers_processed"]
        )

        logger.info(f"Sync {sync_id} completed and event published")


@app.post("/api/v1/papers", response_model=Paper)
async def create_paper(paper_data: PaperCreate, db: Session = Depends(get_db)):
    """Create a new paper."""
    try:
        # Convert API model to database format
        paper_dict = paper_data.model_dump()
        db_data = api_paper_create_to_db_data(paper_dict)

        # Create the paper
        db_paper = PaperModel(**{k: v for k, v in db_data.items() if not k.startswith('_')})
        db.add(db_paper)
        db.flush()  # Get the ID

        # Handle relationships
        update_paper_relationships(db, db_paper, db_data)
        db.commit()

        api_paper = Paper(**db_paper_to_api(db_paper, db))

        # Add to search index
        try:
            search_service.add_paper_to_index(db_paper)
        except Exception as e:
            logger.warning(f"Failed to add paper to search index: {e}")

        # Publish paper.added event
        event_publisher.publish_paper_added(
            paper_id=db_paper.id,
            paper_title=db_paper.title,
            metadata={
                "doi": db_paper.doi,
                "year": db_paper.year,
                "journal": db_paper.journal
            }
        )

        logger.info(f"Created paper {db_paper.id}: {db_paper.title}")
        return api_paper

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except IntegrityError as e:
        db.rollback()
        # Check if it's a unique constraint violation (duplicate DOI, etc.)
        error_msg = str(e.orig).lower()
        if "unique" in error_msg or "duplicate" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A paper with this DOI already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database constraint violation: {str(e.orig)}"
        )
    except Exception as e:
        logger.error(f"Error creating paper: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create paper: {str(e)}"
        )


@app.put("/api/v1/papers/{paper_id}", response_model=Paper)
async def update_paper(paper_id: int, paper_update: PaperUpdate, db: Session = Depends(get_db)):
    """Update an existing paper."""
    try:
        # Get original paper for comparison
        original_paper = db.query(PaperModel).filter(PaperModel.id == paper_id).first()
        if not original_paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paper not found"
            )

        # Convert API model to database format
        paper_dict = paper_update.model_dump(exclude_unset=True)
        db_data = api_paper_update_to_db_data(paper_dict)

        # Update the paper
        for key, value in db_data.items():
            if not key.startswith('_') and hasattr(original_paper, key):
                setattr(original_paper, key, value)

        # Handle relationships
        update_paper_relationships(db, original_paper, db_data)
        db.commit()

        db_paper = original_paper
        api_paper = Paper(**db_paper_to_api(db_paper, db))

        # Determine what fields changed for the event
        changes = []
        update_data = paper_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                changes.append(field)

        # Publish paper.updated event
        event_publisher.publish_paper_updated(
            paper_id=db_paper.id,
            paper_title=db_paper.title,
            changes=changes,
            metadata={
                "updated_fields": changes,
                "doi": db_paper.doi,
                "year": db_paper.year
            }
        )

        logger.info(f"Updated paper {db_paper.id}: {db_paper.title}")
        return api_paper

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating paper {paper_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update paper: {str(e)}"
        )


@app.delete("/api/v1/papers/{paper_id}")
async def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """Delete a paper."""
    try:
        # Get paper info before deletion for the event
        db_paper = db.query(PaperModel).filter(PaperModel.id == paper_id).first()
        if not db_paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paper not found"
            )

        paper_title = db_paper.title
        paper_metadata = {
            "doi": db_paper.doi,
            "year": db_paper.year,
            "journal": db_paper.journal
        }

        # Delete the paper
        db.delete(db_paper)
        db.commit()

        # Publish paper.deleted event
        event_publisher.publish_paper_deleted(
            paper_id=paper_id,
            paper_title=paper_title,
            metadata=paper_metadata
        )

        logger.info(f"Deleted paper {paper_id}: {paper_title}")
        return {"message": "Paper deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting paper {paper_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete paper: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.service.host,
        port=config.service.port,
        log_config=None,  # Use our custom logging
        access_log=False  # Disable uvicorn access logs (we handle in middleware)
    )
