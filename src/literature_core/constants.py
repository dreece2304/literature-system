"""Constants for literature management operations.

Centralizes all magic strings, enums, and default values used throughout
the codebase to ensure consistency and make changes easier.

Usage:
    from literature_core.constants import ReadStatus, DEFAULT_SEARCH_LIMIT

    if paper.read_status == ReadStatus.UNREAD:
        ...
"""
# Enum removed - not used, classes used for string constants


# =============================================================================
# Paper Status Constants
# =============================================================================

class ReadStatus:
    """Reading status values for papers."""

    UNREAD = "unread"
    READING = "reading"
    READ = "read"
    SKIMMED = "skimmed"

    ALL = [UNREAD, READING, READ, SKIMMED]

    @classmethod
    def is_valid(cls, status: str) -> bool:
        return status in cls.ALL


class ExtractionStatus:
    """AI extraction status for paper content.

    Two-tier extraction system:
    - ABSTRACT_ONLY: Quick extraction from title/abstract
    - COMPREHENSIVE: Deep extraction from full PDF text
    """

    NONE = "none"
    ABSTRACT_ONLY = "abstract_only"  # Quick: paper_type, topics, summary
    COMPREHENSIVE = "comprehensive"  # Deep: full schema from PDF chunks

    ALL = [NONE, ABSTRACT_ONLY, COMPREHENSIVE]

    @classmethod
    def is_valid(cls, status: str) -> bool:
        return status in cls.ALL


class MetadataSource:
    """Sources where paper metadata can come from.

    Used for tracking provenance of imported paper data.
    """

    CROSSREF = "crossref"
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    MANUAL = "manual"
    ZOTERO = "zotero"
    BIBTEX = "bibtex"

    # Priority order for metadata lookup (most reliable first)
    LOOKUP_PRIORITY = [CROSSREF, OPENALEX, SEMANTIC_SCHOLAR, ARXIV]

    ALL = [CROSSREF, OPENALEX, SEMANTIC_SCHOLAR, ARXIV, PUBMED, MANUAL, ZOTERO, BIBTEX]

    @classmethod
    def is_valid(cls, source: str) -> bool:
        return source in cls.ALL


class EnrichmentStatus:
    """Status of paper enrichment workflow.

    Tracks what data is available and what's still needed for a paper.

    Flow: PENDING → NEEDS_PDF → NEEDS_CHUNKING → NEEDS_EXTRACTION → COMPLETE
                      ↘            ↘                ↘                ↘
                     FAILED       FAILED           FAILED    NEEDS_DEEP_EXTRACTION → COMPLETE
    """

    PENDING = "pending"                 # Just added, needs triage
    NEEDS_PDF = "needs_pdf"             # Has metadata, waiting for PDF
    NEEDS_CHUNKING = "needs_chunking"   # Has PDF, needs text extraction
    NEEDS_EXTRACTION = "needs_extraction"  # Has chunks, queued for AI extraction
    NEEDS_DEEP_EXTRACTION = "needs_deep_extraction"  # Quick done, flagged for deep
    NEEDS_REVIEW = "needs_review"       # Auto-process found issue, needs human decision
    COMPLETE = "complete"               # Fully processed (quick or deep done)
    FAILED = "failed"                   # Unrecoverable error

    ALL = [PENDING, NEEDS_PDF, NEEDS_CHUNKING, NEEDS_EXTRACTION, NEEDS_DEEP_EXTRACTION,
           NEEDS_REVIEW, COMPLETE, FAILED]

    # Backwards compatibility for old status values
    LEGACY_MAPPING = {
        "needs_abstract": NEEDS_EXTRACTION,
        "needs_chunks": NEEDS_CHUNKING,
    }

    @classmethod
    def is_valid(cls, status: str) -> bool:
        return status in cls.ALL

    @classmethod
    def normalize(cls, status: str) -> str:
        """Normalize legacy status values to current values."""
        return cls.LEGACY_MAPPING.get(status, status)


class ChunkingStatus:
    """PDF chunking status values.

    Tracks the state of PDF text extraction and chunking.
    """

    NONE = "none"            # No PDF or never queued
    PENDING = "pending"      # Queued for processing
    PROCESSING = "processing"  # Currently processing
    COMPLETE = "complete"    # Successfully chunked
    FAILED = "failed"        # Chunking failed

    ALL = [NONE, PENDING, PROCESSING, COMPLETE, FAILED]

    @classmethod
    def is_valid(cls, status: str) -> bool:
        return status in cls.ALL


class ImportMethod:
    """How a paper was imported into the system.

    Tracks the import method for auditing and debugging.
    """

    WIZARD = "wizard"        # Unified import wizard
    BIBTEX = "bibtex"        # BibTeX import
    EXTERNAL = "external"    # Legacy import_from_external
    MANUAL = "manual"        # Manual creation
    ZOTERO = "zotero"        # Zotero sync

    ALL = [WIZARD, BIBTEX, EXTERNAL, MANUAL, ZOTERO]

    @classmethod
    def is_valid(cls, method: str) -> bool:
        return method in cls.ALL


