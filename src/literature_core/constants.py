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
    """AI extraction status for paper content."""

    NONE = "none"
    BASIC = "basic"           # Title, abstract extracted
    COMPREHENSIVE = "comprehensive"  # Full analysis with key findings

    ALL = [NONE, BASIC, COMPREHENSIVE]


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
DEFAULT_MIN_SIMILARITY = 0.5

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
