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
"""
from .paper_service import PaperService
from .collection_service import CollectionService
from .note_service import NoteService
from .search_service import SearchService
from .pdf_service import PDFService
from .import_export_service import ImportExportService
from .citation_service import CitationService
from .hybrid_search_service import HybridSearchService
from .search_diagnostics_service import SearchDiagnosticsService
from .embedding_service import EmbeddingService
from .validation_service import ValidationService

__all__ = [
    "PaperService",
    "CollectionService",
    "NoteService",
    "SearchService",
    "PDFService",
    "ImportExportService",
    "CitationService",
    "HybridSearchService",
    "SearchDiagnosticsService",
    "EmbeddingService",
    "ValidationService",
]