class NoteType:
    """Types of notes that can be attached to papers."""

    HIGHLIGHT = "highlight"
    COMMENT = "comment"
    SUMMARY = "summary"

    ALL = [HIGHLIGHT, COMMENT, SUMMARY]

    @classmethod
    def is_valid(cls, note_type: str) -> bool:
        return note_type in cls.ALL


# =============================================================================
# External Service Constants
# =============================================================================

class ExternalService:
    """External API service identifiers."""

    CROSSREF = "crossref"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    SPRINGER = "springer"
    UNPAYWALL = "unpaywall"

    # Services that can provide metadata
    METADATA_SOURCES = [CROSSREF, SEMANTIC_SCHOLAR, OPENALEX, ARXIV]

    # Services that can provide PDFs
    PDF_SOURCES = [UNPAYWALL, ARXIV, SEMANTIC_SCHOLAR, SPRINGER]


class SearchType:
    """Types of search operations."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    AUTHOR = "author"
    TAG = "tag"
    TITLE = "title"

    ALL = [KEYWORD, SEMANTIC, AUTHOR, TAG, TITLE]


# =============================================================================
# DOI Prefixes by Publisher
# =============================================================================

class DOIPrefix:
    """Common DOI prefixes by publisher for URL generation."""

    ELSEVIER = "10.1016"
    ACS = "10.1021"
    WILEY = "10.1002"
    NATURE = "10.1038"
    SPRINGER = "10.1007"
    RSC = "10.1039"
    IOP = "10.1088"
    AIP = "10.1063"
    TAYLOR_FRANCIS = "10.1080"
    MDPI = "10.3390"
    IEEE = "10.1109"
    PLOS = "10.1371"

    @classmethod
    def get_publisher(cls, doi: str) -> str | None:
        """Get publisher name from DOI prefix."""
        prefix_map = {
            cls.ELSEVIER: "Elsevier",
            cls.ACS: "ACS Publications",
            cls.WILEY: "Wiley",
            cls.NATURE: "Nature",
            cls.SPRINGER: "Springer",
            cls.RSC: "RSC",
            cls.IOP: "IOP Publishing",
            cls.AIP: "AIP Publishing",
            cls.TAYLOR_FRANCIS: "Taylor & Francis",
            cls.MDPI: "MDPI",
            cls.IEEE: "IEEE",
            cls.PLOS: "PLOS",
        }
        for prefix, name in prefix_map.items():
            if doi.startswith(prefix):
                return name
        return None


# =============================================================================
# Default Values
# =============================================================================

# Search defaults
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 500
DEFAULT_MIN_SIMILARITY = 0.35  # Discovery-focused threshold

# Pagination defaults
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Text processing defaults
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
MAX_ABSTRACT_LENGTH = 5000
MAX_TITLE_LENGTH = 500

# File processing
MAX_PDF_SIZE_MB = 100
SUPPORTED_PDF_EXTENSIONS = [".pdf"]

# API timeouts (seconds)
DEFAULT_API_TIMEOUT = 30
LONG_API_TIMEOUT = 60
PDF_DOWNLOAD_TIMEOUT = 120

# Rate limiting (requests per minute)
CROSSREF_RATE_LIMIT = 50
SEMANTIC_SCHOLAR_RATE_LIMIT = 100
OPENALEX_RATE_LIMIT = 100


# =============================================================================
# File Paths (relative to data directory)
# =============================================================================

class DataPaths:
    """Standard relative paths within the data directory."""

    DATABASE = "metadata/literature.db"
    CHROMA = "chroma"
    WHOOSH = "whoosh"
    PDFS = "pdfs"
    EXPORTS = "exports"
    CACHE = "cache"


# =============================================================================
# Export Formats
# =============================================================================

class ExportFormat:
    """Supported export formats."""

    BIBTEX = "bibtex"
    JSON = "json"
    CSV = "csv"

    ALL = [BIBTEX, JSON, CSV]

    @classmethod
    def is_valid(cls, format: str) -> bool:
        return format in cls.ALL


# =============================================================================
# BibTeX Entry Types
# =============================================================================

class BibTeXType:
    """Standard BibTeX entry types."""

    ARTICLE = "article"
    BOOK = "book"
    INPROCEEDINGS = "inproceedings"
    CONFERENCE = "conference"
    INCOLLECTION = "incollection"
    PHDTHESIS = "phdthesis"
    MASTERSTHESIS = "mastersthesis"
    TECHREPORT = "techreport"
    MISC = "misc"
    UNPUBLISHED = "unpublished"

    ALL = [ARTICLE, BOOK, INPROCEEDINGS, CONFERENCE, INCOLLECTION,
           PHDTHESIS, MASTERSTHESIS, TECHREPORT, MISC, UNPUBLISHED]


# =============================================================================
# Rating Scale
# =============================================================================

MIN_RATING = 1
MAX_RATING = 5


# =============================================================================
# Citation Styles
# =============================================================================

class CitationStyle:
    """Supported citation/bibliography styles."""

    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    BIBTEX = "bibtex"
    IEEE = "ieee"

    ALL = [APA, MLA, CHICAGO, BIBTEX, IEEE]
