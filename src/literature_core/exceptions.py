"""Exception hierarchy for literature management operations.

This module defines a structured exception hierarchy that provides:
- Clear error categorization for debugging
- Machine-readable error codes for API responses
- Contextual information for error handling

Usage:
    from literature_core.exceptions import PaperNotFoundError

    try:
        paper = get_paper(paper_id)
    except PaperNotFoundError as e:
        return error(str(e), code="PAPER_NOT_FOUND", details={"paper_id": e.paper_id})
"""


class LiteratureError(Exception):
    """Base exception for all literature operations.

    All custom exceptions inherit from this class, allowing callers to catch
    all literature-related errors with a single except clause.
    """

    code: str = "LITERATURE_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# =============================================================================
# Entity Not Found Errors
# =============================================================================

class EntityNotFoundError(LiteratureError):
    """Base class for entity not found errors."""

    code = "ENTITY_NOT_FOUND"

    def __init__(self, entity_type: str, entity_id: int | str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} {entity_id} not found")


class PaperNotFoundError(EntityNotFoundError):
    """Raised when a paper cannot be found by ID."""

    code = "PAPER_NOT_FOUND"

    def __init__(self, paper_id: int):
        self.paper_id = paper_id
        super().__init__("Paper", paper_id)


class CollectionNotFoundError(EntityNotFoundError):
    """Raised when a collection cannot be found by ID."""

    code = "COLLECTION_NOT_FOUND"

    def __init__(self, collection_id: int):
        self.collection_id = collection_id
        super().__init__("Collection", collection_id)


class NoteNotFoundError(EntityNotFoundError):
    """Raised when a note cannot be found by ID."""

    code = "NOTE_NOT_FOUND"

    def __init__(self, note_id: int):
        self.note_id = note_id
        super().__init__("Note", note_id)


class AuthorNotFoundError(EntityNotFoundError):
    """Raised when an author cannot be found."""

    code = "AUTHOR_NOT_FOUND"

    def __init__(self, identifier: int | str):
        self.identifier = identifier
        super().__init__("Author", identifier)


class TagNotFoundError(EntityNotFoundError):
    """Raised when a tag cannot be found."""

    code = "TAG_NOT_FOUND"

    def __init__(self, identifier: int | str):
        self.identifier = identifier
        super().__init__("Tag", identifier)


# =============================================================================
# Duplicate/Conflict Errors
# =============================================================================

class DuplicateError(LiteratureError):
    """Base class for duplicate entity errors."""

    code = "DUPLICATE_ERROR"


class DuplicatePaperError(DuplicateError):
    """Raised when attempting to create a paper that already exists."""

    code = "DUPLICATE_PAPER"

    def __init__(self, identifier: str, existing_id: int | None = None):
        self.identifier = identifier
        self.existing_id = existing_id
        msg = f"Paper already exists with identifier: {identifier}"
        if existing_id:
            msg += f" (ID: {existing_id})"
        super().__init__(msg)


class DuplicateTagError(DuplicateError):
    """Raised when attempting to create a tag that already exists."""

    code = "DUPLICATE_TAG"

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Tag already exists: {name}")


class DuplicateCollectionError(DuplicateError):
    """Raised when attempting to create a collection that already exists."""

    code = "DUPLICATE_COLLECTION"

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Collection already exists: {name}")


# =============================================================================
# External Service Errors
# =============================================================================

class ExternalServiceError(LiteratureError):
    """Base class for external service errors."""

    code = "EXTERNAL_SERVICE_ERROR"

    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(f"{service}: {message}")


class ExternalAPIError(ExternalServiceError):
    """Raised when an external API call fails."""

    code = "EXTERNAL_API_ERROR"

    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(service, message)


class CrossRefError(ExternalAPIError):
    """Raised when CrossRef API calls fail."""

    code = "CROSSREF_ERROR"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("CrossRef", message, status_code)


class SemanticScholarError(ExternalAPIError):
    """Raised when Semantic Scholar API calls fail."""

    code = "SEMANTIC_SCHOLAR_ERROR"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("Semantic Scholar", message, status_code)


class OpenAlexError(ExternalAPIError):
    """Raised when OpenAlex API calls fail."""

    code = "OPENALEX_ERROR"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("OpenAlex", message, status_code)


class ArxivError(ExternalAPIError):
    """Raised when arXiv API calls fail."""

    code = "ARXIV_ERROR"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__("arXiv", message, status_code)


