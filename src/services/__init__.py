"""Services layer for literature management.

The services layer provides business logic and data access for the literature
management system. Services are database-aware and handle all CRUD operations.

Usage:
    from services import PaperService, CollectionService

    # Get a paper
    paper = PaperService.get(123)

    # List papers with filters
    papers, total = PaperService.list(author="Smith", year=2024, limit=20)

    # Get a collection
    collection = CollectionService.get(1)

    # Search (unified entry point)
    from services import UnifiedSearchService
    results = await UnifiedSearchService.search("ALD thin films")

    # Extraction (unified - includes PDF chunking and AI extraction)
    from services import ExtractionService
    result = ExtractionService.extract_pdf_and_store(paper_id)
    stats = ExtractionService.get_queue_stats()
"""
from .paper_service import PaperService
from .collection_service import CollectionService
from .note_service import NoteService
from .search_service import SearchService
from .pdf_service import PDFService
from .import_export_service import ImportExportService
from .citation_service import CitationService
from .unified_search_service import UnifiedSearchService
from .search_diagnostics_service import SearchDiagnosticsService
from .embedding_service import EmbeddingService
from .validation_service import ValidationService
from .extraction_service import ExtractionService
from .paper_import_service import PaperImportService

# Backwards-compatible aliases (DEPRECATED - use ExtractionService instead)
# These will be removed in future version
ChunkedExtractionService = ExtractionService
ChunkingQueueService = ExtractionService

__all__ = [
    "PaperService",
    "CollectionService",
    "NoteService",
    "SearchService",
    "UnifiedSearchService",
    "PDFService",
    "ImportExportService",
    "CitationService",
    "SearchDiagnosticsService",
    "EmbeddingService",
    "ValidationService",
    "ExtractionService",
    "PaperImportService",
    # Deprecated aliases
    "ChunkedExtractionService",
    "ChunkingQueueService",
]
