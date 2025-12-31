"""Validation Service for verifying papers exist in external databases.

Provides tools to verify paper metadata against CrossRef, Semantic Scholar,
and other academic databases. Tracks validation status per paper.

Architecture:
    ValidationService -> ExternalSearchService -> External APIs
                      -> PaperService -> Database
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from literature_core import get_session, get_logger, Paper
from services.external_search import ExternalSearchService

logger = get_logger(__name__)


@dataclass
class ValidationStatus:
    """Status report for paper validation coverage."""
    total_papers: int = 0
    validated_papers: int = 0
    verified_papers: int = 0
    not_found_papers: int = 0
    error_papers: int = 0
    unvalidated_papers: int = 0

    # Papers with identifiers that can be validated
    papers_with_doi: int = 0
    papers_with_arxiv: int = 0
    papers_with_title_only: int = 0

    @property
    def validation_coverage_percent(self) -> float:
        """Percentage of papers that have been validated (any status)."""
        if self.total_papers == 0:
            return 100.0
        return (self.validated_papers / self.total_papers) * 100

    @property
    def verification_rate_percent(self) -> float:
        """Percentage of validated papers that were verified."""
        if self.validated_papers == 0:
            return 0.0
        return (self.verified_papers / self.validated_papers) * 100


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    papers_processed: int = 0
    papers_verified: int = 0
    papers_not_found: int = 0
    papers_error: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if at least some papers were processed without total failure."""
        return self.papers_processed > 0 or len(self.errors) == 0


@dataclass
class PaperValidation:
    """Validation result for a single paper."""
    paper_id: int
    status: str  # verified, not_found, error
    source: Optional[str] = None  # crossref, semantic_scholar, etc.
    confidence: float = 0.0
    matched_doi: Optional[str] = None
    matched_title: Optional[str] = None
    message: Optional[str] = None


