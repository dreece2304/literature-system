"""Search Diagnostics Service - Health checks for search infrastructure.

Provides comprehensive diagnostics for the search system including:
- FTS5 index status
- ChromaDB vector store status
- Embedding coverage
- Warnings and recommendations

Usage:
    from services import SearchDiagnosticsService

    # Get full diagnostics
    diagnostics = SearchDiagnosticsService.get_diagnostics()

    # Check embedding coverage
    coverage = SearchDiagnosticsService.get_embedding_coverage()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func

from literature_core import get_session, Paper, PaperChunk

logger = logging.getLogger(__name__)


@dataclass
class SearchDiagnostics:
    """Comprehensive search system diagnostics."""
    # FTS5 status
    fts_available: bool = False
    fts_indexed_count: int = 0
    fts_needs_rebuild: bool = False

    # Vector store status
    chromadb_available: bool = False
    chromadb_paper_count: int = 0
    chromadb_chunk_count: int = 0

    # Database status
    total_papers: int = 0
    papers_with_full_text: int = 0
    papers_with_abstract: int = 0

    # Embedding coverage
    papers_with_embeddings: int = 0
    papers_needing_embeddings: int = 0
    embedding_coverage_percent: float = 0.0

    # Model status
    embedding_model_loaded: bool = False
    embedding_model_name: str | None = None

    # Timestamps
    check_time: datetime = field(default_factory=datetime.now)

    # Issues
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class SearchDiagnosticsService:
    """Service for search system health checks."""

    @classmethod
    def get_diagnostics(cls) -> SearchDiagnostics:
        """Get comprehensive search system diagnostics.

        Returns:
            SearchDiagnostics with full status information
        """
        diagnostics = SearchDiagnostics()

        # Check FTS5 status
        cls._check_fts_status(diagnostics)

        # Check database stats
        cls._check_database_stats(diagnostics)

        # Check vector store status
        cls._check_vectorstore_status(diagnostics)

        # Check embedding model
        cls._check_embedding_model(diagnostics)

        # Generate recommendations
        cls._generate_recommendations(diagnostics)

        return diagnostics

    @classmethod
    def _check_fts_status(cls, diagnostics: SearchDiagnostics) -> None:
        """Check FTS5 full-text search status."""
        try:
            from literature_core.fts import get_fts_status

            status = get_fts_status()
            diagnostics.fts_available = status.is_available
            diagnostics.fts_indexed_count = status.indexed_count
            diagnostics.fts_needs_rebuild = status.needs_rebuild

            if status.last_error:
                diagnostics.errors.append(f"FTS5: {status.last_error}")

            if not status.is_available:
                diagnostics.warnings.append(
                    "FTS5 not available - keyword search will be slower"
                )
            elif status.needs_rebuild:
                diagnostics.warnings.append(
                    f"FTS5 index out of sync: {status.indexed_count} indexed, "
                    f"{status.papers_count} total papers"
                )

        except Exception as e:
            diagnostics.errors.append(f"Failed to check FTS5 status: {str(e)}")

    @classmethod
    def _check_database_stats(cls, diagnostics: SearchDiagnostics) -> None:
        """Check database statistics."""
        try:
            with get_session() as session:
                # Total papers
                diagnostics.total_papers = session.query(func.count(Paper.id)).scalar() or 0

                # Papers with chunks (Paper.full_text column is deprecated)
                diagnostics.papers_with_full_text = (
                    session.query(func.count(func.distinct(PaperChunk.paper_id)))
                    .scalar() or 0
                )

                # Papers with abstract
                diagnostics.papers_with_abstract = (
                    session.query(func.count(Paper.id))
                    .filter(Paper.abstract.isnot(None))
                    .filter(Paper.abstract != "")
                    .scalar() or 0
                )

        except Exception as e:
            diagnostics.errors.append(f"Failed to check database stats: {str(e)}")

    @classmethod
    def _check_vectorstore_status(cls, diagnostics: SearchDiagnostics) -> None:
        """Check ChromaDB vector store status."""
        try:
            from embeddings.vectorstore import get_vector_store, get_chunk_store

            # Paper-level embeddings
            try:
                vector_store = get_vector_store()
                diagnostics.chromadb_paper_count = vector_store.count()
                diagnostics.chromadb_available = True
            except Exception as e:
                logger.debug(f"Vector store check failed: {e}")
                diagnostics.chromadb_paper_count = 0

            # Chunk-level embeddings
            try:
                chunk_store = get_chunk_store()
                diagnostics.chromadb_chunk_count = chunk_store.count()
            except Exception as e:
                logger.debug(f"Chunk store check failed: {e}")
                diagnostics.chromadb_chunk_count = 0

            # Calculate embedding coverage
            diagnostics.papers_with_embeddings = diagnostics.chromadb_paper_count
            diagnostics.papers_needing_embeddings = max(
                0, diagnostics.total_papers - diagnostics.papers_with_embeddings
            )

            if diagnostics.total_papers > 0:
                diagnostics.embedding_coverage_percent = round(
                    (diagnostics.papers_with_embeddings / diagnostics.total_papers) * 100,
                    1
                )

            if not diagnostics.chromadb_available:
                diagnostics.warnings.append(
                    "ChromaDB not available - semantic search will not work"
                )
            elif diagnostics.embedding_coverage_percent < 50:
                diagnostics.warnings.append(
                    f"Low embedding coverage ({diagnostics.embedding_coverage_percent}%) - "
                    "semantic search may miss papers"
                )

        except ImportError:
            diagnostics.warnings.append("Embeddings module not available")
        except Exception as e:
            diagnostics.errors.append(f"Failed to check vector store: {str(e)}")

    @classmethod
    def _check_embedding_model(cls, diagnostics: SearchDiagnostics) -> None:
        """Check embedding model status."""
        try:
            from embeddings.generator import get_embedding_generator

            generator = get_embedding_generator()
            diagnostics.embedding_model_loaded = generator is not None
            if generator and hasattr(generator, 'model_name'):
                diagnostics.embedding_model_name = generator.model_name

        except ImportError:
            diagnostics.embedding_model_loaded = False
        except Exception as e:
            diagnostics.warnings.append(f"Embedding model not loaded: {str(e)}")
            diagnostics.embedding_model_loaded = False

    @classmethod
    def _generate_recommendations(cls, diagnostics: SearchDiagnostics) -> None:
        """Generate actionable recommendations."""
        if not diagnostics.fts_available:
            diagnostics.recommendations.append(
                "Run 'python -m scripts.migrate_fts5' to enable FTS5 full-text search"
            )
        elif diagnostics.fts_needs_rebuild:
            diagnostics.recommendations.append(
                "Run 'python -m scripts.migrate_fts5 --rebuild' to rebuild FTS5 index"
            )

        if diagnostics.papers_needing_embeddings > 0:
            diagnostics.recommendations.append(
                f"Generate embeddings for {diagnostics.papers_needing_embeddings} papers "
                "to improve semantic search"
            )

        if diagnostics.papers_with_full_text < diagnostics.total_papers * 0.5:
            missing = diagnostics.total_papers - diagnostics.papers_with_full_text
            diagnostics.recommendations.append(
                f"{missing} papers missing full text - extract PDFs to improve search"
            )

    @classmethod
    def get_embedding_coverage(cls) -> dict[str, Any]:
        """Get detailed embedding coverage statistics.

        Returns:
            Dict with paper-level and chunk-level coverage stats
        """
        diagnostics = cls.get_diagnostics()

        return {
            "total_papers": diagnostics.total_papers,
            "papers_with_embeddings": diagnostics.papers_with_embeddings,
            "papers_needing_embeddings": diagnostics.papers_needing_embeddings,
            "coverage_percent": diagnostics.embedding_coverage_percent,
            "chunk_count": diagnostics.chromadb_chunk_count,
        }

    @classmethod
    def get_search_health(cls) -> dict[str, Any]:
        """Get simplified search health status.

        Returns:
            Dict with overall health status and key metrics
        """
        diagnostics = cls.get_diagnostics()

        # Determine overall health
        has_errors = len(diagnostics.errors) > 0
        has_warnings = len(diagnostics.warnings) > 0

        if has_errors:
            health = "unhealthy"
        elif has_warnings:
            health = "degraded"
        else:
            health = "healthy"

        return {
            "status": health,
            "fts_available": diagnostics.fts_available,
            "semantic_available": diagnostics.chromadb_available,
            "total_papers": diagnostics.total_papers,
            "embedding_coverage_percent": diagnostics.embedding_coverage_percent,
            "warnings": diagnostics.warnings,
            "errors": diagnostics.errors,
            "recommendations": diagnostics.recommendations,
            "check_time": diagnostics.check_time.isoformat(),
        }


def get_search_status() -> dict[str, Any]:
    """Convenience function to get search status."""
    return SearchDiagnosticsService.get_search_health()