# =============================================================================
# PDF Acquisition Errors
# =============================================================================

class PDFError(LiteratureError):
    """Base class for PDF-related errors."""

    code = "PDF_ERROR"


class PDFNotFoundError(PDFError):
    """Raised when a PDF cannot be found for a paper."""

    code = "PDF_NOT_FOUND"

    def __init__(self, paper_id: int, tried_sources: list[str] | None = None):
        self.paper_id = paper_id
        self.tried_sources = tried_sources or []
        msg = f"No PDF found for paper {paper_id}"
        if tried_sources:
            msg += f" (tried: {', '.join(tried_sources)})"
        super().__init__(msg)


class PDFAcquisitionError(PDFError):
    """Raised when PDF download fails."""

    code = "PDF_ACQUISITION_ERROR"

    def __init__(self, paper_id: int, reason: str, url: str | None = None):
        self.paper_id = paper_id
        self.reason = reason
        self.url = url
        msg = f"Failed to acquire PDF for paper {paper_id}: {reason}"
        super().__init__(msg)


class PDFExtractionError(PDFError):
    """Raised when text extraction from PDF fails."""

    code = "PDF_EXTRACTION_ERROR"

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Failed to extract text from {file_path}: {reason}")


# =============================================================================
# Zotero Integration Errors
# =============================================================================

class ZoteroError(LiteratureError):
    """Base class for Zotero-related errors."""

    code = "ZOTERO_ERROR"


class ZoteroConnectionError(ZoteroError):
    """Raised when connection to Zotero fails."""

    code = "ZOTERO_CONNECTION_ERROR"

    def __init__(self, message: str):
        super().__init__(f"Zotero connection error: {message}")


class ZoteroSyncError(ZoteroError):
    """Raised when Zotero sync operation fails."""

    code = "ZOTERO_SYNC_ERROR"

    def __init__(self, message: str, items_synced: int = 0):
        self.items_synced = items_synced
        super().__init__(f"Zotero sync error: {message}")


class ZoteroAuthError(ZoteroError):
    """Raised when Zotero authentication fails."""

    code = "ZOTERO_AUTH_ERROR"

    def __init__(self, message: str = "Invalid API key or library ID"):
        super().__init__(f"Zotero authentication error: {message}")


# =============================================================================
# Search Errors
# =============================================================================

class SearchError(LiteratureError):
    """Base class for search-related errors."""

    code = "SEARCH_ERROR"


class SemanticSearchError(SearchError):
    """Raised when semantic search fails."""

    code = "SEMANTIC_SEARCH_ERROR"

    def __init__(self, message: str):
        super().__init__(f"Semantic search error: {message}")


class IndexError(SearchError):
    """Raised when search index operations fail."""

    code = "INDEX_ERROR"

    def __init__(self, message: str):
        super().__init__(f"Search index error: {message}")


# =============================================================================
# Import/Export Errors
# =============================================================================

class ImportExportError(LiteratureError):
    """Base class for import/export errors."""

    code = "IMPORT_EXPORT_ERROR"


class BibTeXParseError(ImportExportError):
    """Raised when BibTeX parsing fails."""

    code = "BIBTEX_PARSE_ERROR"

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        msg = f"BibTeX parse error: {message}"
        if line:
            msg += f" (line {line})"
        super().__init__(msg)


class ImportError(ImportExportError):
    """Raised when import operation fails."""

    code = "IMPORT_ERROR"

    def __init__(self, source: str, message: str):
        self.source = source
        super().__init__(f"Import from {source} failed: {message}")


class ExportError(ImportExportError):
    """Raised when export operation fails."""

    code = "EXPORT_ERROR"

    def __init__(self, format: str, message: str):
        self.format = format
        super().__init__(f"Export to {format} failed: {message}")


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(LiteratureError):
    """Raised when input validation fails."""

    code = "VALIDATION_ERROR"

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"Validation error for '{field}': {message}")


class InvalidIdentifierError(ValidationError):
    """Raised when an identifier (DOI, arXiv ID, etc.) is invalid."""

    code = "INVALID_IDENTIFIER"

    def __init__(self, identifier_type: str, value: str):
        self.identifier_type = identifier_type
        self.value = value
        super().__init__(identifier_type, f"Invalid {identifier_type}: {value}")
