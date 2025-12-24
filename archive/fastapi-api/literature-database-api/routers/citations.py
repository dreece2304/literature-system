"""Citation and Manuscript management API router."""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.database import get_session
from src.models import Paper
from src.services.citation_service import CitationService
from src.api.schemas import (
    ManuscriptCreate, ManuscriptUpdate, ManuscriptResponse,
    CitationLocationResponse, CitationScanRequest, CitationScanResponse,
    CitationCheckResponse, SetCitationKeyRequest, CitationKeySuggestion,
    CitationReportEntry, CitationReportResponse
)

router = APIRouter(prefix="/api/v1", tags=["citations"])


def get_db():
    """Dependency to get database session."""
    return next(get_session())


# ========== Manuscript Endpoints ==========

@router.get("/manuscripts", response_model=List[ManuscriptResponse])
async def list_manuscripts(db: Session = Depends(get_db)):
    """List all registered manuscripts."""
    try:
        service = CitationService(db)
        return service.list_manuscripts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manuscripts", response_model=ManuscriptResponse)
async def create_manuscript(
    manuscript: ManuscriptCreate,
    db: Session = Depends(get_db)
):
    """Register a new manuscript project."""
    try:
        service = CitationService(db)
        return service.register_manuscript(
            name=manuscript.name,
            project_path=manuscript.project_path,
            tex_directory=manuscript.tex_directory,
            bib_file=manuscript.bib_file,
            description=manuscript.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manuscripts/{manuscript_id}", response_model=ManuscriptResponse)
async def get_manuscript(manuscript_id: int, db: Session = Depends(get_db)):
    """Get a manuscript by ID."""
    try:
        service = CitationService(db)
        manuscript = service.get_manuscript(manuscript_id)
        if not manuscript:
            raise HTTPException(status_code=404, detail="Manuscript not found")
        return manuscript
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/manuscripts/{manuscript_id}", response_model=ManuscriptResponse)
async def update_manuscript(
    manuscript_id: int,
    manuscript_update: ManuscriptUpdate,
    db: Session = Depends(get_db)
):
    """Update a manuscript."""
    try:
        service = CitationService(db)
        update_data = manuscript_update.model_dump(exclude_unset=True)
        updated = service.update_manuscript(manuscript_id, **update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Manuscript not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/manuscripts/{manuscript_id}")
async def delete_manuscript(manuscript_id: int, db: Session = Depends(get_db)):
    """Delete a manuscript and all its citation locations."""
    try:
        service = CitationService(db)
        if not service.delete_manuscript(manuscript_id):
            raise HTTPException(status_code=404, detail="Manuscript not found")
        return {"message": "Manuscript deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Citation Scanning Endpoints ==========

@router.post("/citations/scan/{manuscript_id}", response_model=CitationScanResponse)
async def scan_citations(
    manuscript_id: int,
    scan_request: CitationScanRequest = CitationScanRequest(),
    db: Session = Depends(get_db)
):
    """Scan a manuscript for citations in LaTeX files."""
    try:
        service = CitationService(db)
        result = service.scan_citations(
            manuscript_id,
            clear_existing=scan_request.clear_existing
        )
        return CitationScanResponse(
            manuscript_id=result.manuscript_id,
            total_citations=result.total_citations,
            unique_keys=result.unique_keys,
            matched_to_papers=result.matched_to_papers,
            unmatched_keys=result.unmatched_keys,
            locations_created=result.locations_created
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/citations/check/{manuscript_id}", response_model=CitationCheckResponse)
async def check_citations(manuscript_id: int, db: Session = Depends(get_db)):
    """Check citation consistency for a manuscript."""
    try:
        service = CitationService(db)
        result = service.check_citations(manuscript_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/citations/report/{manuscript_id}", response_model=CitationReportResponse)
async def get_citation_report(manuscript_id: int, db: Session = Depends(get_db)):
    """Get a detailed citation report for a manuscript."""
    try:
        service = CitationService(db)
        manuscript = service.get_manuscript(manuscript_id)
        if not manuscript:
            raise HTTPException(status_code=404, detail="Manuscript not found")

        locations = service.get_manuscript_citations(manuscript_id)

        # Group by citation key
        by_key = {}
        for loc in locations:
            if loc.citation_key not in by_key:
                by_key[loc.citation_key] = {
                    'locations': [],
                    'paper': loc.paper
                }
            by_key[loc.citation_key]['locations'].append(loc)

        entries = []
        for key, data in sorted(by_key.items(), key=lambda x: -len(x[1]['locations'])):
            paper = data['paper']
            entries.append(CitationReportEntry(
                citation_key=key,
                paper_id=paper.id if paper else None,
                paper_title=paper.title if paper else None,
                total_citations=len(data['locations']),
                locations=[CitationLocationResponse.model_validate(loc) for loc in data['locations']]
            ))

        return CitationReportResponse(
            manuscript_id=manuscript.id,
            manuscript_name=manuscript.name,
            last_scanned=manuscript.last_scanned,
            total_unique_citations=len(by_key),
            total_citation_instances=len(locations),
            entries=entries
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/citations/export/{manuscript_id}")
async def export_citations(
    manuscript_id: int,
    format: str = "json",
    db: Session = Depends(get_db)
):
    """Export citation registry in JSON or CSV format."""
    try:
        service = CitationService(db)
        output = service.export_registry(manuscript_id, format=format)

        if format == "json":
            return JSONResponse(content={"data": output})
        else:
            return JSONResponse(content={"csv_data": output})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Paper Citation Key Endpoints ==========

@router.get("/papers/{paper_id}/citations", response_model=List[CitationLocationResponse])
async def get_paper_citation_locations(paper_id: int, db: Session = Depends(get_db)):
    """Get all locations where a paper is cited."""
    try:
        service = CitationService(db)
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        return service.get_paper_citations(paper_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/papers/{paper_id}/citation-key")
async def set_paper_citation_key(
    paper_id: int,
    request: SetCitationKeyRequest,
    db: Session = Depends(get_db)
):
    """Set the citation key for a paper."""
    try:
        service = CitationService(db)
        if not service.set_citation_key(paper_id, request.citation_key):
            raise HTTPException(status_code=404, detail="Paper not found")
        return {"message": f"Citation key set to '{request.citation_key}'"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/citations/suggestions", response_model=List[CitationKeySuggestion])
async def get_citation_key_suggestions(db: Session = Depends(get_db)):
    """Get citation key suggestions for papers without one."""
    try:
        service = CitationService(db)
        suggestions = service.suggest_citation_keys()
        return [
            CitationKeySuggestion(
                paper_id=paper.id,
                paper_title=paper.title,
                suggested_key=key
            )
            for paper, key in suggestions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
