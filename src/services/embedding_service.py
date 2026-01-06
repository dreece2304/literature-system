"""Embedding Service for managing paper embeddings.

Provides functionality to:
- Check which papers need embeddings
- Generate embeddings for papers (batch processing)
- Report embedding coverage status

Usage:
    from services import EmbeddingService

    # Check status
    status = EmbeddingService.get_embedding_status()

    # Process papers needing embeddings
    result = await EmbeddingService.process_queue(limit=50)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from literature_core import get_session, Paper, PaperChunk, get_logger
from .paper_service import PaperService

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass
class EmbeddingStatus:
    """Status of embedding coverage."""

    total_papers: int = 0
    papers_with_abstract: int = 0
    papers_with_full_text: int = 0

    # Paper-level embeddings (title + abstract)
    paper_embeddings_count: int = 0
    papers_needing_paper_embedding: int = 0

    # Chunk-level embeddings (full text)
    chunk_embeddings_count: int = 0
    papers_with_chunks: int = 0
    papers_needing_chunk_embedding: int = 0

    # IDs of papers needing work
    paper_ids_needing_paper_embedding: list[int] = field(default_factory=list)
    paper_ids_needing_chunk_embedding: list[int] = field(default_factory=list)

    @property
    def paper_coverage_percent(self) -> float:
        """Percentage of papers with paper-level embeddings."""
        if self.papers_with_abstract == 0:
            return 100.0
        return (self.paper_embeddings_count / self.papers_with_abstract) * 100

    @property
    def chunk_coverage_percent(self) -> float:
        """Percentage of full-text papers with chunk embeddings."""
        if self.papers_with_full_text == 0:
            return 100.0
        return (self.papers_with_chunks / self.papers_with_full_text) * 100


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""

    papers_processed: int = 0
    chunks_created: int = 0
    paper_embeddings_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 or self.papers_processed > 0


class EmbeddingService:
    """Service for managing paper embeddings."""

    @classmethod
    def get_embedding_status(cls, include_ids: bool = False) -> EmbeddingStatus:
        """Get current embedding coverage status.

        Args:
            include_ids: If True, include lists of paper IDs needing embeddings

        Returns:
            EmbeddingStatus with coverage information
        """
        from embeddings.vectorstore import get_vector_store, get_chunk_store

        status = EmbeddingStatus()

        # Get database counts
        with get_session() as session:
            status.total_papers = session.query(Paper).count()
            status.papers_with_abstract = (
                session.query(Paper).filter(Paper.abstract.isnot(None)).count()
            )
            # Count papers with chunks (Paper.full_text column is deprecated)
            papers_with_chunks_db = set(
                p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
            )
            status.papers_with_full_text = len(papers_with_chunks_db)

            # Get all paper IDs for comparison
            all_paper_ids = set(
                p.id for p in session.query(Paper.id).all()
            )
            papers_with_abstract_ids = set(
                p.id
                for p in session.query(Paper.id).filter(
                    Paper.abstract.isnot(None)
                ).all()
            )

        # Get paper-level embedding status
        try:
            paper_store = get_vector_store()
            paper_stats = paper_store.get_stats()
            status.paper_embeddings_count = paper_stats.get("count", 0)

            # Get IDs of papers with embeddings
            embedded_paper_ids = set()
            if status.paper_embeddings_count > 0:
                # Get all IDs from ChromaDB
                result = paper_store.collection.get(include=[])
                if result and result.get("ids"):
                    embedded_paper_ids = set(int(id_) for id_ in result["ids"])

            # Papers needing paper embedding: have abstract but no embedding
            needing_paper = papers_with_abstract_ids - embedded_paper_ids
            status.papers_needing_paper_embedding = len(needing_paper)
            if include_ids:
                status.paper_ids_needing_paper_embedding = sorted(needing_paper)

        except Exception as e:
            logger.warning(f"Could not get paper embedding status: {e}")

        # Get chunk-level embedding status
        try:
            chunk_store = get_chunk_store()
            chunk_stats = chunk_store.get_stats()
            status.chunk_embeddings_count = chunk_stats.get("total_chunks", 0)
            status.papers_with_chunks = chunk_stats.get("papers_indexed", 0)

            # Get IDs of papers with chunk embeddings
            chunked_paper_ids = set()
            if status.papers_with_chunks > 0:
                result = chunk_store.collection.get(include=["metadatas"])
                if result and result.get("metadatas"):
                    chunked_paper_ids = set(
                        m.get("paper_id")
                        for m in result["metadatas"]
                        if m.get("paper_id")
                    )

            # Papers needing chunk embedding: have text chunks but no embeddings
            needing_chunks = papers_with_chunks_db - chunked_paper_ids
            status.papers_needing_chunk_embedding = len(needing_chunks)
            if include_ids:
                status.paper_ids_needing_chunk_embedding = sorted(needing_chunks)

        except Exception as e:
            logger.warning(f"Could not get chunk embedding status: {e}")

        return status

    @classmethod
    async def process_queue(
        cls,
        limit: int = 50,
        include_paper_embeddings: bool = True,
        include_chunk_embeddings: bool = True,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> EmbeddingResult:
        """Process papers that need embeddings.

        Args:
            limit: Maximum papers to process
            include_paper_embeddings: Generate paper-level embeddings
            include_chunk_embeddings: Generate chunk-level embeddings
            chunk_size: Target characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            EmbeddingResult with processing statistics
        """
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_vector_store, get_chunk_store

        result = EmbeddingResult()

        # Get status to find papers needing work
        status = cls.get_embedding_status(include_ids=True)

        # Initialize embedding tools
        generator = get_embedding_generator()

        # Process paper-level embeddings
        if include_paper_embeddings and status.paper_ids_needing_paper_embedding:
            paper_store = get_vector_store()
            paper_ids = status.paper_ids_needing_paper_embedding[:limit]

            with get_session() as session:
                papers = (
                    session.query(Paper)
                    .filter(Paper.id.in_(paper_ids))
                    .all()
                )

                for paper in papers:
                    try:
                        # Generate embedding for title + abstract
                        text = f"{paper.title or ''} {paper.abstract or ''}"
                        if not text.strip():
                            continue

                        embedding = generator.generate(text)

                        # Add to vector store
                        paper_store.add(
                            id=str(paper.id),
                            embedding=embedding,
                            metadata={
                                "paper_id": paper.id,
                                "title": paper.title or "",
                                "year": paper.year,
                            },
                            document=text[:1000],  # Truncate for storage
                        )
                        result.paper_embeddings_created += 1
                        result.papers_processed += 1

                    except Exception as e:
                        error_msg = f"Paper {paper.id}: {str(e)}"
                        logger.error(f"Failed to embed paper: {error_msg}")
                        result.errors.append(error_msg)

        # Process chunk-level embeddings
        if include_chunk_embeddings and status.paper_ids_needing_chunk_embedding:
            chunk_store = get_chunk_store()
            remaining = limit - result.papers_processed
            if remaining > 0:
                paper_ids = status.paper_ids_needing_chunk_embedding[:remaining]

                with get_session() as session:
                    papers = (
                        session.query(Paper)
                        .filter(Paper.id.in_(paper_ids))
                        .all()
                    )

                    for paper in papers:
                        try:
                            # Get full text from chunks (Paper.full_text column is deprecated)
                            full_text = PaperService.get_full_text(paper.id, session)
                            if not full_text:
                                continue

                            # Generate chunk embeddings
                            chunk_embeddings = generator.embed_paper_chunks(
                                paper_id=paper.id,
                                full_text=full_text,
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                            )

                            if chunk_embeddings:
                                chunk_store.add_chunks(
                                    chunk_ids=[c.chunk_id for c in chunk_embeddings],
                                    embeddings=[c.embedding for c in chunk_embeddings],
                                    texts=[c.text for c in chunk_embeddings],
                                    metadatas=[c.to_metadata() for c in chunk_embeddings],
                                )
                                result.chunks_created += len(chunk_embeddings)
                                result.papers_processed += 1

                        except Exception as e:
                            error_msg = f"Paper {paper.id} chunks: {str(e)}"
                            logger.error(f"Failed to embed chunks: {error_msg}")
                            result.errors.append(error_msg)

        return result

    @classmethod
    async def embed_paper(
        cls,
        paper_id: int,
        include_paper_embedding: bool = True,
        include_chunk_embedding: bool = True,
    ) -> EmbeddingResult:
        """Generate embeddings for a single paper.

        Args:
            paper_id: ID of paper to embed
            include_paper_embedding: Generate paper-level embedding
            include_chunk_embedding: Generate chunk-level embedding

        Returns:
            EmbeddingResult with processing statistics
        """
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_vector_store, get_chunk_store

        result = EmbeddingResult()
        generator = get_embedding_generator()

        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                result.errors.append(f"Paper {paper_id} not found")
                return result

            # Generate paper-level embedding
            if include_paper_embedding and paper.abstract:
                try:
                    paper_store = get_vector_store()
                    text = f"{paper.title or ''} {paper.abstract or ''}"
                    embedding = generator.generate(text)

                    paper_store.add(
                        id=str(paper.id),
                        embedding=embedding,
                        metadata={
                            "paper_id": paper.id,
                            "title": paper.title or "",
                            "year": paper.year,
                        },
                        document=text[:1000],
                    )
                    result.paper_embeddings_created += 1
                    result.papers_processed += 1

                except Exception as e:
                    result.errors.append(f"Paper embedding: {str(e)}")

            # Generate chunk embeddings
            # Get full text from chunks (Paper.full_text column is deprecated)
            full_text = PaperService.get_full_text(paper_id, session)
            if include_chunk_embedding and full_text:
                try:
                    chunk_store = get_chunk_store()

                    # Delete existing chunks first
                    try:
                        chunk_store.delete_paper_chunks(paper.id)
                    except Exception:
                        pass

                    chunk_embeddings = generator.embed_paper_chunks(
                        paper_id=paper.id,
                        full_text=full_text,
                    )

                    if chunk_embeddings:
                        chunk_store.add_chunks(
                            chunk_ids=[c.chunk_id for c in chunk_embeddings],
                            embeddings=[c.embedding for c in chunk_embeddings],
                            texts=[c.text for c in chunk_embeddings],
                            metadatas=[c.to_metadata() for c in chunk_embeddings],
                        )
                        result.chunks_created += len(chunk_embeddings)
                        if result.papers_processed == 0:
                            result.papers_processed = 1

                except Exception as e:
                    result.errors.append(f"Chunk embedding: {str(e)}")

        return result
