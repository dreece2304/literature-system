"""Paper Service - Business logic for paper operations.

This service provides all paper-related operations including CRUD, search,
and batch operations. It uses direct SQLAlchemy database access.

Usage:
    from services import PaperService

    # Get a paper (raises PaperNotFoundError if not found)
    paper = PaperService.get(123)

    # List papers with filters
    papers, total = PaperService.list(author="Smith", limit=20)

    # Add a new paper
    paper = PaperService.create(title="My Paper", authors=["John Doe"])

    # Update a paper
    paper = PaperService.update(123, title="New Title")

    # Search papers
    results = PaperService.search("machine learning", limit=10)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Author,
    Tag,
    PaperContent,
    PaperNotFoundError,
    ValidationError,
    ReadStatus,
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    MIN_RATING,
    MAX_RATING,
)

logger = get_logger(__name__)


@dataclass
class PaperListResult:
    """Result of a paper list operation."""
    papers: list[dict]
    total: int
    limit: int
    offset: int


@dataclass
class BatchResult:
    """Result of a batch operation."""
    processed: list[int]
    failed: list[dict]


class PaperService:
    """Service for paper-related operations."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _get_or_create_author(session, name: str) -> Author:
        """Get existing author or create new one."""
        author = session.query(Author).filter(Author.name == name).first()
        if not author:
            author = Author(name=name)
            session.add(author)
            session.flush()
        return author

    @staticmethod
    def _get_or_create_tag(session, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = session.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        return tag

    @staticmethod
    def paper_to_dict(paper: Paper, include_content: bool = False) -> dict:
        """Convert Paper model to dictionary.

        Args:
            paper: Paper ORM instance
            include_content: Whether to include full_text

        Returns:
            Dictionary representation of the paper
        """
        result = {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "year": paper.year,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "pubmed_id": paper.pubmed_id,
            "journal": paper.journal,
            "volume": paper.volume,
            "issue": paper.issue,
            "pages": paper.pages,
            "publisher": paper.publisher,
            "citation_key": paper.citation_key,
            "citation_count": paper.citation_count,
            "file_path": paper.file_path,
            "date_added": paper.date_added.isoformat() if paper.date_added else None,
            "date_modified": paper.date_modified.isoformat() if paper.date_modified else None,
            "date_read": paper.date_read.isoformat() if paper.date_read else None,
            "rating": paper.rating,
            "read_status": paper.read_status,
            "word_count": paper.word_count,
            "authors": [{"id": a.id, "name": a.name} for a in paper.authors],
            "tags": [{"id": t.id, "name": t.name} for t in paper.tags],
            "zotero_key": paper.zotero_key,
        }
        if include_content and paper.full_text:
            result["full_text"] = paper.full_text
        return result

    @staticmethod
    def paper_to_summary(paper: Paper) -> dict:
        """Convert Paper to a summary dictionary (for list operations).

        Args:
            paper: Paper ORM instance

        Returns:
            Summary dictionary with key fields only
        """
        return {
            "id": paper.id,
            "title": paper.title,
            "year": paper.year,
            "authors": [a.name for a in paper.authors],
            "read_status": paper.read_status,
            "rating": paper.rating,
        }

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    @classmethod
    def get(cls, paper_id: int) -> dict:
        """Get a paper by ID.

        Args:
            paper_id: The paper's database ID

        Returns:
            Dictionary representation of the paper

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)
            return cls.paper_to_dict(paper)

    @classmethod
    def list(
        cls,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
        author: str | None = None,
        year: int | None = None,
        tag: str | None = None,
        read_status: str | None = None,
    ) -> PaperListResult:
        """List papers with optional filtering and pagination.

        Args:
            limit: Maximum papers to return (max: 500)
            offset: Number of papers to skip
            author: Filter by author name (partial match)
            year: Filter by publication year
            tag: Filter by tag name
            read_status: Filter by read status (unread, reading, read)

        Returns:
            PaperListResult with papers and pagination info
        """
        limit = min(limit, MAX_SEARCH_LIMIT)

        # Validate read_status if provided
        if read_status and not ReadStatus.is_valid(read_status):
            raise ValidationError("read_status", f"Must be one of: {ReadStatus.ALL}")

        with get_session() as session:
            query = session.query(Paper)

            # Apply filters
            if author:
                query = query.join(Paper.authors).filter(
                    Author.name.ilike(f"%{author}%")
                )
            if year:
                query = query.filter(Paper.year == year)
            if tag:
                query = query.join(Paper.tags).filter(Tag.name == tag)
            if read_status:
                query = query.filter(Paper.read_status == read_status)

            # Get total count before pagination
            total = query.count()

            # Apply pagination
            papers = (
                query.order_by(Paper.date_added.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            return PaperListResult(
                papers=[cls.paper_to_summary(p) for p in papers],
                total=total,
                limit=limit,
                offset=offset,
            )

    @classmethod
    def create(
        cls,
        title: str,
        abstract: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        arxiv_id: str | None = None,
        journal: str | None = None,
        authors: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Create a new paper.

        Args:
            title: Paper title (required)
            abstract: Paper abstract
            year: Publication year
            doi: Digital Object Identifier
            arxiv_id: arXiv identifier
            journal: Journal name
            authors: List of author names
            tags: List of tag names

        Returns:
            Dictionary representation of the created paper
        """
        if not title:
            raise ValidationError("title", "Title is required")

        with get_session() as session:
            paper = Paper(
                title=title,
                abstract=abstract,
                year=year,
                doi=doi,
                arxiv_id=arxiv_id,
                journal=journal,
            )

            # Handle authors
            for name in (authors or []):
                author = cls._get_or_create_author(session, name)
                paper.authors.append(author)

            # Handle tags
            for name in (tags or []):
                tag = cls._get_or_create_tag(session, name)
                paper.tags.append(tag)

            session.add(paper)
            session.flush()

            logger.info(f"Created paper {paper.id}: {title}")
            return cls.paper_to_dict(paper)

    @classmethod
    def update(
        cls,
        paper_id: int,
        title: str | None = None,
        abstract: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        rating: int | None = None,
        read_status: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Update an existing paper.

        Args:
            paper_id: Paper ID to update
            title: New title
            abstract: New abstract
            year: New year
            doi: New DOI
            rating: New rating (1-5)
            read_status: New read status
            tags: Replace tags with this list

        Returns:
            Updated paper dictionary

        Raises:
            PaperNotFoundError: If paper doesn't exist
            ValidationError: If validation fails
        """
        # Validate rating if provided
        if rating is not None and not (MIN_RATING <= rating <= MAX_RATING):
            raise ValidationError("rating", f"Must be between {MIN_RATING} and {MAX_RATING}")

        # Validate read_status if provided
        if read_status and not ReadStatus.is_valid(read_status):
            raise ValidationError("read_status", f"Must be one of: {ReadStatus.ALL}")

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            # Update simple fields
            if title is not None:
                paper.title = title
            if abstract is not None:
                paper.abstract = abstract
            if year is not None:
                paper.year = year
            if doi is not None:
                paper.doi = doi
            if rating is not None:
                paper.rating = rating
            if read_status is not None:
                paper.read_status = read_status

            # Handle tags if provided (replace all)
            if tags is not None:
                paper.tags.clear()
                for tag_name in tags:
                    tag = cls._get_or_create_tag(session, tag_name)
                    paper.tags.append(tag)

            paper.date_modified = datetime.utcnow()
            logger.info(f"Updated paper {paper_id}")
            return cls.paper_to_dict(paper)

    @classmethod
    def delete(cls, paper_id: int) -> None:
        """Delete a paper.

        Args:
            paper_id: Paper ID to delete

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)
            session.delete(paper)
            logger.info(f"Deleted paper {paper_id}")

    # =========================================================================
    # Search Operations
    # =========================================================================

    @classmethod
    def search(cls, query: str, limit: int = 10) -> list[dict]:
        """Search papers by title, abstract, or full text.

        Args:
            query: Search query string
            limit: Maximum results to return

        Returns:
            List of matching papers (summary format)
        """
        with get_session() as session:
            search_pattern = f"%{query}%"
            papers = (
                session.query(Paper)
                .filter(
                    (Paper.title.ilike(search_pattern))
                    | (Paper.abstract.ilike(search_pattern))
                    | (Paper.full_text.ilike(search_pattern))
                )
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "authors": [a.name for a in p.authors],
                    "abstract": (
                        (p.abstract[:200] + "...")
                        if p.abstract and len(p.abstract) > 200
                        else p.abstract
                    ),
                }
                for p in papers
            ]

    # =========================================================================
    # Content Operations
    # =========================================================================

    @classmethod
    def get_content(cls, paper_id: int) -> dict:
        """Get full paper content for AI analysis.

        Args:
            paper_id: Paper ID

        Returns:
            Dictionary with title, abstract, full_text, and extraction data

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            result = {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "full_text": paper.full_text,
                "word_count": paper.word_count,
                "authors": [a.name for a in paper.authors],
            }

            # Include extracted content if available
            if paper.content:
                result["extraction"] = {
                    "paper_type": paper.content.paper_type,
                    "topics": paper.content.topics,
                    "one_sentence_summary": paper.content.one_sentence_summary,
                    "key_findings": paper.content.key_findings,
                    "methodology_summary": paper.content.methodology_summary,
                }

            return result

    @classmethod
    def store_extraction(
        cls,
        paper_id: int,
        paper_type: str | None = None,
        topics: list[str] | None = None,
        one_sentence_summary: str | None = None,
        key_findings: list[str] | None = None,
        methodology_summary: str | None = None,
    ) -> None:
        """Store AI-extracted content for a paper.

        Args:
            paper_id: Paper ID
            paper_type: Type of paper (research_article, review, etc.)
            topics: List of identified topics/themes
            one_sentence_summary: One sentence summary
            key_findings: List of key findings
            methodology_summary: Summary of methodology

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            content = (
                session.query(PaperContent)
                .filter(PaperContent.paper_id == paper_id)
                .first()
            )

            if content:
                # Update existing
                if paper_type is not None:
                    content.paper_type = paper_type
                if topics is not None:
                    content.topics = topics
                if one_sentence_summary is not None:
                    content.one_sentence_summary = one_sentence_summary
                if key_findings is not None:
                    content.key_findings = key_findings
                if methodology_summary is not None:
                    content.methodology_summary = methodology_summary
                content.extraction_depth = "COMPREHENSIVE"
                content.extractor_model = "claude-code"
            else:
                # Create new
                content = PaperContent(
                    paper_id=paper_id,
                    paper_type=paper_type,
                    topics=topics,
                    one_sentence_summary=one_sentence_summary,
                    key_findings=key_findings,
                    methodology_summary=methodology_summary,
                    extraction_depth="COMPREHENSIVE",
                    extractor_model="claude-code",
                )
                session.add(content)

            logger.info(f"Stored extraction for paper {paper_id}")

    @classmethod
    def get_extraction_queue(cls, limit: int = 20) -> list[dict]:
        """Get papers that need AI extraction.

        Args:
            limit: Maximum papers to return

        Returns:
            List of papers needing extraction
        """
        with get_session() as session:
            papers_with_content = session.query(PaperContent.paper_id).scalar_subquery()
            papers = (
                session.query(Paper)
                .filter(~Paper.id.in_(papers_with_content))
                .filter(Paper.abstract.isnot(None) | Paper.full_text.isnot(None))
                .order_by(Paper.date_added.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "has_abstract": p.abstract is not None,
                    "has_full_text": p.full_text is not None,
                }
                for p in papers
            ]

    # =========================================================================
    # Batch Operations
    # =========================================================================

    @classmethod
    def batch_update(
        cls,
        paper_ids: list[int],
        tags_to_add: list[str] | None = None,
        tags_to_remove: list[str] | None = None,
        read_status: str | None = None,
        rating: int | None = None,
    ) -> BatchResult:
        """Bulk update multiple papers.

        Args:
            paper_ids: List of paper IDs to update
            tags_to_add: Tags to add to all papers
            tags_to_remove: Tags to remove from all papers
            read_status: Set read status for all papers
            rating: Set rating for all papers

        Returns:
            BatchResult with processed and failed lists
        """
        # Validate inputs
        if rating is not None and not (MIN_RATING <= rating <= MAX_RATING):
            raise ValidationError("rating", f"Must be between {MIN_RATING} and {MAX_RATING}")
        if read_status and not ReadStatus.is_valid(read_status):
            raise ValidationError("read_status", f"Must be one of: {ReadStatus.ALL}")

        processed = []
        failed = []

        with get_session() as session:
            # Pre-fetch tags to add
            add_tag_objs = [
                cls._get_or_create_tag(session, name)
                for name in (tags_to_add or [])
            ]

            for paper_id in paper_ids:
                try:
                    paper = session.query(Paper).filter(Paper.id == paper_id).first()
                    if not paper:
                        failed.append({"id": paper_id, "error": "Paper not found"})
                        continue

                    # Apply tag changes
                    if tags_to_remove:
                        paper.tags = [
                            t for t in paper.tags if t.name not in tags_to_remove
                        ]
                    for tag in add_tag_objs:
                        if tag not in paper.tags:
                            paper.tags.append(tag)

                    # Apply other updates
                    if read_status:
                        paper.read_status = read_status
                    if rating:
                        paper.rating = rating

                    paper.date_modified = datetime.utcnow()
                    processed.append(paper_id)

                except Exception as e:
                    failed.append({"id": paper_id, "error": str(e)})

        logger.info(f"Batch updated {len(processed)} papers, {len(failed)} failed")
        return BatchResult(processed=processed, failed=failed)

    @classmethod
    def batch_delete(cls, paper_ids: list[int]) -> BatchResult:
        """Bulk delete multiple papers.

        Args:
            paper_ids: List of paper IDs to delete

        Returns:
            BatchResult with deleted and failed lists
        """
        processed = []
        failed = []

        with get_session() as session:
            for paper_id in paper_ids:
                try:
                    paper = session.query(Paper).filter(Paper.id == paper_id).first()
                    if paper:
                        session.delete(paper)
                        processed.append(paper_id)
                    else:
                        failed.append({"id": paper_id, "error": "Paper not found"})
                except Exception as e:
                    failed.append({"id": paper_id, "error": str(e)})

        logger.info(f"Batch deleted {len(processed)} papers, {len(failed)} failed")
        return BatchResult(processed=processed, failed=failed)
