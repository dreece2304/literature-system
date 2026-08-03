"""PDF Service - Business logic for PDF acquisition and management.

This service provides PDF acquisition, status tracking, duplicate detection,
and text extraction capabilities.

REFACTOR NOTES (from tools/pdf.py review):
- Fixed race condition: Original had check-then-act with separate sessions
  (query paper, close session, do work, open new session to update).
  Now uses single transaction for atomic updates.
- Fixed O(n²) duplicate detection: Original compared ALL title pairs.
  Now uses sorted/grouped approach for hash duplicates and limits title
  comparison to papers without PDFs (where duplicates matter most).
- Fixed N+1 query: Original accessed paper.authors/tags without eager loading.
  Now uses joinedload for relationships.
- Fixed memory issue: Original fetched ALL papers for status check.
  Now uses database filtering with proper queries.
- Fixed wrong logger: Was using `from loguru import logger` directly.
  Now uses configured get_logger from literature_core.
- Fixed silent failures: Original caught exceptions and returned empty/False.
  Now raises typed exceptions for proper error handling.
- Moved PDF_STORAGE_PATH to settings instead of module-level env var.
- Added proper type hints throughout.
- Removed duplicated _paper_to_dict (now uses shared helper).

Dependencies:
- pdfplumber: For PDF text extraction
- httpx: For PDF downloads
- External search service: For finding PDF URLs

Usage:
    from services import PDFService

    # Get PDF status for papers
    status = PDFService.get_status(filter_type="needs_pdf", limit=50)

    # Acquire PDF for a paper
    result = await PDFService.acquire(paper_id=123, use_vpn=True)

    # Find duplicate papers
    duplicates = PDFService.find_duplicates(method="title", threshold=0.85)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

from literature_core import (
    get_session,
    get_logger,
    settings,
    Paper,
    PaperNotFoundError,
    PDFError,
    DEFAULT_SEARCH_LIMIT,
    EnrichmentStatus,
)

logger = get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class PDFStatusResult:
    """Result of PDF status query."""
    total_papers: int
    has_pdf: int
    needs_pdf: int
    no_identifier: int
    papers: list[dict]
    filter_type: str


@dataclass
class DuplicateGroup:
    """A group of duplicate papers."""
    type: str  # "hash_match" or "title_similarity"
    papers: list[dict]
    file_hash: str | None = None
    similarity: float | None = None


@dataclass
class DuplicateResult:
    """Result of duplicate detection."""
    method: str
    threshold: float | None
    total_papers: int
    duplicate_groups: list[DuplicateGroup]


@dataclass
class AcquireResult:
    """Result of PDF acquisition."""
    status: str  # "success", "already_exists", "not_found", "error"
    paper_id: int
    file_path: str | None = None
    word_count: int | None = None
    pdf_url: str | None = None
    source: str | None = None
    tried_sources: list[str] = field(default_factory=list)
    message: str | None = None


# ============================================================================
# Service Class
# ============================================================================


class PDFService:
    """Service for PDF-related operations."""

    # =========================================================================
    # Configuration
    # =========================================================================

    # Maximum PDF download size (bytes). Downloads beyond this are aborted to
    # prevent a hostile/misbehaving endpoint from exhausting memory or disk.
    MAX_PDF_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB

    @staticmethod
    def get_storage_path() -> Path:
        """Get the PDF storage path from settings."""
        return settings.pdf_storage_path

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def paper_to_pdf_dict(paper: Paper) -> dict:
        """Convert Paper to dict for PDF operations.

        Only includes fields relevant to PDF handling.
        Assumes paper is loaded with relationships.
        """
        title = paper.title or ""
        return {
            "id": paper.id,
            "title": title[:80] + "..." if len(title) > 80 else title,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "file_path": paper.file_path,
            "file_hash": paper.file_hash,
            "word_count": paper.word_count,
        }

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex-encoded SHA256 hash

        Raises:
            PDFError: If file cannot be read
        """
        try:
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except OSError as e:
            raise PDFError(f"Cannot read file for hashing: {e}")

    @staticmethod
    def extract_text(file_path: Path | str, use_ocr: bool = True) -> tuple[str, int]:
        """Extract text from PDF using pdfplumber, with OCR fallback.

        First attempts text extraction with pdfplumber (fast, for text-based PDFs).
        If no text is found and use_ocr=True, falls back to OCR using Tesseract.

        Args:
            file_path: Path to PDF file (string or Path object)
            use_ocr: Whether to use OCR fallback for image-based PDFs

        Returns:
            Tuple of (full_text, word_count)

        Raises:
            PDFError: If text extraction fails
        """
        # Convert string to Path if needed
        if isinstance(file_path, str):
            file_path = Path(file_path)

        try:
            import pdfplumber
        except ImportError:
            raise PDFError("pdfplumber not installed - cannot extract text")

        full_text = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text.append(text)

            combined = "\n\n".join(full_text)
            word_count = len(combined.split())

            # If pdfplumber found text, return it
            if word_count > 0:
                return combined, word_count

            # No text found - try OCR if enabled
            if use_ocr:
                logger.info(f"No embedded text found in {file_path.name}, trying OCR...")
                ocr_text, ocr_words = PDFService._extract_text_ocr(file_path)
                if ocr_words > 0:
                    logger.info(f"OCR extracted {ocr_words} words from {file_path.name}")
                    return ocr_text, ocr_words
                else:
                    logger.warning(f"OCR also found no text in {file_path.name}")

            return combined, word_count

        except Exception as e:
            raise PDFError(f"Failed to extract text from PDF: {e}")

    @staticmethod
    def _extract_text_ocr(file_path: Path) -> tuple[str, int]:
        """Extract text from PDF using OCR (Tesseract).

        Converts PDF pages to images and runs OCR on each.

        Args:
            file_path: Path to PDF file

        Returns:
            Tuple of (full_text, word_count)
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError as e:
            logger.warning(f"OCR dependencies not available: {e}")
            return "", 0

        try:
            # Convert PDF to images (150 DPI is good balance of speed/quality)
            images = convert_from_path(file_path, dpi=150)

            full_text = []
            for i, image in enumerate(images):
                # Run OCR on each page
                text = pytesseract.image_to_string(image, lang='eng')
                if text and text.strip():
                    full_text.append(text.strip())

            combined = "\n\n".join(full_text)
            word_count = len(combined.split())
            return combined, word_count

        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return "", 0

    @staticmethod
    def _sanitize_filename_component(value: str) -> str:
        """Sanitize a string for safe use as a single filename component.

        Replaces path separators and colons with underscores (matching the
        historical DOI behavior so filenames for benign identifiers are
        unchanged and existing files still resolve), strips control
        characters, and removes leading dots. With separators replaced,
        '..' sequences can no longer traverse directories.
        """
        sanitized = str(value).replace("/", "_").replace("\\", "_").replace(":", "_")
        sanitized = "".join(c for c in sanitized if c.isprintable())
        return sanitized.lstrip(".")

    @classmethod
    def generate_filename(cls, paper: dict) -> str:
        """Generate a unique filename for a paper's PDF.

        Uses DOI or arXiv ID if available, falls back to paper ID.
        All components are sanitized so untrusted identifiers (e.g. an
        arxiv_id from an external API) cannot escape the storage directory.
        """
        paper_id = paper.get("id", "unknown")
        doi = paper.get("doi", "")
        arxiv_id = paper.get("arxiv_id", "")

        doi_part = cls._sanitize_filename_component(doi) if doi else ""
        arxiv_part = cls._sanitize_filename_component(arxiv_id) if arxiv_id else ""

        if doi_part:
            base = doi_part
        elif arxiv_part:
            base = f"arxiv_{arxiv_part}"
        else:
            base = f"paper_{cls._sanitize_filename_component(str(paper_id)) or 'unknown'}"

        return f"{base}.pdf"

    # =========================================================================
    # Status and Query Operations
    # =========================================================================

    @classmethod
    def get_status(
        cls,
        filter_type: str = "all",
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> PDFStatusResult:
        """Get PDF status for papers.

        Uses database filtering instead of loading all papers into memory.

        Args:
            filter_type: One of "all", "has_pdf", "needs_pdf"
            limit: Maximum papers to return

        Returns:
            PDFStatusResult with counts and paper list
        """
        limit = min(limit, 1000)  # Cap at 1000

        with get_session() as session:
            # Get counts using efficient database queries
            total = session.query(Paper).count()
            has_pdf_count = session.query(Paper).filter(
                Paper.file_path.isnot(None)
            ).count()
            needs_pdf_count = session.query(Paper).filter(
                Paper.file_path.is_(None),
                (Paper.doi.isnot(None)) | (Paper.arxiv_id.isnot(None)),
            ).count()
            no_id_count = session.query(Paper).filter(
                Paper.file_path.is_(None),
                Paper.doi.is_(None),
                Paper.arxiv_id.is_(None),
            ).count()

            # Build query based on filter
            if filter_type == "has_pdf":
                query = session.query(Paper).filter(
                    Paper.file_path.isnot(None)
                )
            elif filter_type == "needs_pdf":
                query = session.query(Paper).filter(
                    Paper.file_path.is_(None),
                    (Paper.doi.isnot(None)) | (Paper.arxiv_id.isnot(None)),
                )
            else:  # "all"
                query = session.query(Paper)

            papers = query.limit(limit).all()

            return PDFStatusResult(
                total_papers=total,
                has_pdf=has_pdf_count,
                needs_pdf=needs_pdf_count,
                no_identifier=no_id_count,
                papers=[cls.paper_to_pdf_dict(p) for p in papers],
                filter_type=filter_type,
            )

    # =========================================================================
    # Link Local PDF
    # =========================================================================

    @classmethod
    def link_local_pdf(cls, paper_id: int, file_path: str) -> dict:
        """Link an existing local PDF file to a paper.

        Validates the file exists, computes hash, extracts word count,
        and updates the paper record. Also sets enrichment_status to NEEDS_CHUNKING.

        Args:
            paper_id: Paper ID to link PDF to
            file_path: Path to local PDF file

        Returns:
            Dict with paper_id, file_path, file_hash, word_count

        Raises:
            PaperNotFoundError: If paper doesn't exist
            PDFError: If file doesn't exist or is not a valid PDF
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            raise PDFError(f"File not found: {file_path}")

        if not path.is_file():
            raise PDFError(f"Not a file: {file_path}")

        # Validate it's a PDF
        try:
            with open(path, "rb") as f:
                header = f.read(5)
                if not header.startswith(b"%PDF"):
                    raise PDFError(f"Not a valid PDF file: {file_path}")
        except OSError as e:
            raise PDFError(f"Cannot read file: {e}")

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                raise PaperNotFoundError(paper_id)

            # Compute hash and extract text
            file_hash = cls.compute_file_hash(path)

            try:
                _, word_count = cls.extract_text(path)
            except PDFError:
                word_count = 0
                logger.warning(f"Text extraction failed for {file_path}")

            # Update paper
            paper.file_path = str(path.absolute())
            paper.file_hash = file_hash
            paper.word_count = word_count
            paper.enrichment_status = EnrichmentStatus.NEEDS_CHUNKING

            logger.info(
                f"Linked PDF to paper {paper_id}: {file_path} "
                f"({word_count} words)"
            )

            return {
                "paper_id": paper_id,
                "file_path": str(path.absolute()),
                "file_hash": file_hash,
                "word_count": word_count,
            }

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    @classmethod
    def find_duplicates(
        cls,
        method: str = "title",
        threshold: float = 0.85,
        limit: int = 50,
    ) -> DuplicateResult:
        """Find duplicate papers by file hash or title similarity.

        For hash method: Groups papers with identical file hashes.
        For title method: Compares titles using sequence matching.
            Only compares papers that need PDFs (where duplicates matter most)
            to avoid O(n²) complexity on entire library.

        Args:
            method: "hash" or "title"
            threshold: Similarity threshold for title matching (0.0-1.0)
            limit: Maximum duplicate groups to return

        Returns:
            DuplicateResult with duplicate groups
        """
        duplicates: list[DuplicateGroup] = []

        with get_session() as session:
            total = session.query(Paper).count()

            if method == "hash":
                # Efficient: Group by file_hash in database
                from sqlalchemy import func

                # Find hashes that appear more than once
                hash_counts = (
                    session.query(Paper.file_hash, func.count(Paper.id))
                    .filter(Paper.file_hash.isnot(None))
                    .group_by(Paper.file_hash)
                    .having(func.count(Paper.id) > 1)
                    .all()
                )

                for file_hash, count in hash_counts:
                    papers = (
                        session.query(Paper)
                        .filter(Paper.file_hash == file_hash)
                        .all()
                    )
                    duplicates.append(DuplicateGroup(
                        type="hash_match",
                        file_hash=file_hash,
                        papers=[
                            {"id": p.id, "title": p.title, "file_path": p.file_path}
                            for p in papers
                        ],
                    ))

                    if len(duplicates) >= limit:
                        break

            else:  # title similarity
                # Only check papers that need PDFs (reduces comparison count)
                papers = (
                    session.query(Paper)
                    .filter(
                        Paper.file_path.is_(None),
                        Paper.title.isnot(None),
                    )
                    .limit(500)  # Cap to prevent O(n²) explosion
                    .all()
                )

                checked: set[tuple[int, int]] = set()
                for i, p1 in enumerate(papers):
                    for j, p2 in enumerate(papers[i + 1:], i + 1):
                        pair_key = (min(p1.id, p2.id), max(p1.id, p2.id))
                        if pair_key in checked:
                            continue
                        checked.add(pair_key)

                        title1 = (p1.title or "").lower().strip()
                        title2 = (p2.title or "").lower().strip()

                        if not title1 or not title2:
                            continue

                        similarity = SequenceMatcher(None, title1, title2).ratio()
                        if similarity >= threshold:
                            duplicates.append(DuplicateGroup(
                                type="title_similarity",
                                similarity=round(similarity, 3),
                                papers=[
                                    {"id": p1.id, "title": p1.title},
                                    {"id": p2.id, "title": p2.title},
                                ],
                            ))

                            if len(duplicates) >= limit:
                                break

                    if len(duplicates) >= limit:
                        break

        return DuplicateResult(
            method=method,
            threshold=threshold if method == "title" else None,
            total_papers=total,
            duplicate_groups=duplicates,
        )

    # =========================================================================
    # PDF Acquisition
    # =========================================================================

    @classmethod
    async def acquire(
        cls,
        paper_id: int,
        use_vpn: bool = False,
        use_openurl: bool = False,
        use_proxy: bool = False,
    ) -> AcquireResult:
        """Acquire PDF for a paper using multiple strategies.

        Strategies tried in order:
        1. Open access sources (Unpaywall, arXiv, Semantic Scholar)
        2. Direct publisher URL (requires VPN)
        3. UW OpenURL resolver
        4. UW EZProxy (requires browser cookies)

        Uses single transaction for atomic check-and-update.

        Args:
            paper_id: Paper ID to acquire PDF for
            use_vpn: Try direct publisher URLs (use when on VPN)
            use_openurl: Use UW Primo OpenURL resolver
            use_proxy: Use UW EZProxy URLs

        Returns:
            AcquireResult with status and details

        Raises:
            PaperNotFoundError: If paper doesn't exist
        """
        import httpx

        with get_session() as session:
            paper = (
                session.query(Paper)
                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                .filter(Paper.id == paper_id)
                .first()
            )

            if not paper:
                raise PaperNotFoundError(paper_id)

            # Check if already has PDF
            if paper.file_path:
                file_path = Path(paper.file_path)
                if file_path.exists():
                    return AcquireResult(
                        status="already_exists",
                        paper_id=paper_id,
                        file_path=str(file_path),
                        word_count=paper.word_count or 0,
                    )

            # Need DOI or arXiv ID to acquire
            if not paper.doi and not paper.arxiv_id:
                return AcquireResult(
                    status="error",
                    paper_id=paper_id,
                    message="Paper has no DOI or arXiv ID - cannot acquire PDF",
                )

            # Build paper dict for helper functions
            paper_dict = {
                "id": paper.id,
                "title": paper.title,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "authors": [a.name for a in paper.authors],
            }
            doi = paper.doi

            # Try to find PDF URL
            pdf_url = None
            source = None
            tried_sources = []

            # Strategy 1: Open access sources
            pdf_url = await cls._find_open_access_url(paper_dict)
            tried_sources.append("open_access")
            if pdf_url:
                source = "open_access"

            # Strategy 2: Direct publisher URL (when on VPN)
            if not pdf_url and use_vpn and doi:
                pdf_url = cls._get_direct_publisher_url(doi)
                # Elsevier needs special handling
                if not pdf_url and doi.startswith("10.1016"):
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        pdf_url = await cls._get_elsevier_pdf_url(doi, client)
                tried_sources.append("vpn_direct")
                if pdf_url:
                    source = "vpn_direct"

            # Strategy 3: UW OpenURL resolver
            if not pdf_url and use_openurl and doi:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    pdf_url = await cls._resolve_openurl(doi, client)
                tried_sources.append("openurl_resolver")
                if pdf_url:
                    source = "openurl_resolver"

            # Strategy 4: UW EZProxy
            if not pdf_url and use_proxy and doi:
                pdf_url = cls._get_ezproxy_url(doi)
                tried_sources.append("ezproxy")
                if pdf_url:
                    source = "ezproxy"

            if not pdf_url:
                msg = "No PDF found."
                if not use_vpn:
                    msg += " Try use_vpn=true if connected to UW VPN."
                if not use_openurl:
                    msg += " Try use_openurl=true to query UW library."
                return AcquireResult(
                    status="not_found",
                    paper_id=paper_id,
                    tried_sources=tried_sources,
                    message=msg,
                )

            # Generate filename and download
            storage_path = cls.get_storage_path()
            filename = cls.generate_filename(paper_dict)
            file_path = storage_path / filename

            # Defense in depth: never write outside the storage directory
            if not file_path.resolve().is_relative_to(storage_path.resolve()):
                logger.error(
                    f"Refusing to write PDF outside storage directory for paper {paper_id}: {filename!r}"
                )
                return AcquireResult(
                    status="error",
                    paper_id=paper_id,
                    tried_sources=tried_sources,
                    message="Generated PDF filename resolved outside storage directory",
                )

            storage_path.mkdir(parents=True, exist_ok=True)

            success = await cls._download_pdf(pdf_url, file_path)
            if not success:
                return AcquireResult(
                    status="download_failed",
                    paper_id=paper_id,
                    pdf_url=pdf_url,
                    tried_sources=tried_sources,
                    message="Failed to download PDF",
                )

            # Extract text and compute hash
            try:
                _, word_count = cls.extract_text(file_path)
                file_hash = cls.compute_file_hash(file_path)
            except PDFError as e:
                logger.warning(f"Text extraction failed: {e}")
                word_count = 0
                file_hash = cls.compute_file_hash(file_path)

            # Update paper in SAME transaction
            paper.file_path = str(file_path)
            paper.file_hash = file_hash
            paper.word_count = word_count
            # NOTE: We no longer write to paper.full_text - chunking creates PaperChunk records instead

            # Update enrichment status to needs_chunking (has PDF, needs text extraction)
            paper.enrichment_status = EnrichmentStatus.NEEDS_CHUNKING

            logger.info(
                f"Acquired PDF for paper {paper_id}: {file_path} "
                f"({word_count} words, source: {source})"
            )

            result = AcquireResult(
                status="success",
                paper_id=paper_id,
                file_path=str(file_path),
                word_count=word_count,
                pdf_url=pdf_url,
                source=source,
                tried_sources=tried_sources,
            )

        # Auto-extract PDF text and create chunks after successful acquisition
        # Done outside transaction to avoid long locks
        if result.status == "success":
            try:
                from .extraction_service import ExtractionService
                extraction_result = ExtractionService.extract_pdf_and_store(paper_id=paper_id)
                if extraction_result.success:
                    logger.info(
                        f"Extracted PDF for paper {paper_id}: "
                        f"{extraction_result.chunk_count} chunks, "
                        f"{extraction_result.word_count} words"
                    )
                else:
                    logger.warning(
                        f"PDF extraction failed for paper {paper_id}: "
                        f"{extraction_result.error}"
                    )
            except Exception as e:
                # Don't fail the acquisition if extraction fails
                logger.warning(f"Failed to extract PDF for paper {paper_id}: {e}")

        return result

    # =========================================================================
    # Private Helper Methods for PDF Acquisition
    # =========================================================================

    @classmethod
    async def _find_open_access_url(cls, paper: dict) -> str | None:
        """Try to find an open access PDF URL for a paper."""
        doi = paper.get("doi")
        title = paper.get("title", "")
        arxiv_id = paper.get("arxiv_id")

        try:
            # Import here to avoid circular dependency
            from services.external_search import ExternalSearchService
            service = ExternalSearchService()

            # Strategy 1: Unpaywall
            if doi:
                pdf_url = await service.find_pdf_url(doi)
                if pdf_url:
                    return pdf_url

            # Strategy 2: Springer Open Access
            if doi:
                pdf_url = await service.search_springer_openaccess_by_doi(doi)
                if pdf_url:
                    return pdf_url

            # Strategy 3: Semantic Scholar
            if title:
                results = await service._search_semantic_scholar_query(title, limit=1)
                if results and results[0].pdf_url:
                    if service._title_similarity(title, results[0].title) > 0.8:
                        return results[0].pdf_url

        except Exception as e:
            logger.warning(f"External search failed: {e}")

        # Strategy 4: arXiv (predictable URLs)
        if arxiv_id:
            clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            return f"https://arxiv.org/pdf/{clean_id}.pdf"

        return None

    @staticmethod
    def _get_direct_publisher_url(doi: str) -> str | None:
        """Get direct publisher PDF URL (for use with VPN)."""
        publishers = {
            "10.1021": f"https://pubs.acs.org/doi/pdf/{doi}",
            "10.1002": f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
            "10.1038": f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf",
            "10.1007": f"https://link.springer.com/content/pdf/{doi}.pdf",
            "10.1039": f"https://pubs.rsc.org/en/content/articlepdf/{doi.split('/')[-1]}",
            "10.1088": f"https://iopscience.iop.org/article/{doi}/pdf",
            "10.1063": f"https://pubs.aip.org/aip/jap/article-pdf/doi/{doi}",
            "10.1080": f"https://www.tandfonline.com/doi/pdf/{doi}",
            "10.3390": f"https://www.mdpi.com/{doi.split('/')[-1]}/pdf",
        }

        for prefix, url in publishers.items():
            if doi.startswith(prefix):
                return url

        # Elsevier needs special handling - return None
        if doi.startswith("10.1016"):
            return None

        # Generic DOI.org redirect
        return f"https://doi.org/{doi}"

    @staticmethod
    def _get_ezproxy_url(doi: str) -> str | None:
        """Get PDF URL through UW EZProxy."""
        from urllib.parse import urlparse, urlunparse

        UW_EZPROXY_PREFIX = "offcampus.lib.washington.edu"

        publishers = {
            "10.1021": f"https://pubs.acs.org/doi/pdf/{doi}",
            "10.1002": f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
            "10.1038": f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf",
            "10.1007": f"https://link.springer.com/content/pdf/{doi}.pdf",
        }

        for prefix, url_template in publishers.items():
            if doi.startswith(prefix):
                parsed = urlparse(url_template)
                proxied_host = f"{parsed.netloc}.{UW_EZPROXY_PREFIX}"
                return urlunparse(parsed._replace(netloc=proxied_host))

        return None

    @classmethod
    async def _get_elsevier_pdf_url(
        cls,
        doi: str,
        client: Any,
    ) -> str | None:
        """Get Elsevier PDF URL by looking up PII from CrossRef."""
        import re

        try:
            response = await client.get(
                f"https://api.crossref.org/works/{doi}",
                headers={"User-Agent": "LiteratureAI/1.0 (mailto:research@example.com)"},
                timeout=15.0,
            )

            if response.status_code != 200:
                return None

            data = response.json()
            message = data.get("message", {})

            # Look for PDF link
            links = message.get("link", [])
            for link in links:
                if link.get("content-type") == "application/pdf":
                    return link.get("URL")

            # Look for resource link to extract PII
            resource = message.get("resource", {}).get("primary", {}).get("URL")
            if resource and ("sciencedirect.com" in resource or "elsevier.com" in resource):
                pii_match = re.search(r'/pii/([A-Z0-9]+)', resource)
                if pii_match:
                    pii = pii_match.group(1)
                    return f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"

            # Try link array
            for link in links:
                url = link.get("URL", "")
                if "sciencedirect.com" in url:
                    pii_match = re.search(r'/pii/([A-Z0-9]+)', url)
                    if pii_match:
                        pii = pii_match.group(1)
                        return f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"

            return None

        except Exception as e:
            logger.warning(f"Elsevier lookup failed: {e}")
            return None

    @classmethod
    async def _resolve_openurl(
        cls,
        doi: str,
        client: Any,
    ) -> str | None:
        """Resolve DOI through UW Primo OpenURL resolver."""
        import re

        openurl_base = (
            "https://orbiscascade-washington.primo.exlibrisgroup.com"
            "/openurl/01ALLIANCE_UW/01ALLIANCE_UW:UW"
        )
        openurl = f"{openurl_base}?rft_id=info:doi/{doi}"

        try:
            response = await client.get(
                openurl,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )

            if response.status_code != 200:
                return None

            html = response.text

            # Look for PDF links in response
            pdf_patterns = [
                r'href="([^"]+\.pdf[^"]*)"',
                r'href="([^"]+/pdf/[^"]*)"',
                r'href="([^"]+pdfft[^"]*)"',
                r'href="([^"]+pdfdirect[^"]*)"',
                r'(https://[^"]+sciencedirect[^"]+pdfft[^"]*)',
                r'(https://[^"]+wiley[^"]+pdfdirect[^"]*)',
            ]

            for pattern in pdf_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    if match.startswith("http"):
                        logger.debug(f"Found PDF via OpenURL: {match[:80]}...")
                        return match

            return None

        except Exception as e:
            logger.warning(f"OpenURL resolution failed: {e}")
            return None

    @staticmethod
    async def _download_pdf(url: str, output_path: Path) -> bool:
        """Download a PDF from a URL.

        Streams the response with a size cap (MAX_PDF_SIZE_BYTES) so a
        hostile or misbehaving endpoint cannot exhaust memory or disk.
        Only http(s) URLs are fetched - resolver-scraped URLs are untrusted.

        Args:
            url: URL to download from
            output_path: Path to save PDF

        Returns:
            True if download succeeded, False otherwise
        """
        import httpx
        from urllib.parse import urlparse

        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            logger.warning(f"Refusing to download PDF from non-http(s) URL scheme: {scheme or 'none'}")
            return False

        max_bytes = PDFService.MAX_PDF_SIZE_BYTES

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code in (401, 403):
                        logger.debug(f"Access denied (HTTP {response.status_code})")
                        return False

                    if response.status_code != 200:
                        logger.warning(f"Failed to download PDF: HTTP {response.status_code}")
                        return False

                    content_type = response.headers.get("content-type", "")
                    if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                        if "html" in content_type.lower():
                            logger.debug("Got HTML instead of PDF")
                            return False
                        logger.warning(f"Not a PDF: {content_type}")
                        return False

                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > max_bytes:
                                logger.warning(
                                    f"PDF download rejected: Content-Length {content_length} "
                                    f"exceeds cap of {max_bytes} bytes"
                                )
                                return False
                        except ValueError:
                            pass  # Ignore malformed Content-Length; the streaming cap still applies

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            logger.warning(
                                f"PDF download aborted: response exceeded cap of {max_bytes} bytes"
                            )
                            return False
                        chunks.append(chunk)

                content = b"".join(chunks)
                if not content.startswith(b"%PDF"):
                    logger.warning("Downloaded file is not a valid PDF")
                    return False

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(content)
                return True

            except Exception as e:
                logger.error(f"Error downloading PDF: {e}")
                return False
