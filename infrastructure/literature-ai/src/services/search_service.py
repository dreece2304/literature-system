"""
Search service for semantic paper search.

Provides high-level interface for querying the vector store with
automatic embedding generation and result formatting.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from src.embeddings.generator import get_embedding_generator
from src.embeddings.vectorstore import get_vector_store


@dataclass
class SearchResult:
    """Represents a single search result."""

    paper_id: str
    chunk_id: str
    score: float
    text: str
    metadata: Dict[str, Any]

    @property
    def title(self) -> str:
        """Get paper title from metadata."""
        return self.metadata.get("title", "Unknown")

    @property
    def authors(self) -> str:
        """Get paper authors from metadata."""
        return self.metadata.get("authors", "Unknown")

    @property
    def year(self) -> Optional[int]:
        """Get paper year from metadata."""
        return self.metadata.get("year")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "chunk_id": self.chunk_id,
            "score": round(self.score, 4),
            "text": self.text,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "metadata": self.metadata,
        }


class SearchService:
    """
    Service for semantic search over paper collection.

    Features:
    - Automatic query embedding
    - Metadata filtering
    - Result deduplication and ranking
    - Context extraction
    """

    def __init__(self):
        """Initialize search service."""
        self.generator = get_embedding_generator()
        self.vectorstore = get_vector_store()

        logger.info("SearchService initialized")

    def search(
        self,
        query: str,
        top_k: int = 10,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """
        Search for papers matching the query.

        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Metadata filters (e.g., {"year": {"$gte": 2020}})

        Returns:
            List of SearchResult objects
        """
        logger.info(f"Searching: '{query}' (top_k={top_k})")

        # Generate query embedding
        query_embedding = self.generator.generate(query)

        # Search vector store
        raw_results = self.vectorstore.search(
            query_embedding=query_embedding,
            top_k=top_k,
            where=filters,
            score_threshold=score_threshold,
        )

        # Convert to SearchResult objects
        results = []
        for item in raw_results:
            # Extract paper_id from chunk_id (format: paper-id_chunk_N)
            chunk_id = item["id"]
            paper_id = chunk_id.rsplit("_chunk_", 1)[0] if "_chunk_" in chunk_id else chunk_id

            result = SearchResult(
                paper_id=paper_id,
                chunk_id=chunk_id,
                score=item["score"],
                text=item.get("document", ""),
                metadata=item.get("metadata", {}),
            )
            results.append(result)

        logger.info(f"Found {len(results)} results")
        return results

    def search_by_paper_id(
        self,
        paper_id: str,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """
        Get all chunks for a specific paper.

        Args:
            paper_id: Paper ID
            top_k: Maximum number of chunks

        Returns:
            List of SearchResult objects
        """
        logger.debug(f"Fetching chunks for paper: {paper_id}")

        # Get by metadata filter
        raw_results = self.vectorstore.get(
            where={"paper_id": paper_id},
            limit=top_k,
            include=["metadatas", "documents"],
        )

        results = []
        for item in raw_results:
            result = SearchResult(
                paper_id=paper_id,
                chunk_id=item["id"],
                score=1.0,  # Not a similarity search
                text=item.get("document", ""),
                metadata=item.get("metadata", {}),
            )
            results.append(result)

        logger.debug(f"Found {len(results)} chunks for paper {paper_id}")
        return results

    def find_similar_papers(
        self,
        paper_id: str,
        top_k: int = 10,
        exclude_self: bool = True,
    ) -> List[SearchResult]:
        """
        Find papers similar to a given paper.

        Args:
            paper_id: Reference paper ID
            top_k: Number of similar papers to find
            exclude_self: Exclude the reference paper from results

        Returns:
            List of SearchResult objects
        """
        logger.info(f"Finding papers similar to: {paper_id}")

        # Get chunks from the reference paper
        paper_chunks = self.search_by_paper_id(paper_id, top_k=3)

        if not paper_chunks:
            logger.warning(f"No chunks found for paper {paper_id}")
            return []

        # Use the first chunk as query
        # (could also average embeddings, but first chunk usually has title/abstract)
        query_text = paper_chunks[0].text

        # Search for similar papers
        results = self.search(
            query=query_text,
            top_k=top_k * 2,  # Get extra to account for filtering
        )

        # Filter out chunks from the reference paper if needed
        if exclude_self:
            results = [r for r in results if r.paper_id != paper_id]

        # Deduplicate by paper_id (keep highest scoring chunk per paper)
        seen_papers = set()
        deduplicated = []

        for result in results:
            if result.paper_id not in seen_papers:
                deduplicated.append(result)
                seen_papers.add(result.paper_id)

            if len(deduplicated) >= top_k:
                break

        logger.info(f"Found {len(deduplicated)} similar papers")
        return deduplicated

    def search_with_context(
        self,
        query: str,
        context_papers: List[str],
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search within a specific set of papers (context).

        Args:
            query: Search query
            context_papers: List of paper IDs to search within
            top_k: Number of results

        Returns:
            List of SearchResult objects
        """
        logger.info(f"Searching within {len(context_papers)} papers")

        # Generate query embedding
        query_embedding = self.generator.generate(query)

        # Search each paper and aggregate results
        all_results = []

        for paper_id in context_papers:
            # Get paper chunks
            chunks = self.vectorstore.get(
                where={"paper_id": paper_id},
                include=["metadatas", "documents", "embeddings"],
            )

            # Compute similarity for each chunk
            for chunk in chunks:
                if "embedding" not in chunk:
                    continue

                similarity = self.generator.compute_similarity(
                    query_embedding,
                    chunk["embedding"],
                )

                result = SearchResult(
                    paper_id=paper_id,
                    chunk_id=chunk["id"],
                    score=similarity,
                    text=chunk.get("document", ""),
                    metadata=chunk.get("metadata", {}),
                )
                all_results.append(result)

        # Sort by score and return top_k
        all_results.sort(key=lambda x: x.score, reverse=True)
        results = all_results[:top_k]

        logger.info(f"Found {len(results)} results in context")
        return results

    def get_paper_summary(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a summary of a paper from its chunks.

        Args:
            paper_id: Paper ID

        Returns:
            Summary dictionary with title, authors, preview, etc.
        """
        chunks = self.search_by_paper_id(paper_id, top_k=5)

        if not chunks:
            return None

        # Use first chunk metadata (should have full metadata)
        first_chunk = chunks[0]

        # Aggregate text from chunks
        text_preview = " ".join([c.text for c in chunks[:2]])[:500] + "..."

        return {
            "paper_id": paper_id,
            "title": first_chunk.title,
            "authors": first_chunk.authors,
            "year": first_chunk.year,
            "preview": text_preview,
            "num_chunks": len(chunks),
            "metadata": first_chunk.metadata,
        }

    def count_papers(self) -> int:
        """
        Count total number of indexed papers.

        Returns:
            Number of papers (approximate, based on chunks)
        """
        total_chunks = self.vectorstore.count()

        # Estimate papers (assuming average 5 chunks per paper)
        # Note: This is approximate, actual count would require querying unique paper_ids
        estimated_papers = total_chunks // 5

        logger.debug(f"Estimated {estimated_papers} papers from {total_chunks} chunks")
        return estimated_papers

    def get_stats(self) -> Dict[str, Any]:
        """
        Get search service statistics.

        Returns:
            Statistics dictionary
        """
        vectorstore_stats = self.vectorstore.get_stats()

        return {
            "total_chunks": vectorstore_stats["count"],
            "estimated_papers": self.count_papers(),
            "embedding_dimension": self.generator.dimension,
            "distance_metric": vectorstore_stats["distance_metric"],
        }


# Global singleton instance
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """
    Get global SearchService instance (singleton).

    Returns:
        Shared SearchService instance
    """
    global _search_service

    if _search_service is None:
        _search_service = SearchService()

    return _search_service


def reset_search_service():
    """Reset global search service (useful for testing)."""
    global _search_service
    _search_service = None
