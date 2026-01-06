"""Paper Import Service - Unified intelligent paper import workflow.

This service provides a smart import wizard that:
1. Accepts DOI, arXiv ID, or title (with optional disambiguation hints)
2. Queries external sources with priority fallback (CrossRef → OpenAlex → Semantic Scholar)
3. Merges results from multiple sources, filling missing fields
4. Checks for duplicates before import (DOI, arXiv ID, title similarity)
5. Tracks metadata provenance and confidence
6. Determines enrichment needs
7. Optionally triggers PDF chunking

Usage:
    from services import PaperImportService

    # Import by DOI (most reliable)
    result = await PaperImportService.import_paper(doi="10.1021/acs.chemmater.5b00123")

    # Import by arXiv ID
    result = await PaperImportService.import_paper(arxiv_id="2301.12345")

    # Import by title (with disambiguation)
    result = await PaperImportService.import_paper(
        title="Atomic Layer Deposition of ZnO",
        authors="Johnson",
        year=2020
    )

    # Full import with PDF and tags
    result = await PaperImportService.import_paper(
        doi="10.1021/...",
        tags=["ald", "review"],
        collection_id=5,
        pdf_path="/path/to/paper.pdf"
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Author,
    Tag,
    Collection,
    PaperNotFoundError,
    ValidationError,
    MetadataSource,
    EnrichmentStatus,
    ImportMethod,
)

logger = get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SourceResult:
    """Result from a single external source lookup."""

    source: str
    success: bool
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    journal: str | None = None
    volume: str | None = None
    pages: str | None = None
    citation_count: int | None = None
    pdf_url: str | None = None
    confidence: float = 0.0
    error: str | None = None


@dataclass
class MergedMetadata:
    """Merged metadata from multiple sources."""

    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    abstract: str | None
    journal: str | None
    volume: str | None
    pages: str | None
    citation_count: int | None
    pdf_url: str | None
    primary_source: str
    confidence: float
    sources_used: list[str]
    missing_fields: list[str]


@dataclass
class DuplicateCheck:
    """Result of duplicate detection."""

    is_duplicate: bool
    match_type: str | None = None  # doi, arxiv_id, title_similarity
    existing_paper_id: int | None = None
    existing_paper_title: str | None = None
    similarity: float | None = None


@dataclass
class ImportWizardResult:
    """Complete result of the import wizard."""

    status: str  # success, duplicate, not_found, error
    paper_id: int | None = None
    paper: dict | None = None

    # Provenance
    metadata_source: str | None = None
    metadata_confidence: float | None = None
    sources_checked: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)

    # Enrichment status
    enrichment_status: str | None = None
    missing_fields: list[str] = field(default_factory=list)

    # Duplicate info (if applicable)
    duplicate_info: DuplicateCheck | None = None

    # Warnings/info
    warnings: list[str] = field(default_factory=list)
    message: str | None = None


# =============================================================================
# Service Class
# =============================================================================


class PaperImportService:
    """Unified paper import service with intelligent workflow."""

    # Source priority for metadata lookup
    SOURCE_PRIORITY = [
        MetadataSource.CROSSREF,
        MetadataSource.OPENALEX,
        MetadataSource.SEMANTIC_SCHOLAR,
        MetadataSource.ARXIV,
    ]

    # Title similarity threshold for duplicate detection
    TITLE_SIMILARITY_THRESHOLD = 0.92

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    @classmethod
    async def import_paper(
        cls,
        doi: str | None = None,
        arxiv_id: str | None = None,
        title: str | None = None,
        authors: str | None = None,  # For disambiguation
        year: int | None = None,  # For disambiguation
        tags: list[str] | None = None,
        collection_id: int | None = None,
        pdf_path: str | None = None,
        skip_duplicate_check: bool = False,
        auto_chunk_pdf: bool = True,
    ) -> ImportWizardResult:
        """
        Import a paper using the unified wizard workflow.

        Args:
            doi: DOI to look up
            arxiv_id: arXiv ID to look up
            title: Title to search for (with optional author/year for disambiguation)
            authors: Author string for disambiguation when searching by title
            year: Publication year for disambiguation
            tags: Tags to apply to imported paper
            collection_id: Collection to add paper to
            pdf_path: Local PDF path to attach
            skip_duplicate_check: Skip duplicate detection
            auto_chunk_pdf: Auto-trigger PDF chunking if PDF provided

        Returns:
            ImportWizardResult with full details
        """
        # Validate input
        if not doi and not arxiv_id and not title:
            raise ValidationError(
                "identifier",
                "Must provide at least one of: doi, arxiv_id, or title",
            )

        sources_checked: list[str] = []
        warnings: list[str] = []

        # Step 1: Fetch metadata from external sources
        merged = await cls._fetch_and_merge_metadata(
            doi=doi,
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            year=year,
            sources_checked=sources_checked,
        )

        if not merged:
            return ImportWizardResult(
                status="not_found",
                sources_checked=sources_checked,
                message="Could not find paper metadata in any source",
            )

        # Step 2: Check for duplicates
        if not skip_duplicate_check:
            dup_check = cls._check_duplicates(
                doi=merged.doi,
                arxiv_id=merged.arxiv_id,
                title=merged.title,
            )

            if dup_check.is_duplicate:
                return ImportWizardResult(
                    status="duplicate",
                    paper_id=dup_check.existing_paper_id,
                    duplicate_info=dup_check,
                    sources_checked=sources_checked,
                    message=f"Paper already exists (matched by {dup_check.match_type})",
                )

        # Step 3: Determine enrichment status
        enrichment_status = cls._determine_enrichment_status(
            merged=merged,
            has_pdf=pdf_path is not None,
        )

        # Step 4: Create paper
        paper_dict = cls._create_paper(
            merged=merged,
            tags=tags,
            collection_id=collection_id,
            pdf_path=pdf_path,
            enrichment_status=enrichment_status,
        )

        # Step 5: Auto-chunk PDF if requested
        if pdf_path and auto_chunk_pdf:
            try:
                from services.chunked_extraction_service import ChunkedExtractionService

                result = ChunkedExtractionService.extract_and_store(paper_id=paper_dict["id"])
                if result.success:
                    # Update enrichment status
                    enrichment_status = EnrichmentStatus.COMPLETE
                    cls._update_enrichment_status(paper_dict["id"], enrichment_status)
                else:
                    warnings.append(f"PDF chunking failed: {result.error}")
            except Exception as e:
                warnings.append(f"PDF chunking error: {str(e)}")

        return ImportWizardResult(
            status="success",
            paper_id=paper_dict["id"],
            paper=paper_dict,
            metadata_source=merged.primary_source,
            metadata_confidence=merged.confidence,
            sources_checked=sources_checked,
            sources_used=merged.sources_used,
            enrichment_status=enrichment_status,
            missing_fields=merged.missing_fields,
            warnings=warnings,
            message=f"Paper imported successfully from {merged.primary_source}",
        )

    # =========================================================================
    # Metadata Fetching
    # =========================================================================

    @classmethod
    async def _fetch_and_merge_metadata(
        cls,
        doi: str | None,
        arxiv_id: str | None,
        title: str | None,
        authors: str | None,
        year: int | None,
        sources_checked: list[str],
    ) -> MergedMetadata | None:
        """Fetch metadata from multiple sources and merge."""
        from services.external_search import ExternalSearchService

        service = ExternalSearchService()
        results: list[SourceResult] = []

        # Determine lookup strategy based on input
        if doi:
            # DOI lookup - most reliable
            for source in cls.SOURCE_PRIORITY:
                if source == MetadataSource.ARXIV:
                    continue  # arXiv doesn't have DOI lookup
                sources_checked.append(source)
                result = await cls._lookup_by_doi(service, doi, source)
                if result.success:
                    results.append(result)
                    # CrossRef is authoritative for DOI - can stop early if good result
                    if source == MetadataSource.CROSSREF and result.confidence > 0.9:
                        break

        elif arxiv_id:
            # arXiv ID lookup
            sources_checked.append(MetadataSource.ARXIV)
            result = await cls._lookup_by_arxiv(service, arxiv_id)
            if result.success:
                results.append(result)

            # Also try Semantic Scholar which indexes arXiv
            sources_checked.append(MetadataSource.SEMANTIC_SCHOLAR)
            ss_result = await cls._lookup_arxiv_semantic_scholar(service, arxiv_id)
            if ss_result.success:
                results.append(ss_result)

        else:
            # Title search - need to check multiple sources
            for source in cls.SOURCE_PRIORITY:
                sources_checked.append(source)
                result = await cls._search_by_title(
                    service, title, authors, year, source  # type: ignore
                )
                if result.success and result.confidence > 0.5:
                    results.append(result)

        if not results:
            return None

        # Merge results from all successful sources
        return cls._merge_results(results)

    @classmethod
    async def _lookup_by_doi(
        cls, service, doi: str, source: str
    ) -> SourceResult:
        """Look up paper by DOI from a specific source."""
        try:
            if source == MetadataSource.CROSSREF:
                result = await service.lookup_crossref_doi(doi)
                if result:
                    return SourceResult(
                        source=MetadataSource.CROSSREF,
                        success=True,
                        title=result.title,
                        authors=result.authors or [],
                        year=result.year,
                        doi=result.doi,
                        abstract=result.abstract,
                        journal=result.journal,
                        citation_count=result.citation_count,
                        confidence=1.0,  # DOI lookup is exact
                    )

            elif source == MetadataSource.OPENALEX:
                results = await service._search_openalex(doi, limit=1)
                if results:
                    r = results[0]
                    return SourceResult(
                        source=MetadataSource.OPENALEX,
                        success=True,
                        title=r.title,
                        authors=r.authors or [],
                        year=r.year,
                        doi=r.doi,
                        abstract=r.abstract,
                        journal=r.journal,
                        citation_count=r.citation_count,
                        pdf_url=r.pdf_url,
                        confidence=0.95,
                    )

            elif source == MetadataSource.SEMANTIC_SCHOLAR:
                results = await service._search_semantic_scholar_query(doi, limit=1)
                if results and results[0].doi and results[0].doi.lower() == doi.lower():
                    r = results[0]
                    return SourceResult(
                        source=MetadataSource.SEMANTIC_SCHOLAR,
                        success=True,
                        title=r.title,
                        authors=r.authors or [],
                        year=r.year,
                        doi=r.doi,
                        abstract=r.abstract,
                        journal=r.journal,
                        citation_count=r.citation_count,
                        pdf_url=r.pdf_url,
                        arxiv_id=r.arxiv_id,
                        confidence=0.95,
                    )

        except Exception as e:
            logger.warning(f"DOI lookup failed for {source}: {e}")
            return SourceResult(source=source, success=False, error=str(e))

        return SourceResult(source=source, success=False, error="No result")

    @classmethod
    async def _lookup_by_arxiv(cls, service, arxiv_id: str) -> SourceResult:
        """Look up paper by arXiv ID."""
        try:
            results = await service._search_arxiv(arxiv_id, limit=1)
            if results:
                r = results[0]
                # Verify this is the exact arXiv ID
                if r.arxiv_id and arxiv_id in r.arxiv_id:
                    return SourceResult(
                        source=MetadataSource.ARXIV,
                        success=True,
                        title=r.title,
                        authors=r.authors or [],
                        year=r.year,
                        doi=r.doi,
                        arxiv_id=r.arxiv_id,
                        abstract=r.abstract,
                        pdf_url=r.pdf_url,
                        confidence=1.0,  # Exact arXiv ID match
                    )
        except Exception as e:
            logger.warning(f"arXiv lookup failed: {e}")
            return SourceResult(source=MetadataSource.ARXIV, success=False, error=str(e))

        return SourceResult(source=MetadataSource.ARXIV, success=False, error="No result")

    @classmethod
    async def _lookup_arxiv_semantic_scholar(cls, service, arxiv_id: str) -> SourceResult:
        """Look up arXiv paper via Semantic Scholar."""
        try:
            # Semantic Scholar has arXiv papers indexed
            results = await service._search_semantic_scholar_query(f"arxiv:{arxiv_id}", limit=1)
            if results:
                r = results[0]
                return SourceResult(
                    source=MetadataSource.SEMANTIC_SCHOLAR,
                    success=True,
                    title=r.title,
                    authors=r.authors or [],
                    year=r.year,
                    doi=r.doi,
                    arxiv_id=r.arxiv_id,
                    abstract=r.abstract,
                    citation_count=r.citation_count,
                    pdf_url=r.pdf_url,
                    confidence=0.9,
                )
        except Exception as e:
            logger.warning(f"Semantic Scholar arXiv lookup failed: {e}")

        return SourceResult(source=MetadataSource.SEMANTIC_SCHOLAR, success=False)

    @classmethod
    async def _search_by_title(
        cls, service, title: str, authors: str | None, year: int | None, source: str
    ) -> SourceResult:
        """Search for paper by title with optional disambiguation."""
        try:
            # Build search query
            query = title
            if authors:
                query = f"{title} {authors}"

            results = []
            if source == MetadataSource.CROSSREF:
                results = await service._search_crossref(query, limit=5)
            elif source == MetadataSource.OPENALEX:
                results = await service._search_openalex(query, limit=5)
            elif source == MetadataSource.SEMANTIC_SCHOLAR:
                results = await service._search_semantic_scholar_query(query, limit=5)
            elif source == MetadataSource.ARXIV:
                results = await service._search_arxiv(query, limit=5)

            # Find best match
            if results:
                best_match = None
                best_confidence = 0.0

                for r in results:
                    confidence = cls._calculate_title_similarity(title, r.title)

                    # Boost confidence if year matches
                    if year and r.year == year:
                        confidence = min(1.0, confidence + 0.1)

                    # Boost confidence if authors match (partial)
                    if authors and r.authors:
                        author_match = any(
                            authors.lower() in a.lower() for a in r.authors
                        )
                        if author_match:
                            confidence = min(1.0, confidence + 0.1)

                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = r

                if best_match and best_confidence > 0.5:
                    return SourceResult(
                        source=source,
                        success=True,
                        title=best_match.title,
                        authors=best_match.authors or [],
                        year=best_match.year,
                        doi=best_match.doi,
                        arxiv_id=getattr(best_match, "arxiv_id", None),
                        abstract=best_match.abstract,
                        journal=best_match.journal,
                        citation_count=best_match.citation_count,
                        pdf_url=best_match.pdf_url,
                        confidence=best_confidence,
                    )

        except Exception as e:
            logger.warning(f"Title search failed for {source}: {e}")
            return SourceResult(source=source, success=False, error=str(e))

        return SourceResult(source=source, success=False, error="No matching result")

    @staticmethod
    def _calculate_title_similarity(title1: str, title2: str) -> float:
        """Calculate similarity between two titles."""
        # Normalize titles
        t1 = title1.lower().strip()
        t2 = title2.lower().strip()

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, t1, t2).ratio()

    @classmethod
    def _merge_results(cls, results: list[SourceResult]) -> MergedMetadata:
        """Merge results from multiple sources, preferring higher confidence."""
        # Sort by confidence
        results.sort(key=lambda r: r.confidence, reverse=True)
        primary = results[0]

        # Start with primary source
        merged = {
            "title": primary.title,
            "authors": primary.authors,
            "year": primary.year,
            "doi": primary.doi,
            "arxiv_id": primary.arxiv_id,
            "abstract": primary.abstract,
            "journal": primary.journal,
            "volume": primary.volume,
            "pages": primary.pages,
            "citation_count": primary.citation_count,
            "pdf_url": primary.pdf_url,
        }

        sources_used = [primary.source]

        # Fill in missing fields from other sources
        for result in results[1:]:
            filled_any = False
            if not merged["abstract"] and result.abstract:
                merged["abstract"] = result.abstract
                filled_any = True
            if not merged["doi"] and result.doi:
                merged["doi"] = result.doi
                filled_any = True
            if not merged["arxiv_id"] and result.arxiv_id:
                merged["arxiv_id"] = result.arxiv_id
                filled_any = True
            if not merged["citation_count"] and result.citation_count:
                merged["citation_count"] = result.citation_count
                filled_any = True
            if not merged["pdf_url"] and result.pdf_url:
                merged["pdf_url"] = result.pdf_url
                filled_any = True
            if not merged["journal"] and result.journal:
                merged["journal"] = result.journal
                filled_any = True
            if not merged["authors"] and result.authors:
                merged["authors"] = result.authors
                filled_any = True
            if not merged["year"] and result.year:
                merged["year"] = result.year
                filled_any = True
            if filled_any:
                sources_used.append(result.source)

        # Determine missing fields
        missing = []
        if not merged["abstract"]:
            missing.append("abstract")
        if not merged["year"]:
            missing.append("year")
        if not merged["journal"]:
            missing.append("journal")
        if not merged["authors"]:
            missing.append("authors")

        return MergedMetadata(
            title=merged["title"] or "",
            authors=merged["authors"] or [],
            year=merged["year"],
            doi=merged["doi"],
            arxiv_id=merged["arxiv_id"],
            abstract=merged["abstract"],
            journal=merged["journal"],
            volume=merged["volume"],
            pages=merged["pages"],
            citation_count=merged["citation_count"],
            pdf_url=merged["pdf_url"],
            primary_source=primary.source,
            confidence=primary.confidence,
            sources_used=sources_used,
            missing_fields=missing,
        )

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    @classmethod
    def _check_duplicates(
        cls,
        doi: str | None,
        arxiv_id: str | None,
        title: str,
    ) -> DuplicateCheck:
        """Check if paper already exists in database."""
        with get_session() as session:
            # Check DOI (exact match)
            if doi:
                existing = session.query(Paper).filter(Paper.doi == doi).first()
                if existing:
                    return DuplicateCheck(
                        is_duplicate=True,
                        match_type="doi",
                        existing_paper_id=existing.id,
                        existing_paper_title=existing.title,
                    )

            # Check arXiv ID (exact match)
            if arxiv_id:
                existing = session.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
                if existing:
                    return DuplicateCheck(
                        is_duplicate=True,
                        match_type="arxiv_id",
                        existing_paper_id=existing.id,
                        existing_paper_title=existing.title,
                    )

            # Check title similarity (fuzzy match)
            # Only check recent papers to avoid O(n) on full database
            recent_papers = (
                session.query(Paper)
                .filter(Paper.title.isnot(None))
                .order_by(Paper.date_added.desc())
                .limit(1000)
                .all()
            )

            normalized_title = title.lower().strip()
            for paper in recent_papers:
                paper_title = (paper.title or "").lower().strip()
                similarity = SequenceMatcher(None, normalized_title, paper_title).ratio()
                if similarity > cls.TITLE_SIMILARITY_THRESHOLD:
                    return DuplicateCheck(
                        is_duplicate=True,
                        match_type="title_similarity",
                        existing_paper_id=paper.id,
                        existing_paper_title=paper.title,
                        similarity=round(similarity, 3),
                    )

        return DuplicateCheck(is_duplicate=False)

    # =========================================================================
    # Enrichment Status
    # =========================================================================

    @classmethod
    def _determine_enrichment_status(
        cls,
        merged: MergedMetadata,
        has_pdf: bool,
    ) -> str:
        """Determine what enrichment is still needed."""
        # If no PDF, we need to acquire it first (abstract may come from PDF extraction)
        if not has_pdf:
            return EnrichmentStatus.NEEDS_PDF
        # If we have PDF, we need AI extraction
        return EnrichmentStatus.NEEDS_EXTRACTION

    @classmethod
    def _update_enrichment_status(cls, paper_id: int, status: str) -> None:
        """Update enrichment status for a paper."""
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if paper:
                paper.enrichment_status = status
                session.commit()

    # =========================================================================
    # Paper Creation
    # =========================================================================

    @classmethod
    def _create_paper(
        cls,
        merged: MergedMetadata,
        tags: list[str] | None,
        collection_id: int | None,
        pdf_path: str | None,
        enrichment_status: str,
    ) -> dict:
        """Create paper in database with all metadata."""
        with get_session() as session:
            paper = Paper(
                title=merged.title,
                abstract=merged.abstract,
                year=merged.year,
                doi=merged.doi,
                arxiv_id=merged.arxiv_id,
                journal=merged.journal,
                volume=merged.volume,
                pages=merged.pages,
                citation_count=merged.citation_count,
                file_path=pdf_path,
                # Provenance fields
                metadata_source=merged.primary_source,
                metadata_confidence=merged.confidence,
                enrichment_status=enrichment_status,
                import_method=ImportMethod.WIZARD,
                import_date=datetime.utcnow(),
            )
            session.add(paper)
            session.flush()

            # Add authors with position
            for i, author_name in enumerate(merged.authors):
                if not author_name or not author_name.strip():
                    continue
                author = (
                    session.query(Author).filter(Author.name == author_name).first()
                )
                if not author:
                    author = Author(name=author_name)
                    session.add(author)
                    session.flush()
                # Add to association with position
                session.execute(
                    Paper.__table__.metadata.tables["paper_authors"].insert().values(
                        paper_id=paper.id, author_id=author.id, position=i
                    )
                )

            # Add tags
            for tag_name in tags or []:
                if not tag_name or not tag_name.strip():
                    continue
                tag = session.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)
                paper.tags.append(tag)

            # Add to collection
            if collection_id:
                collection = (
                    session.query(Collection)
                    .filter(Collection.id == collection_id)
                    .first()
                )
                if collection:
                    collection.papers.append(paper)
                else:
                    logger.warning(f"Collection {collection_id} not found, skipping")

            session.commit()

            logger.info(
                f"Imported paper {paper.id}: {paper.title[:50]}... "
                f"(source: {merged.primary_source}, confidence: {merged.confidence:.2f})"
            )

            return {
                "id": paper.id,
                "title": paper.title,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "year": paper.year,
                "abstract": paper.abstract[:200] + "..." if paper.abstract and len(paper.abstract) > 200 else paper.abstract,
                "authors": [a.name for a in paper.authors],
                "metadata_source": paper.metadata_source,
                "metadata_confidence": paper.metadata_confidence,
                "enrichment_status": paper.enrichment_status,
            }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @classmethod
    def get_enrichment_queue(
        cls,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get papers needing enrichment.

        Args:
            status: Filter by specific enrichment status
            limit: Maximum papers to return

        Returns:
            List of paper dicts needing enrichment
        """
        with get_session() as session:
            query = session.query(Paper)

            if status:
                query = query.filter(Paper.enrichment_status == status)
            else:
                # Exclude complete papers
                query = query.filter(Paper.enrichment_status != EnrichmentStatus.COMPLETE)

            papers = query.order_by(Paper.date_added.desc()).limit(limit).all()

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "doi": p.doi,
                    "enrichment_status": p.enrichment_status,
                    "has_abstract": p.abstract is not None,
                    "has_pdf": p.file_path is not None,
                }
                for p in papers
            ]
