"""Import/Export Service - Business logic for paper import and export.

This service provides BibTeX parsing, paper import from external sources,
and export in various formats (BibTeX, JSON, CSV).

REFACTOR NOTES (from tools/import_export.py review):
- Fixed N+1 query in export: Original queried notes per paper in a loop.
  Now uses eager loading with joinedload for all relationships.
- Fixed silent exception swallowing: Original used bare `except: pass` for
  external API calls. Now logs warnings and continues.
- Fixed missing eager loading: Original accessed paper.authors/tags without
  joinedload, causing N+1 queries. Now uses selectinload.
- Fixed redundant query in export_collection: Original queried papers twice.
  Now returns paper IDs directly for reuse.
- Added proper logging throughout.
- Added proper type hints.
- Added dataclasses for structured results.
- Centralized BibTeX parsing and formatting logic.

Dependencies:
- ExternalSearchService: For looking up paper metadata from CrossRef, arXiv, etc.

Usage:
    from services import ImportExportService

    # Import from BibTeX
    result = ImportExportService.import_bibtex(content, tags=["review"])

    # Export papers as BibTeX
    bibtex = ImportExportService.export_bibtex(paper_ids=[1, 2, 3])

    # Import from external source
    paper = await ImportExportService.import_from_external(doi="10.1234/...")
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import joinedload, selectinload

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Author,
    Tag,
    Collection,
    Note,
    CollectionNotFoundError,
    ValidationError,
    MAX_SEARCH_LIMIT,
)

logger = get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ImportedPaper:
    """A successfully imported paper."""
    id: int
    title: str
    bibtex_key: str | None = None


@dataclass
class SkippedPaper:
    """A paper that was skipped during import."""
    title: str
    reason: str
    existing_id: int | None = None


@dataclass
class FailedPaper:
    """A paper that failed to import."""
    title: str
    error: str


@dataclass
class ImportResult:
    """Result of an import operation."""
    status: str
    total_entries: int
    imported: list[ImportedPaper]
    skipped: list[SkippedPaper]
    failed: list[FailedPaper]


@dataclass
class ExternalImportResult:
    """Result of importing from an external source."""
    status: str
    paper: dict | None = None
    paper_id: int | None = None
    title: str | None = None
    sources_checked: list[str] = field(default_factory=list)
    message: str | None = None


# ============================================================================
# Service Class
# ============================================================================


class ImportExportService:
    """Service for import/export operations."""

    # =========================================================================
    # BibTeX Parsing
    # =========================================================================

    @staticmethod
    def parse_bibtex(bibtex_content: str) -> list[dict]:
        """Parse BibTeX content into paper dictionaries.

        Handles common BibTeX formats and cleans up LaTeX artifacts.

        Args:
            bibtex_content: Raw BibTeX string

        Returns:
            List of paper dicts with fields: title, authors, year, doi, etc.
        """
        entries = []
        entry_pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,([^@]+)\}'
        field_pattern = r'(\w+)\s*=\s*[\{"]((?:[^{}"]|(?:\{[^{}]*\}))+)[\}"]\s*,?'

        for match in re.finditer(entry_pattern, bibtex_content, re.DOTALL):
            entry_type, key, fields_text = match.groups()
            paper: dict[str, Any] = {
                "bibtex_key": key.strip(),
                "bibtex_type": entry_type.lower(),
            }

            for field_match in re.finditer(field_pattern, fields_text, re.DOTALL):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                # Clean up LaTeX artifacts
                field_value = re.sub(r'[{}]', '', field_value)
                field_value = field_value.replace('\\&', '&')

                if field_name == "title":
                    paper["title"] = field_value
                elif field_name == "author":
                    authors = [a.strip() for a in field_value.split(' and ')]
                    paper["authors"] = authors
                elif field_name == "year":
                    try:
                        paper["year"] = int(field_value)
                    except ValueError:
                        pass
                elif field_name == "doi":
                    paper["doi"] = field_value
                elif field_name == "abstract":
                    paper["abstract"] = field_value
                elif field_name == "journal":
                    paper["journal"] = field_value
                elif field_name == "volume":
                    paper["volume"] = field_value
                elif field_name == "pages":
                    paper["pages"] = field_value
                elif field_name == "eprint":
                    paper["arxiv_id"] = field_value

            if "title" in paper:
                entries.append(paper)

        logger.debug(f"Parsed {len(entries)} BibTeX entries")
        return entries

    @staticmethod
    def format_bibtex_entry(paper: dict, include_abstract: bool = True) -> str:
        """Format a paper dictionary as a BibTeX entry.

        Args:
            paper: Paper dict with title, authors, year, etc.
            include_abstract: Whether to include abstract field

        Returns:
            Formatted BibTeX entry string
        """
        # Generate citation key if not present
        key = paper.get("citation_key") or ""
        if not key:
            first_author = ""
            if paper.get("authors"):
                author = paper["authors"][0]
                if isinstance(author, dict):
                    first_author = author.get("name", "").split()[-1].lower()
                else:
                    first_author = str(author).split()[-1].lower()
            year = paper.get("year", "")
            title_word = (paper.get("title", "").split()[0] if paper.get("title") else "").lower()
            # Clean special characters from key
            key = re.sub(r'[^a-z0-9]', '', f"{first_author}{year}{title_word}")

        entry_type = "article"

        fields = []
        if paper.get("title"):
            fields.append(f'  title = {{{paper["title"]}}}')
        if paper.get("authors"):
            authors_list = paper["authors"]
            if authors_list and isinstance(authors_list[0], dict):
                author_names = [a.get("name", "") for a in authors_list]
            else:
                author_names = [str(a) for a in authors_list]
            fields.append(f'  author = {{{" and ".join(author_names)}}}')
        if paper.get("year"):
            fields.append(f'  year = {{{paper["year"]}}}')
        if paper.get("journal"):
            fields.append(f'  journal = {{{paper["journal"]}}}')
        if paper.get("volume"):
            fields.append(f'  volume = {{{paper["volume"]}}}')
        if paper.get("pages"):
            fields.append(f'  pages = {{{paper["pages"]}}}')
        if paper.get("doi"):
            fields.append(f'  doi = {{{paper["doi"]}}}')
        if include_abstract and paper.get("abstract"):
            fields.append(f'  abstract = {{{paper["abstract"]}}}')
        if paper.get("arxiv_id"):
            fields.append(f'  eprint = {{{paper["arxiv_id"]}}}')

        return f"@{entry_type}{{{key},\n" + ",\n".join(fields) + "\n}"

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def paper_to_export_dict(paper: Paper, include_notes: bool = False) -> dict:
        """Convert Paper model to export-ready dict.

        Assumes relationships are already loaded (eager loading).

        Args:
            paper: Paper ORM instance with loaded relationships
            include_notes: Whether to include notes

        Returns:
            Dictionary ready for export
        """
        result = {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "year": paper.year,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "journal": paper.journal,
            "volume": paper.volume,
            "pages": paper.pages,
            "authors": [a.name for a in paper.authors],
            "tags": [t.name for t in paper.tags],
        }

        if include_notes:
            result["notes"] = [
                {
                    "id": n.id,
                    "content": n.content,
                    "note_type": n.note_type,
                    "page_number": n.page_number,
                }
                for n in paper.notes
            ]

        return result

    @classmethod
    def _create_paper_with_relations(
        cls,
        session,
        title: str,
        abstract: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        arxiv_id: str | None = None,
        journal: str | None = None,
        volume: str | None = None,
        pages: str | None = None,
        authors: list[str] | None = None,
        tags: list[str] | None = None,
        collection_id: int | None = None,
    ) -> Paper:
        """Create a paper with authors, tags, and optional collection.

        All operations are performed in the current session/transaction.

        Args:
            session: SQLAlchemy session
            title: Paper title (required)
            abstract: Paper abstract
            year: Publication year
            doi: Digital Object Identifier
            arxiv_id: arXiv identifier
            journal: Journal name
            volume: Volume number
            pages: Page range
            authors: List of author names
            tags: List of tag names
            collection_id: Collection to add paper to

        Returns:
            Created Paper instance
        """
        paper = Paper(
            title=title,
            abstract=abstract,
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
            journal=journal,
            volume=volume,
            pages=pages,
        )
        session.add(paper)
        session.flush()

        # Add authors
        if authors:
            for author_name in authors:
                if not author_name:
                    continue
                author = session.query(Author).filter(Author.name == author_name).first()
                if not author:
                    author = Author(name=author_name)
                    session.add(author)
                paper.authors.append(author)

        # Add tags
        if tags:
            for tag_name in tags:
                if not tag_name:
                    continue
                tag = session.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)
                paper.tags.append(tag)

        # Add to collection
        if collection_id:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if collection:
                collection.papers.append(paper)

        return paper

    # =========================================================================
    # Import Operations
    # =========================================================================

    @classmethod
    def import_bibtex(
        cls,
        bibtex_content: str,
        tags: list[str] | None = None,
        collection_id: int | None = None,
    ) -> ImportResult:
        """Import papers from BibTeX content.

        Parses BibTeX entries and creates papers in the database.
        Skips papers with duplicate DOIs.

        Args:
            bibtex_content: Raw BibTeX string
            tags: Tags to apply to all imported papers
            collection_id: Collection to add papers to

        Returns:
            ImportResult with imported/skipped/failed counts
        """
        entries = cls.parse_bibtex(bibtex_content)
        if not entries:
            return ImportResult(
                status="error",
                total_entries=0,
                imported=[],
                skipped=[],
                failed=[FailedPaper(title="", error="No valid BibTeX entries found")],
            )

        imported: list[ImportedPaper] = []
        skipped: list[SkippedPaper] = []
        failed: list[FailedPaper] = []

        with get_session() as session:
            for entry in entries:
                try:
                    # Check if paper with same DOI exists
                    if entry.get("doi"):
                        existing = session.query(Paper).filter(
                            Paper.doi == entry["doi"]
                        ).first()
                        if existing:
                            skipped.append(SkippedPaper(
                                title=entry.get("title", "Unknown"),
                                reason="DOI already exists",
                                existing_id=existing.id,
                            ))
                            continue

                    paper = cls._create_paper_with_relations(
                        session,
                        title=entry.get("title", "Unknown Title"),
                        abstract=entry.get("abstract"),
                        year=entry.get("year"),
                        doi=entry.get("doi"),
                        arxiv_id=entry.get("arxiv_id"),
                        journal=entry.get("journal"),
                        volume=entry.get("volume"),
                        pages=entry.get("pages"),
                        authors=entry.get("authors", []),
                        tags=tags,
                        collection_id=collection_id,
                    )

                    imported.append(ImportedPaper(
                        id=paper.id,
                        title=paper.title,
                        bibtex_key=entry.get("bibtex_key"),
                    ))

                except Exception as e:
                    logger.warning(f"Failed to import BibTeX entry: {e}")
                    failed.append(FailedPaper(
                        title=entry.get("title", "Unknown"),
                        error=str(e),
                    ))

        logger.info(
            f"BibTeX import complete: {len(imported)} imported, "
            f"{len(skipped)} skipped, {len(failed)} failed"
        )

        return ImportResult(
            status="completed",
            total_entries=len(entries),
            imported=imported,
            skipped=skipped,
            failed=failed,
        )

    @classmethod
    async def import_from_external(
        cls,
        doi: str | None = None,
        arxiv_id: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        collection_id: int | None = None,
    ) -> ExternalImportResult:
        """Import a paper from external sources.

        Looks up metadata from CrossRef, OpenAlex, Semantic Scholar, or arXiv
        and creates a paper in the database.

        Args:
            doi: DOI to look up
            arxiv_id: arXiv ID to look up
            title: Title to search for
            tags: Tags to apply to imported paper
            collection_id: Collection to add paper to

        Returns:
            ExternalImportResult with status and paper info
        """
        # Import here to avoid circular dependency
        from services.external_search import ExternalSearchService

        if not doi and not arxiv_id and not title:
            raise ValidationError("identifier", "Must provide doi, arxiv_id, or title")

        external_service = ExternalSearchService()
        sources_checked: list[str] = []
        all_results: dict[str, Any] = {}

        # Query multiple APIs based on what we have
        if doi:
            # CrossRef - primary for DOI
            try:
                cr_result = await external_service.lookup_by_doi(doi)
                if cr_result:
                    all_results["crossref"] = cr_result
                    sources_checked.append("crossref")
            except Exception as e:
                logger.warning(f"CrossRef lookup failed: {e}")

            # OpenAlex - secondary
            try:
                oa_results = await external_service._search_openalex(doi, limit=1)
                if oa_results:
                    all_results["openalex"] = oa_results[0]
                    sources_checked.append("openalex")
            except Exception as e:
                logger.warning(f"OpenAlex lookup failed: {e}")

        elif arxiv_id:
            try:
                arxiv_results = await external_service._search_arxiv(arxiv_id, limit=1)
                if arxiv_results:
                    all_results["arxiv"] = arxiv_results[0]
                    sources_checked.append("arxiv")
            except Exception as e:
                logger.warning(f"arXiv lookup failed: {e}")

        elif title:
            try:
                oa_results = await external_service._search_openalex(title, limit=3)
                if oa_results:
                    def sim(r):
                        return external_service._title_similarity(title, r.title)
                    best = max(oa_results, key=sim)
                    if sim(best) > 0.5:
                        all_results["openalex"] = best
                        sources_checked.append("openalex")
            except Exception as e:
                logger.warning(f"OpenAlex search failed: {e}")

            try:
                cr_results = await external_service._search_crossref_multi(title, limit=3)
                if cr_results:
                    best = max(cr_results, key=lambda r: r.confidence)
                    if best.confidence > 0.5:
                        all_results["crossref"] = best
                        sources_checked.append("crossref")
            except Exception as e:
                logger.warning(f"CrossRef search failed: {e}")

        if not all_results:
            return ExternalImportResult(
                status="error",
                sources_checked=sources_checked,
                message="Could not find paper metadata",
            )

        # Merge results from multiple sources
        primary_source = list(all_results.keys())[0]
        r = all_results[primary_source]
        metadata = {
            "title": r.title,
            "authors": r.authors or [],
            "year": r.year,
            "doi": r.doi,
            "abstract": r.abstract,
            "journal": getattr(r, 'journal', None),
            "arxiv_id": getattr(r, 'arxiv_id', None),
        }

        # Fill in missing fields from other sources
        for source_name, result in all_results.items():
            if source_name == primary_source:
                continue
            if not metadata["abstract"] and result.abstract:
                metadata["abstract"] = result.abstract
            if not metadata["doi"] and result.doi:
                metadata["doi"] = result.doi
            if not metadata["authors"] and result.authors:
                metadata["authors"] = result.authors
            if not metadata.get("journal") and getattr(result, 'journal', None):
                metadata["journal"] = result.journal

        # Create paper in database
        with get_session() as session:
            check_doi = metadata.get("doi") or doi
            if check_doi:
                existing = session.query(Paper).filter(Paper.doi == check_doi).first()
                if existing:
                    return ExternalImportResult(
                        status="already_exists",
                        paper_id=existing.id,
                        title=existing.title,
                        sources_checked=sources_checked,
                    )

            paper = cls._create_paper_with_relations(
                session,
                title=metadata.get("title", "Unknown Title"),
                abstract=metadata.get("abstract"),
                year=metadata.get("year"),
                doi=metadata.get("doi") or doi,
                arxiv_id=metadata.get("arxiv_id") or arxiv_id,
                journal=metadata.get("journal"),
                authors=metadata.get("authors", []),
                tags=tags,
                collection_id=collection_id,
            )

            logger.info(f"Imported paper {paper.id} from external sources: {sources_checked}")

            return ExternalImportResult(
                status="success",
                paper=cls.paper_to_export_dict(paper),
                sources_checked=sources_checked,
            )

    # =========================================================================
    # Export Operations
    # =========================================================================

    @classmethod
    def export_papers(
        cls,
        paper_ids: list[int] | None = None,
        format: str = "bibtex",
        include_abstract: bool = True,
        include_notes: bool = False,
        limit: int = MAX_SEARCH_LIMIT,
    ) -> str:
        """Export papers in various formats.

        Uses eager loading to avoid N+1 queries.

        Args:
            paper_ids: Specific paper IDs to export (None for all)
            format: Export format ("bibtex", "json", "csv")
            include_abstract: Include abstracts (BibTeX/JSON)
            include_notes: Include notes (JSON only)
            limit: Maximum papers to export if paper_ids not specified

        Returns:
            Formatted export string
        """
        with get_session() as session:
            query = session.query(Paper).options(
                selectinload(Paper.authors),
                selectinload(Paper.tags),
            )

            if include_notes:
                query = query.options(selectinload(Paper.notes))

            if paper_ids:
                papers = query.filter(Paper.id.in_(paper_ids)).all()
            else:
                papers = query.limit(limit).all()

            paper_dicts = [
                cls.paper_to_export_dict(p, include_notes=include_notes)
                for p in papers
            ]

            if format == "bibtex":
                entries = [
                    cls.format_bibtex_entry(p, include_abstract)
                    for p in paper_dicts
                ]
                return "\n\n".join(entries)

            elif format == "json":
                import json
                return json.dumps(paper_dicts, indent=2)

            elif format == "csv":
                output = io.StringIO()
                fieldnames = ["id", "title", "authors", "year", "journal", "doi"]
                writer = csv.DictWriter(
                    output, fieldnames=fieldnames, extrasaction='ignore'
                )
                writer.writeheader()
                for paper in paper_dicts:
                    row = dict(paper)
                    if row.get("authors"):
                        row["authors"] = "; ".join(row["authors"])
                    writer.writerow(row)
                return output.getvalue()

            else:
                raise ValidationError("format", f"Unknown format: {format}")

    @classmethod
    def export_collection(
        cls,
        collection_id: int,
        format: str = "bibtex",
        include_subcollections: bool = False,
    ) -> str:
        """Export all papers in a collection.

        Args:
            collection_id: Collection to export
            format: Export format
            include_subcollections: Include papers from child collections

        Returns:
            Formatted export string

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            paper_ids = [p.id for p in collection.papers]

            if include_subcollections:
                children = session.query(Collection).filter(
                    Collection.parent_id == collection_id
                ).all()
                for child in children:
                    for p in child.papers:
                        if p.id not in paper_ids:
                            paper_ids.append(p.id)

        return cls.export_papers(
            paper_ids=paper_ids,
            format=format,
            include_abstract=True,
        )
