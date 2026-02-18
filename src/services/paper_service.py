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

from sqlalchemy.orm import joinedload

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Author,
    Tag,
    PaperContent,
    PaperChunk,
    PaperNotFoundError,
    ValidationError,
    ReadStatus,
    EnrichmentStatus,
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
            "file_hash": paper.file_hash,
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
        if include_content:
            # Get full text from chunks (Paper.full_text column is deprecated)
            full_text = PaperService.get_full_text(paper.id)
            if full_text:
                result["full_text"] = full_text
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
            # Use joinedload to prevent N+1 queries on authors/tags
            query = session.query(Paper).options(
                joinedload(Paper.authors),
                joinedload(Paper.tags),
            )

            # Apply filters
            if author:
                query = query.join(Paper.authors, isouter=True).filter(
                    Author.name.ilike(f"%{author}%")
                )
            if year:
                query = query.filter(Paper.year == year)
            if tag:
                query = query.join(Paper.tags, isouter=True).filter(Tag.name == tag)
            if read_status:
                query = query.filter(Paper.read_status == read_status)

            # Get total count before pagination (use subquery for accuracy with joins)
            total = query.with_entities(Paper.id).distinct().count()

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
        file_path: str | None = None,
        file_hash: str | None = None,
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
            file_path: Path to local PDF file
            file_hash: SHA256 hash of PDF for duplicate detection

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

        # Track if PDF was added/changed for auto-chunking
        pdf_changed = False
        # Track if embedding-relevant fields changed
        needs_reembed = False

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            # Update simple fields - track changes for re-embedding
            if title is not None and title != paper.title:
                paper.title = title
                needs_reembed = True
            if abstract is not None and abstract != paper.abstract:
                paper.abstract = abstract
                needs_reembed = True
            if year is not None:
                paper.year = year
            if doi is not None:
                paper.doi = doi
            if rating is not None:
                paper.rating = rating
            if read_status is not None:
                paper.read_status = read_status

            # Update PDF-related fields
            if file_path is not None:
                # Track if file_path actually changed
                if paper.file_path != file_path:
                    pdf_changed = True
                    # Update enrichment status to needs_chunking (has PDF, needs text extraction)
                    paper.enrichment_status = EnrichmentStatus.NEEDS_CHUNKING
                paper.file_path = file_path
            if file_hash is not None:
                paper.file_hash = file_hash

            # Handle tags if provided (replace all)
            if tags is not None:
                paper.tags.clear()
                for tag_name in tags:
                    tag = cls._get_or_create_tag(session, tag_name)
                    paper.tags.append(tag)

            paper.date_modified = datetime.utcnow()
            logger.info(f"Updated paper {paper_id}")
            result = cls.paper_to_dict(paper)

        # Auto-queue chunking if PDF was added/changed
        if pdf_changed:
            try:
                from .extraction_service import ExtractionService
                ExtractionService.queue_extraction(paper_id)
                logger.info(f"Queued paper {paper_id} for extraction after PDF update")
            except Exception as e:
                # Don't fail the update if queuing fails
                logger.warning(f"Failed to queue extraction for paper {paper_id}: {e}")

        # Re-embed if title/abstract changed (after commit)
        if needs_reembed:
            try:
                from .embedding_service import EmbeddingService
                EmbeddingService.reembed_paper_sync(paper_id)
            except Exception as e:
                # Don't fail the update if re-embedding fails
                logger.warning(f"Failed to re-embed paper {paper_id}: {e}")

        return result

    @classmethod
    def delete(cls, paper_id: int) -> None:
        """Delete a paper and clean up embeddings.

        Args:
            paper_id: Paper ID to delete

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            # Delete from ChromaDB FIRST (before SQLite cascade)
            try:
                from embeddings.vectorstore import get_vector_store, get_chunk_store
                get_vector_store().delete([str(paper_id)])
                get_chunk_store().delete_paper_chunks(paper_id)
            except Exception as e:
                logger.warning(f"Failed to delete embeddings for paper {paper_id}: {e}")

            # Then delete from SQLite (cascades to chunks, notes, etc.)
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
                    # Note: Full-text search on chunks uses FTS5, not LIKE queries
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
    def get_full_text(cls, paper_id: int, session=None) -> str | None:
        """Reconstruct full text from chunks (for backward compatibility).

        This is the preferred way to get full text content. It reads from
        PaperChunk records which replace the deprecated Paper.full_text field.

        Args:
            paper_id: Paper ID
            session: Optional existing session

        Returns:
            Concatenated text from all chunks, or None if no chunks exist
        """
        def _get(sess):
            chunks = (
                sess.query(PaperChunk)
                .filter(PaperChunk.paper_id == paper_id)
                .order_by(PaperChunk.chunk_order)
                .all()
            )
            if not chunks:
                return None
            return "\n\n".join(c.content for c in chunks)

        if session:
            return _get(session)
        else:
            with get_session() as sess:
                return _get(sess)

    @classmethod
    def get_content(cls, paper_id: int, include_full_text: bool = False) -> dict:
        """Get paper content for AI analysis.

        Args:
            paper_id: Paper ID
            include_full_text: If True, include full text from chunks (default False
                             for token efficiency - extraction summary is usually enough)

        Returns:
            Dictionary with title, abstract, extraction data, and optionally full_text

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
                "word_count": paper.word_count,
                "authors": [a.name for a in paper.authors],
            }

            # Only include full text if explicitly requested
            if include_full_text:
                result["full_text"] = cls.get_full_text(paper_id, session)

            # Include extracted content if available
            if paper.content:
                result["extraction"] = {
                    "paper_type": paper.content.paper_type,
                    "topics": paper.content.topics,
                    "one_sentence_summary": paper.content.one_sentence_summary,
                    "key_findings": paper.content.key_findings,
                    "methodology_summary": paper.content.methodology_summary,
                }
                # Include structured_data with new extraction fields
                if paper.content.structured_data:
                    result["extraction"].update(paper.content.structured_data)

                # Determine extraction tier based on populated fields
                has_deep_fields = (
                    paper.content.key_findings
                    or paper.content.methodology_summary
                    or (paper.content.structured_data and any(
                        paper.content.structured_data.get(f)
                        for f in ["quantitative_results", "citable_claims", "techniques_used"]
                    ))
                )
                result["extraction_tier"] = "deep" if has_deep_fields else "quick"

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
        structured_data: dict | None = None,
        extractor_model: str | None = None,
        is_quick: bool = True,
    ) -> None:
        """Store AI-extracted content for a paper and update status.

        Schema v2.1: Quick and deep extractions stored separately.
        - Quick: paper_type, topics, one_sentence_summary
        - Deep: deep_paper_type, deep_topics, deep_one_sentence_summary + extended

        After storing, sets enrichment_status to COMPLETE (for both quick and deep).
        Papers can be flagged for deep extraction via NEEDS_DEEP_EXTRACTION status.

        Args:
            paper_id: Paper ID
            paper_type: Type of paper (research_article, review, etc.)
            topics: List of identified topics/themes
            one_sentence_summary: One sentence summary
            key_findings: List of key findings (deep only)
            methodology_summary: Summary of methodology (deep only)
            structured_data: Extended fields (deep only)
            extractor_model: Model used for extraction
            is_quick: If True, quick (abstract-only) extraction (default for Claude)

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        from datetime import datetime
        model_name = extractor_model or "claude-code"
        now = datetime.utcnow()

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            content = (
                session.query(PaperContent)
                .filter(PaperContent.paper_id == paper_id)
                .first()
            )

            if not content:
                content = PaperContent(paper_id=paper_id, schema_version="2.1")
                session.add(content)

            if is_quick:
                # Quick extraction: store to quick fields only
                if paper_type is not None:
                    content.paper_type = paper_type
                if topics is not None:
                    content.topics = topics
                if one_sentence_summary is not None:
                    content.one_sentence_summary = one_sentence_summary
                content.extractor_model = model_name
                content.quick_extraction_date = now
                content.extraction_depth = "abstract_only"
            else:
                # Deep extraction: store to deep_* fields
                if paper_type is not None:
                    content.deep_paper_type = paper_type
                if topics is not None:
                    content.deep_topics = topics
                if one_sentence_summary is not None:
                    content.deep_one_sentence_summary = one_sentence_summary
                if key_findings is not None:
                    content.key_findings = key_findings
                if methodology_summary is not None:
                    content.methodology_summary = methodology_summary
                if structured_data is not None:
                    content.structured_data = structured_data
                content.deep_extractor_model = model_name
                content.deep_extraction_date = now
                content.extraction_depth = "comprehensive"

                # Generate verification if quick extraction exists
                if content.paper_type and paper_type:
                    quick_topics = set(content.topics or [])
                    deep_topics = set(topics or [])
                    overlap = len(quick_topics & deep_topics) / max(len(quick_topics | deep_topics), 1)

                    content.verification = {
                        "paper_type_matches": content.paper_type == paper_type,
                        "topics_overlap": round(overlap, 2),
                        "quick_topics_count": len(quick_topics),
                        "deep_topics_count": len(deep_topics),
                        "verified_at": now.isoformat(),
                    }

            content.schema_version = "2.1"

            # Update enrichment status to complete after extraction
            paper.enrichment_status = EnrichmentStatus.COMPLETE

            tier = "quick" if is_quick else "deep"
            logger.info(f"Stored {tier} extraction for paper {paper_id}")

    @classmethod
    def flag_for_deep_extraction(cls, paper_id: int) -> dict:
        """Flag a paper for deep extraction.

        Sets the enrichment_status to NEEDS_DEEP_EXTRACTION.
        Typically called after quick extraction completes and relevance
        scoring determines the paper warrants deeper analysis.

        Args:
            paper_id: Paper ID to flag

        Returns:
            Updated paper dictionary

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            paper.enrichment_status = EnrichmentStatus.NEEDS_DEEP_EXTRACTION
            paper.date_modified = datetime.utcnow()

            logger.info(f"Flagged paper {paper_id} for deep extraction")
            return cls.paper_to_dict(paper)

    @classmethod
    def batch_flag_for_deep_extraction(cls, paper_ids: list[int]) -> dict:
        """Flag multiple papers for deep extraction.

        Args:
            paper_ids: List of paper IDs to flag

        Returns:
            Summary with flagged count and any errors
        """
        flagged = []
        errors = []

        for paper_id in paper_ids:
            try:
                cls.flag_for_deep_extraction(paper_id)
                flagged.append(paper_id)
            except PaperNotFoundError:
                errors.append({"paper_id": paper_id, "error": "Not found"})
            except Exception as e:
                errors.append({"paper_id": paper_id, "error": str(e)})

        return {
            "flagged_count": len(flagged),
            "flagged_ids": flagged,
            "error_count": len(errors),
            "errors": errors if errors else None,
        }

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
            # Get IDs of papers with chunks (Paper.full_text column is deprecated)
            papers_with_chunks = set(
                p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
            )
            papers = (
                session.query(Paper)
                .filter(~Paper.id.in_(papers_with_content))
                .filter(
                    (Paper.abstract.isnot(None)) |
                    (Paper.id.in_(papers_with_chunks))
                )
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
                    "has_full_text": p.id in papers_with_chunks,
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
        """Bulk delete multiple papers and clean up embeddings.

        Args:
            paper_ids: List of paper IDs to delete

        Returns:
            BatchResult with deleted and failed lists
        """
        processed = []
        failed = []

        # Import embedding stores once for batch operations
        try:
            from embeddings.vectorstore import get_vector_store, get_chunk_store
            vector_store = get_vector_store()
            chunk_store = get_chunk_store()
            embeddings_available = True
        except Exception as e:
            logger.warning(f"ChromaDB not available for cleanup: {e}")
            embeddings_available = False

        with get_session() as session:
            for paper_id in paper_ids:
                try:
                    paper = session.query(Paper).filter(Paper.id == paper_id).first()
                    if paper:
                        # Delete from ChromaDB FIRST
                        if embeddings_available:
                            try:
                                vector_store.delete([str(paper_id)])
                                chunk_store.delete_paper_chunks(paper_id)
                            except Exception as e:
                                logger.warning(f"Failed to delete embeddings for paper {paper_id}: {e}")

                        # Then delete from SQLite
                        session.delete(paper)
                        processed.append(paper_id)
                    else:
                        failed.append({"id": paper_id, "error": "Paper not found"})
                except Exception as e:
                    failed.append({"id": paper_id, "error": str(e)})

        logger.info(f"Batch deleted {len(processed)} papers, {len(failed)} failed")
        return BatchResult(processed=processed, failed=failed)

    # =========================================================================
    # Project Registry Helpers (for Claude extraction)
    # =========================================================================

    @classmethod
    def load_projects_config(cls) -> dict:
        """Load project registry from data/projects.json.

        Returns:
            Dict with 'version' and 'projects' list, or empty dict if not found.
        """
        import json
        from config.ai_settings import PROJECT_ROOT

        config_path = PROJECT_ROOT / "data" / "projects.json"

        if not config_path.exists():
            logger.warning(f"Projects config not found: {config_path}")
            return {"version": "1.0", "projects": []}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            logger.debug(f"Loaded {len(config.get('projects', []))} projects from config")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in projects.json: {e}")
            return {"version": "1.0", "projects": []}
        except Exception as e:
            logger.error(f"Error loading projects config: {e}")
            return {"version": "1.0", "projects": []}

    @classmethod
    def check_paper_in_bib(
        cls,
        doi: str | None,
        title: str,
        bib_path: str
    ) -> tuple[bool, str | None]:
        """Check if a paper is already cited in a .bib file.

        Matches by DOI (exact) or title (fuzzy).

        Args:
            doi: Paper DOI (preferred match)
            title: Paper title (fallback fuzzy match)
            bib_path: Path to .bib file

        Returns:
            Tuple of (is_in_bib, citation_key or None)
        """
        from pathlib import Path
        import re

        bib_file = Path(bib_path)
        if not bib_file.exists():
            logger.debug(f"Bib file not found: {bib_path}")
            return False, None

        try:
            content = bib_file.read_text(encoding="utf-8", errors="ignore")

            # Parse bib entries (simple regex parser)
            entry_pattern = r'@\w+\{([^,]+),([^@]*?)(?=\n@|\Z)'
            entries = re.findall(entry_pattern, content, re.DOTALL)

            for citation_key, entry_body in entries:
                citation_key = citation_key.strip()

                # Check DOI match (exact)
                if doi:
                    doi_match = re.search(
                        r'doi\s*=\s*["{]?([^",}]+)',
                        entry_body,
                        re.IGNORECASE
                    )
                    if doi_match:
                        entry_doi = doi_match.group(1).strip()
                        # Normalize DOIs for comparison
                        if cls._normalize_doi(doi) == cls._normalize_doi(entry_doi):
                            return True, citation_key

                # Check title match (fuzzy)
                title_match = re.search(
                    r'title\s*=\s*["{](.+?)["}]',
                    entry_body,
                    re.IGNORECASE | re.DOTALL
                )
                if title_match:
                    entry_title = title_match.group(1).strip()
                    # Simple fuzzy match: normalize and compare
                    if cls._normalize_title(title) == cls._normalize_title(entry_title):
                        return True, citation_key

            return False, None

        except Exception as e:
            logger.warning(f"Error parsing bib file {bib_path}: {e}")
            return False, None

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        """Normalize DOI for comparison."""
        if not doi:
            return ""
        # Remove common prefixes and lowercase
        doi = doi.lower().strip()
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
        return doi

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for fuzzy comparison."""
        import re
        if not title:
            return ""
        # Remove special chars, lowercase, collapse whitespace
        title = title.lower()
        title = re.sub(r'[^a-z0-9\s]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    @classmethod
    def get_projects_with_bib_status(
        cls,
        paper_id: int
    ) -> list[dict]:
        """Get all projects with whether this paper is in their .bib file.

        Args:
            paper_id: Paper ID to check

        Returns:
            List of project dicts with 'paper_in_bib' and 'citation_key' added
        """
        from pathlib import Path

        # Get paper
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return []
            doi = paper.doi
            title = paper.title

        # Load projects
        config = cls.load_projects_config()
        projects = config.get("projects", [])

        results = []
        for project in projects:
            if not project.get("active", True):
                continue

            # Build full bib path
            project_path = Path(project.get("path", ""))
            bib_relative = project.get("bib_file", "")
            bib_path = project_path / bib_relative

            # Check if paper is in bib
            in_bib, citation_key = cls.check_paper_in_bib(doi, title, str(bib_path))

            results.append({
                "name": project.get("name"),
                "display_name": project.get("display_name"),
                "topics": project.get("topics", []),
                "focus": project.get("focus", ""),
                "relevance_hints": project.get("relevance_hints", {}),
                "paper_in_bib": in_bib,
                "citation_key": citation_key
            })

        return results
