"""Integration API router for AI service communication."""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database import get_session
from src.models import Paper, Manuscript, PaperContent, ProjectRelevance, Tag
from src.api.schemas import (
    PaperContentResponse, AIMetadataUpdate, HealthResponse,
    PaperContentCreate, PaperContentUpdate, PaperContentStoredResponse,
    ProjectRelevanceCreate, ProjectRelevanceUpdate, ProjectRelevanceResponse,
    ProjectPapersResponse, ExtractionQueueResponse, ExtractionStatsResponse
)

router = APIRouter(prefix="/api/v1", tags=["integration"])


def get_db():
    """Dependency to get database session."""
    return next(get_session())


# ========== Integration Health Endpoint ==========

@router.get("/integration/health", response_model=HealthResponse)
async def integration_health(db: Session = Depends(get_db)):
    """Health check for external services."""
    try:
        papers_count = db.query(Paper).count()
        manuscripts_count = db.query(Manuscript).count()

        return HealthResponse(
            status="healthy",
            database="connected",
            search_index="available",
            papers_count=papers_count,
            manuscripts_count=manuscripts_count
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            database=str(e),
            search_index="unknown",
            papers_count=0,
            manuscripts_count=0
        )


# ========== Paper Content for AI Processing ==========

@router.get("/integration/papers/{paper_id}/content", response_model=PaperContentResponse)
async def get_paper_content(paper_id: int, db: Session = Depends(get_db)):
    """Get full paper content for AI processing."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        return PaperContentResponse(
            id=paper.id,
            title=paper.title,
            abstract=paper.abstract,
            year=paper.year,
            doi=paper.doi,
            citation_key=paper.citation_key,
            full_text=paper.full_text,
            authors=[author.name for author in paper.authors],
            tags=[tag.name for tag in paper.tags]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integration/papers/uncategorized", response_model=List[PaperContentResponse])
async def get_uncategorized_papers(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get papers that need AI categorization (no tags)."""
    try:
        papers = db.query(Paper).filter(
            ~Paper.tags.any()
        ).limit(limit).all()

        return [
            PaperContentResponse(
                id=paper.id,
                title=paper.title,
                abstract=paper.abstract,
                year=paper.year,
                doi=paper.doi,
                citation_key=paper.citation_key,
                full_text=paper.full_text,
                authors=[author.name for author in paper.authors],
                tags=[]
            )
            for paper in papers
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/integration/papers/{paper_id}/ai-metadata")
async def update_ai_metadata(
    paper_id: int,
    metadata: AIMetadataUpdate,
    db: Session = Depends(get_db)
):
    """Update paper with AI-generated metadata."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        # Apply suggested tags if provided
        if metadata.suggested_tags:
            for tag_name in metadata.suggested_tags:
                tag = db.query(Tag).filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, category="ai-suggested")
                    db.add(tag)
                if tag not in paper.tags:
                    paper.tags.append(tag)

        db.commit()
        return {"message": "AI metadata applied", "paper_id": paper_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Paper Content Extraction Endpoints ==========

@router.get("/papers/{paper_id}/content", response_model=PaperContentStoredResponse)
async def get_paper_extracted_content(paper_id: int, db: Session = Depends(get_db)):
    """Get AI-extracted content for a paper."""
    try:
        content = db.query(PaperContent).filter_by(paper_id=paper_id).first()
        if not content:
            raise HTTPException(status_code=404, detail="No extracted content found for this paper")
        return content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/papers/{paper_id}/content", response_model=PaperContentStoredResponse)
async def create_paper_content(
    paper_id: int,
    content_data: PaperContentCreate,
    db: Session = Depends(get_db)
):
    """Store AI-extracted content for a paper."""
    try:
        # Check paper exists
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        # Check if content already exists
        existing = db.query(PaperContent).filter_by(paper_id=paper_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Content already exists. Use PUT to update.")

        # Create new content
        content = PaperContent(
            paper_id=paper_id,
            extraction_depth=content_data.extraction_depth,
            extractor_model=content_data.extractor_model,
            paper_type=content_data.paper_type,
            topics=content_data.topics,
            one_sentence_summary=content_data.one_sentence_summary,
            key_findings=[f.model_dump() for f in content_data.key_findings] if content_data.key_findings else None,
            methodology_summary=content_data.methodology_summary,
            structured_data=content_data.structured_data
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        return content
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/papers/{paper_id}/content", response_model=PaperContentStoredResponse)
async def update_paper_content(
    paper_id: int,
    content_data: PaperContentUpdate,
    db: Session = Depends(get_db)
):
    """Update AI-extracted content for a paper."""
    try:
        content = db.query(PaperContent).filter_by(paper_id=paper_id).first()
        if not content:
            raise HTTPException(status_code=404, detail="No extracted content found for this paper")

        update_data = content_data.model_dump(exclude_unset=True)
        if 'key_findings' in update_data and update_data['key_findings']:
            update_data['key_findings'] = [f.model_dump() if hasattr(
                f, 'model_dump') else f for f in update_data['key_findings']]

        for key, value in update_data.items():
            setattr(content, key, value)

        db.commit()
        db.refresh(content)
        return content
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/papers/{paper_id}/content")
async def delete_paper_content(paper_id: int, db: Session = Depends(get_db)):
    """Delete AI-extracted content for a paper."""
    try:
        content = db.query(PaperContent).filter_by(paper_id=paper_id).first()
        if not content:
            raise HTTPException(status_code=404, detail="No extracted content found for this paper")

        db.delete(content)
        db.commit()
        return {"message": "Content deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ========== Project Relevance Endpoints ==========

@router.get("/papers/{paper_id}/relevance", response_model=List[ProjectRelevanceResponse])
async def get_paper_relevance(paper_id: int, db: Session = Depends(get_db)):
    """Get all project relevances for a paper."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        relevances = db.query(ProjectRelevance).filter_by(paper_id=paper_id).all()
        return relevances
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/papers/{paper_id}/relevance", response_model=ProjectRelevanceResponse)
async def add_paper_relevance(
    paper_id: int,
    relevance_data: ProjectRelevanceCreate,
    db: Session = Depends(get_db)
):
    """Add project relevance for a paper."""
    try:
        paper = db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        # Check if relevance for this project already exists
        existing = db.query(ProjectRelevance).filter_by(
            paper_id=paper_id,
            project_name=relevance_data.project_name
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Relevance for project '{relevance_data.project_name}' already exists. Use PUT to update."
            )

        relevance = ProjectRelevance(
            paper_id=paper_id,
            project_name=relevance_data.project_name,
            overall_relevance=relevance_data.overall_relevance,
            relevance_summary=relevance_data.relevance_summary,
            primary_use=relevance_data.primary_use
        )
        db.add(relevance)
        db.commit()
        db.refresh(relevance)
        return relevance
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/papers/{paper_id}/relevance/{project_name}", response_model=ProjectRelevanceResponse)
async def update_paper_relevance(
    paper_id: int,
    project_name: str,
    relevance_data: ProjectRelevanceUpdate,
    db: Session = Depends(get_db)
):
    """Update project relevance for a paper."""
    try:
        relevance = db.query(ProjectRelevance).filter_by(
            paper_id=paper_id,
            project_name=project_name
        ).first()
        if not relevance:
            raise HTTPException(status_code=404, detail="Relevance not found")

        update_data = relevance_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(relevance, key, value)

        db.commit()
        db.refresh(relevance)
        return relevance
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/papers/{paper_id}/relevance/{project_name}")
async def delete_paper_relevance(
    paper_id: int,
    project_name: str,
    db: Session = Depends(get_db)
):
    """Delete project relevance for a paper."""
    try:
        relevance = db.query(ProjectRelevance).filter_by(
            paper_id=paper_id,
            project_name=project_name
        ).first()
        if not relevance:
            raise HTTPException(status_code=404, detail="Relevance not found")

        db.delete(relevance)
        db.commit()
        return {"message": "Relevance deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/papers", response_model=ProjectPapersResponse)
async def get_project_papers(
    project_name: str,
    min_relevance: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all papers relevant to a project."""
    try:
        query = db.query(ProjectRelevance).filter_by(project_name=project_name)

        # Filter by minimum relevance if specified
        if min_relevance:
            relevance_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE']
            if min_relevance not in relevance_order:
                raise HTTPException(status_code=400, detail=f"Invalid relevance level: {min_relevance}")
            min_index = relevance_order.index(min_relevance)
            valid_levels = relevance_order[:min_index + 1]
            query = query.filter(ProjectRelevance.overall_relevance.in_(valid_levels))

        relevances = query.all()

        # Count by relevance level
        by_relevance = {}
        for r in relevances:
            by_relevance[r.overall_relevance] = by_relevance.get(r.overall_relevance, 0) + 1

        # Build paper list
        papers = []
        for r in relevances:
            paper = r.paper
            papers.append({
                'paper_id': paper.id,
                'title': paper.title,
                'year': paper.year,
                'overall_relevance': r.overall_relevance,
                'relevance_summary': r.relevance_summary,
                'primary_use': r.primary_use
            })

        return ProjectPapersResponse(
            project_name=project_name,
            total_papers=len(papers),
            papers_by_relevance=by_relevance,
            papers=papers
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/papers/critical")
async def get_project_critical_papers(project_name: str, db: Session = Depends(get_db)):
    """Get CRITICAL papers for a project."""
    try:
        relevances = db.query(ProjectRelevance).filter_by(
            project_name=project_name,
            overall_relevance='CRITICAL'
        ).all()

        papers = []
        for r in relevances:
            paper = r.paper
            papers.append({
                'paper_id': paper.id,
                'title': paper.title,
                'year': paper.year,
                'doi': paper.doi,
                'relevance_summary': r.relevance_summary,
                'primary_use': r.primary_use
            })

        return {
            'project_name': project_name,
            'critical_count': len(papers),
            'papers': papers
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Extraction Queue Endpoints ==========

@router.get("/extraction/queue", response_model=ExtractionQueueResponse)
async def get_extraction_queue(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get papers needing extraction."""
    try:
        total_papers = db.query(Paper).count()

        # Count by extraction depth
        content_counts = db.query(
            PaperContent.extraction_depth,
            func.count(PaperContent.id)
        ).group_by(PaperContent.extraction_depth).all()

        depth_counts = {depth: count for depth, count in content_counts}

        # Papers without any extraction
        extracted_paper_ids = db.query(PaperContent.paper_id).subquery()
        unextracted_papers = db.query(Paper).filter(
            ~Paper.id.in_(extracted_paper_ids)
        ).limit(limit).all()

        return ExtractionQueueResponse(
            total_papers=total_papers,
            unextracted=total_papers - sum(depth_counts.values()),
            citation_only=depth_counts.get('CITATION_ONLY', 0),
            basic=depth_counts.get('BASIC', 0),
            comprehensive=depth_counts.get('COMPREHENSIVE', 0),
            papers_needing_extraction=[
                {
                    'paper_id': p.id,
                    'title': p.title,
                    'year': p.year,
                    'current_depth': None
                }
                for p in unextracted_papers
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/stats", response_model=ExtractionStatsResponse)
async def get_extraction_stats(db: Session = Depends(get_db)):
    """Get extraction statistics."""
    try:
        total_papers = db.query(Paper).count()

        # Count by extraction depth
        depth_counts = dict(
            db.query(
                PaperContent.extraction_depth,
                func.count(PaperContent.id)
            ).group_by(PaperContent.extraction_depth).all()
        )

        # Count by model
        model_counts = dict(
            db.query(
                PaperContent.extractor_model,
                func.count(PaperContent.id)
            ).filter(PaperContent.extractor_model.isnot(None)
                     ).group_by(PaperContent.extractor_model).all()
        )

        # Average findings per paper
        contents_with_findings = db.query(PaperContent).filter(
            PaperContent.key_findings.isnot(None)
        ).all()

        total_findings = sum(
            len(c.key_findings) if c.key_findings else 0
            for c in contents_with_findings
        )
        avg_findings = total_findings / len(contents_with_findings) if contents_with_findings else 0

        # Recent extractions (last 7 days)
        week_ago = datetime.now() - timedelta(days=7)
        recent = db.query(PaperContent).filter(
            PaperContent.extraction_date >= week_ago
        ).count()

        return ExtractionStatsResponse(
            total_papers=total_papers,
            extraction_counts=depth_counts,
            by_model=model_counts,
            average_findings_per_paper=round(avg_findings, 2),
            recent_extractions=recent
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
