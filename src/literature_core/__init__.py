"""Literature Core - Shared database models and utilities.

This package provides the core database layer for the literature management system.
It can be imported by both literature-database and literature-ai services.

Usage:
    from literature_core import get_session, Paper, Author, settings

    with get_session() as session:
        papers = session.query(Paper).all()

    # Using exceptions
    from literature_core import PaperNotFoundError
    raise PaperNotFoundError(paper_id=123)

    # Using response helpers
    from literature_core import success, error, paginated
    return success({"count": 10})

    # Using constants
    from literature_core import ReadStatus, DEFAULT_SEARCH_LIMIT

    # Using logging
    from literature_core import setup_logging, get_logger
    setup_logging(level="INFO")
    logger = get_logger(__name__)
"""
from .config import settings, Settings
from .database import get_engine, get_session, get_session_factory, init_db

# Exceptions
from .exceptions import (
    LiteratureError,
    EntityNotFoundError,
    PaperNotFoundError,
    CollectionNotFoundError,
    NoteNotFoundError,
    AuthorNotFoundError,
    TagNotFoundError,
    DuplicateError,
    DuplicatePaperError,
    DuplicateTagError,
    DuplicateCollectionError,
    ExternalServiceError,
    ExternalAPIError,
    CrossRefError,
    SemanticScholarError,
    OpenAlexError,
    ArxivError,
    PDFError,
    PDFNotFoundError,
    PDFAcquisitionError,
    PDFExtractionError,
    ZoteroError,
    ZoteroConnectionError,
    ZoteroSyncError,
    ZoteroAuthError,
    SearchError,
    SemanticSearchError,
    IndexError,
    ImportExportError,
    BibTeXParseError,
    ImportError,
    ExportError,
    ValidationError,
    InvalidIdentifierError,
)

# Constants
from .constants import (
    ReadStatus,
    ExtractionStatus,
    NoteType,
    ExternalService,
    SearchType,
    DOIPrefix,
    DataPaths,
    ExportFormat,
    BibTeXType,
    CitationStyle,
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    MAX_ABSTRACT_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_PDF_SIZE_MB,
    SUPPORTED_PDF_EXTENSIONS,
    DEFAULT_API_TIMEOUT,
    LONG_API_TIMEOUT,
    PDF_DOWNLOAD_TIMEOUT,
    CROSSREF_RATE_LIMIT,
    SEMANTIC_SCHOLAR_RATE_LIMIT,
    OPENALEX_RATE_LIMIT,
    MIN_RATING,
    MAX_RATING,
)

# Response helpers
from .response import (
    success,
    error,
    paginated,
    created,
    updated,
    deleted,
    batch_result,
    search_result,
    status_response,
)

# Logging
from .logging_config import (
    setup_logging,
    get_logger,
    LogContext,
    log_operation,
    log_error,
    DEFAULT_FORMAT,
    DEBUG_FORMAT,
    STRUCTURED_FORMAT,
)

# Models
from .models import (
    Base,
    Paper,
    Author,
    Tag,
    Collection,
    Note,
    Citation,
    SearchIndex,
    Manuscript,
    CitationLocation,
    PaperContent,
    ProjectRelevance,
    # Association tables
    paper_authors,
    paper_tags,
    paper_collections,
)

# Chunk models for embeddings
from .chunks import (
    TextChunk,
    ChunkEmbedding,
    ChunkSearchResult,
)

__all__ = [
    # Config
    "settings",
    "Settings",
    # Database
    "get_engine",
    "get_session",
    "get_session_factory",
    "init_db",
    # Exceptions
    "LiteratureError",
    "EntityNotFoundError",
    "PaperNotFoundError",
    "CollectionNotFoundError",
    "NoteNotFoundError",
    "AuthorNotFoundError",
    "TagNotFoundError",
    "DuplicateError",
    "DuplicatePaperError",
    "DuplicateTagError",
    "DuplicateCollectionError",
    "ExternalServiceError",
    "ExternalAPIError",
    "CrossRefError",
    "SemanticScholarError",
    "OpenAlexError",
    "ArxivError",
    "PDFError",
    "PDFNotFoundError",
    "PDFAcquisitionError",
    "PDFExtractionError",
    "ZoteroError",
    "ZoteroConnectionError",
    "ZoteroSyncError",
    "ZoteroAuthError",
    "SearchError",
    "SemanticSearchError",
    "IndexError",
    "ImportExportError",
    "BibTeXParseError",
    "ImportError",
    "ExportError",
    "ValidationError",
    "InvalidIdentifierError",
    # Constants
    "ReadStatus",
    "ExtractionStatus",
    "NoteType",
    "ExternalService",
    "SearchType",
    "DOIPrefix",
    "DataPaths",
    "ExportFormat",
    "BibTeXType",
    "CitationStyle",
    "DEFAULT_SEARCH_LIMIT",
    "MAX_SEARCH_LIMIT",
    "DEFAULT_MIN_SIMILARITY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "MAX_ABSTRACT_LENGTH",
    "MAX_TITLE_LENGTH",
    "MAX_PDF_SIZE_MB",
    "SUPPORTED_PDF_EXTENSIONS",
    "DEFAULT_API_TIMEOUT",
    "LONG_API_TIMEOUT",
    "PDF_DOWNLOAD_TIMEOUT",
    "CROSSREF_RATE_LIMIT",
    "SEMANTIC_SCHOLAR_RATE_LIMIT",
    "OPENALEX_RATE_LIMIT",
    "MIN_RATING",
    "MAX_RATING",
    # Response helpers
    "success",
    "error",
    "paginated",
    "created",
    "updated",
    "deleted",
    "batch_result",
    "search_result",
    "status_response",
    # Logging
    "setup_logging",
    "get_logger",
    "LogContext",
    "log_operation",
    "log_error",
    "DEFAULT_FORMAT",
    "DEBUG_FORMAT",
    "STRUCTURED_FORMAT",
    # Base
    "Base",
    # Models
    "Paper",
    "Author",
    "Tag",
    "Collection",
    "Note",
    "Citation",
    "SearchIndex",
    "Manuscript",
    "CitationLocation",
    "PaperContent",
    "ProjectRelevance",
    # Association tables
    "paper_authors",
    "paper_tags",
    "paper_collections",
    # Chunk models
    "TextChunk",
    "ChunkEmbedding",
    "ChunkSearchResult",
]

__version__ = "0.1.0"