class ValidationService:
    """Service for validating papers against external databases."""

    # Minimum confidence threshold for verification
    MIN_CONFIDENCE = 0.85

    @classmethod
    def get_validation_status(cls, include_ids: bool = False) -> ValidationStatus:
        """Get validation coverage statistics.

        Args:
            include_ids: If True, include lists of paper IDs (not implemented yet)

        Returns:
            ValidationStatus with coverage statistics
        """
        with get_session() as session:
            status = ValidationStatus()

            # Total papers
            status.total_papers = session.query(Paper).count()

            # By validation status
            status.verified_papers = session.query(Paper).filter(
                Paper.validation_status == 'verified'
            ).count()

            status.not_found_papers = session.query(Paper).filter(
                Paper.validation_status == 'not_found'
            ).count()

            status.error_papers = session.query(Paper).filter(
                Paper.validation_status == 'error'
            ).count()

            status.unvalidated_papers = session.query(Paper).filter(
                Paper.validation_status == 'unvalidated'
            ).count()

            status.validated_papers = (
                status.verified_papers +
                status.not_found_papers +
                status.error_papers
            )

            # Papers with identifiers
            status.papers_with_doi = session.query(Paper).filter(
                Paper.doi.isnot(None),
                Paper.doi != ''
            ).count()

            status.papers_with_arxiv = session.query(Paper).filter(
                Paper.arxiv_id.isnot(None),
                Paper.arxiv_id != ''
            ).count()

            # Papers with only title (no DOI or arXiv)
            status.papers_with_title_only = session.query(Paper).filter(
                (Paper.doi.is_(None) | (Paper.doi == '')),
                (Paper.arxiv_id.is_(None) | (Paper.arxiv_id == ''))
            ).count()

            return status

    @classmethod
    def get_papers_needing_validation(
        cls,
        limit: int = 50,
        prioritize_with_doi: bool = True
    ) -> list[dict]:
        """Get papers that need validation.

        Args:
            limit: Maximum papers to return
            prioritize_with_doi: If True, papers with DOI come first (easier to validate)

        Returns:
            List of paper dicts with id, title, doi, arxiv_id
        """
        with get_session() as session:
            query = session.query(Paper).filter(
                Paper.validation_status == 'unvalidated'
            )

            if prioritize_with_doi:
                # Order by: has DOI first, then has arXiv, then others
                query = query.order_by(
                    Paper.doi.is_(None).asc(),  # DOI not null first
                    Paper.arxiv_id.is_(None).asc(),  # Then arXiv
                    Paper.date_added.desc()  # Then newest
                )
            else:
                query = query.order_by(Paper.date_added.desc())

            papers = query.limit(limit).all()

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "doi": p.doi,
                    "arxiv_id": p.arxiv_id,
                    "year": p.year,
                    "authors": [a.name for a in p.authors[:3]],  # First 3 authors
                }
                for p in papers
            ]

    @classmethod
    async def validate_paper(cls, paper_id: int) -> PaperValidation:
        """Validate a single paper against external databases.

        Tries in order:
        1. DOI lookup (most reliable)
        2. arXiv lookup
        3. Title + author search

        Args:
            paper_id: Paper ID to validate

        Returns:
            PaperValidation with result
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return PaperValidation(
                    paper_id=paper_id,
                    status="error",
                    message="Paper not found in database"
                )

            service = ExternalSearchService()
            validation = PaperValidation(paper_id=paper_id, status="not_found")

            try:
                # Strategy 1: DOI lookup (most reliable)
                if paper.doi:
                    result = await service.lookup_by_doi(paper.doi)
                    if result and result.confidence >= cls.MIN_CONFIDENCE:
                        validation = PaperValidation(
                            paper_id=paper_id,
                            status="verified",
                            source=result.source,
                            confidence=result.confidence,
                            matched_doi=result.doi,
                            matched_title=result.title
                        )
                        cls._update_paper_validation(session, paper, validation)
                        return validation

                # Strategy 2: Title + author search
                first_author = paper.authors[0].name if paper.authors else None
                result = await service.find_doi_by_title(
                    title=paper.title,
                    author=first_author,
                    year=paper.year
                )

                if result and result.confidence >= cls.MIN_CONFIDENCE:
                    validation = PaperValidation(
                        paper_id=paper_id,
                        status="verified",
                        source=result.source,
                        confidence=result.confidence,
                        matched_doi=result.doi,
                        matched_title=result.title
                    )

                    # Update paper DOI if we found it and paper didn't have one
                    if result.doi and not paper.doi:
                        paper.doi = result.doi
                        logger.info(f"Paper {paper_id}: Added DOI {result.doi}")

                elif result:
                    # Low confidence match
                    validation = PaperValidation(
                        paper_id=paper_id,
                        status="not_found",
                        source=result.source,
                        confidence=result.confidence,
                        matched_title=result.title,
                        message=f"Low confidence match ({result.confidence:.2f})"
                    )
                else:
                    validation = PaperValidation(
                        paper_id=paper_id,
                        status="not_found",
                        message="No match found in external databases"
                    )

                cls._update_paper_validation(session, paper, validation)

            except Exception as e:
                logger.error(f"Validation error for paper {paper_id}: {e}")
                validation = PaperValidation(
                    paper_id=paper_id,
                    status="error",
                    message=str(e)
                )
                cls._update_paper_validation(session, paper, validation)

            return validation

    @classmethod
    def _update_paper_validation(
        cls,
        session,
        paper: Paper,
        validation: PaperValidation
    ) -> None:
        """Update paper's validation fields in database."""
        paper.validation_status = validation.status
        paper.validation_source = validation.source
        paper.validation_date = datetime.utcnow()
        paper.validation_confidence = validation.confidence
        session.commit()

    @classmethod
    async def validate_batch(
        cls,
        paper_ids: list[int] | None = None,
        limit: int = 20
    ) -> ValidationResult:
        """Validate multiple papers.

        Args:
            paper_ids: Specific papers to validate, or None to get from queue
            limit: Maximum papers to process if using queue

        Returns:
            ValidationResult with statistics
        """
        result = ValidationResult()

        # Get papers to validate
        if paper_ids:
            papers = [{"id": pid} for pid in paper_ids]
        else:
            papers = cls.get_papers_needing_validation(limit=limit)

        for paper_info in papers:
            try:
                validation = await cls.validate_paper(paper_info["id"])
                result.papers_processed += 1

                if validation.status == "verified":
                    result.papers_verified += 1
                elif validation.status == "not_found":
                    result.papers_not_found += 1
                elif validation.status == "error":
                    result.papers_error += 1
                    if validation.message:
                        result.errors.append(
                            f"Paper {paper_info['id']}: {validation.message}"
                        )

            except Exception as e:
                result.papers_error += 1
                result.errors.append(f"Paper {paper_info['id']}: {str(e)}")
                logger.error(f"Batch validation error for paper {paper_info['id']}: {e}")

        logger.info(
            f"Batch validation complete: {result.papers_verified} verified, "
            f"{result.papers_not_found} not found, {result.papers_error} errors"
        )

        return result

    @classmethod
    def reset_validation(cls, paper_ids: list[int] | None = None) -> int:
        """Reset validation status for papers (for re-validation).

        Args:
            paper_ids: Specific papers to reset, or None for all

        Returns:
            Number of papers reset
        """
        with get_session() as session:
            query = session.query(Paper)

            if paper_ids:
                query = query.filter(Paper.id.in_(paper_ids))

            count = query.update(
                {
                    Paper.validation_status: 'unvalidated',
                    Paper.validation_source: None,
                    Paper.validation_date: None,
                    Paper.validation_confidence: None
                },
                synchronize_session=False
            )
            session.commit()

            logger.info(f"Reset validation for {count} papers")
            return count
