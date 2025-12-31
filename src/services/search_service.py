"""Search Service - Business logic for search operations.

This service provides keyword, entity-based, and semantic search capabilities.
Semantic search supports both paper-level (title+abstract) and chunk-level
(full text) embeddings.

Usage:
    from services import SearchService

    # Keyword search
    results = SearchService.keyword_search("machine learning", limit=10)

    # Semantic search (chunk-level by default)
    results = await SearchService.semantic_search("ALD precursor delivery", limit=10)

    # Semantic search (paper-level only)
    results = await SearchService.semantic_search("neural networks", search_level="paper")

    # Search by author
    papers = SearchService.search_by_author("Smith", limit=20)

    # Search by tag
    papers = SearchService.search_by_tag("reinforcement-learning", limit=20)
"""
from __future__ import annotations

from dataclasses import dataclass

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Author,
    Tag,
    DEFAULT_SEARCH_LIMIT,
)

logger = get_logger(__name__)

# Embeddings are now in src/embeddings/ - no path manipulation needed


@dataclass
class SearchResult:
    """A single search result."""
    id: int
    title: str
    year: int | None
    authors: list[str]
    abstract: str | None
    doi: str | None
    tags: list[str]
    score: float | None = None


@dataclass
class SearchResults:
    """Collection of search results."""
    query: str
    search_type: str
    results: list[dict]
    count: int
    matching_chunks: dict[int, list[dict]] | None = None  # paper_id -> chunks
    fallback_used: bool = False
    fallback_reason: str | None = None


class SearchService:
    """Service for search operations."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def paper_to_result(paper: Paper, score: float | None = None) -> dict:
        """Convert Paper to search result dict.

        Args:
            paper: Paper ORM instance
            score: Optional relevance score

        Returns:
            Dictionary search result
        """
        result = {
            "id": paper.id,
            "title": paper.title,
            "year": paper.year,
            "authors": [a.name for a in paper.authors],
            "abstract": (
                (paper.abstract[:200] + "...")
                if paper.abstract and len(paper.abstract) > 200
                else paper.abstract
            ),
            "doi": paper.doi,
            "tags": [t.name for t in paper.tags],
        }
        if score is not None:
            result["score"] = round(score, 3)
        return result

    # =========================================================================
    # Keyword Search
    # =========================================================================

    @classmethod
    def keyword_search(
        cls,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> SearchResults:
        """Full-text keyword search across papers.

        Searches title, abstract, and full text using SQL LIKE.

        Args:
            query: Search query string
            limit: Maximum results to return
            year_min: Minimum publication year
            year_max: Maximum publication year

        Returns:
            SearchResults with matching papers
        """
        with get_session() as session:
            search_pattern = f"%{query}%"
            db_query = session.query(Paper).filter(
                (Paper.title.ilike(search_pattern))
                | (Paper.abstract.ilike(search_pattern))
                | (Paper.full_text.ilike(search_pattern))
            )

            if year_min:
                db_query = db_query.filter(Paper.year >= year_min)
            if year_max:
                db_query = db_query.filter(Paper.year <= year_max)

            papers = db_query.order_by(Paper.year.desc()).limit(limit).all()

            logger.info(f"Keyword search '{query}' returned {len(papers)} results")
            return SearchResults(
                query=query,
                search_type="keyword",
                results=[cls.paper_to_result(p) for p in papers],
                count=len(papers),
            )

    # =========================================================================
    # Semantic Search
    # =========================================================================

    @classmethod
    async def semantic_search(
        cls,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        min_similarity: float = 0.35,
        search_level: str = "chunk",
    ) -> SearchResults:
        """Semantic similarity search using embeddings.

        Supports two search levels:
        - "chunk": Search full-text chunks (finds content in paper body)
        - "paper": Search paper-level embeddings (title + abstract only)

        Args:
            query: Natural language query
            limit: Maximum results to return
            min_similarity: Minimum similarity score (0-1)
            search_level: "chunk" for full-text or "paper" for title+abstract

        Returns:
            SearchResults with matching papers and optional chunk context
        """
        try:
            from embeddings.generator import get_embedding_generator

            generator = get_embedding_generator()

            # Generate query embedding
            query_embedding = generator.generate(query)

            if search_level == "chunk":
                return await cls._search_chunks(
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                )
            else:
                return await cls._search_papers(
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                )

        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            # Get keyword results and mark that fallback was used
            fallback_result = cls.keyword_search(query, limit=limit)
            return SearchResults(
                query=fallback_result.query,
                search_type="semantic_fallback",
                results=fallback_result.results,
                count=fallback_result.count,
                fallback_used=True,
                fallback_reason=f"Semantic search unavailable: {str(e)}",
            )

    @classmethod
    async def _search_chunks(
        cls,
        query: str,
        query_embedding,
        limit: int,
        min_similarity: float,
    ) -> SearchResults:
        """Search chunk-level embeddings and deduplicate by paper."""
        from embeddings.vectorstore import get_chunk_store

        chunk_store = get_chunk_store()

        # Search for more chunks than needed to ensure we get enough unique papers
        chunk_results = chunk_store.search_chunks(
            query_embedding=query_embedding,
            limit=limit * 3,
            min_score=min_similarity,
        )

        if not chunk_results:
            logger.info(f"Chunk search '{query}' returned 0 results")
            return SearchResults(
                query=query,
                search_type="semantic_chunk",
                results=[],
                count=0,
                matching_chunks={},
            )

        # Deduplicate by paper, keeping best score and all matching chunks
        paper_scores: dict[int, float] = {}
        paper_chunks: dict[int, list[dict]] = {}

        for chunk in chunk_results:
            paper_id = chunk["paper_id"]
            score = chunk["score"]

            if paper_id not in paper_scores or score > paper_scores[paper_id]:
                paper_scores[paper_id] = score

            if paper_id not in paper_chunks:
                paper_chunks[paper_id] = []
            paper_chunks[paper_id].append({
                "text": chunk["text"][:300] + "..." if len(chunk["text"]) > 300 else chunk["text"],
                "score": round(score, 3),
                "section": chunk.get("section", ""),
                "chunk_index": chunk.get("chunk_index", 0),
            })

        # Sort by best score and take top N papers
        sorted_papers = sorted(
            paper_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        # Fetch full paper objects with eager loading of relationships
        paper_ids = [p[0] for p in sorted_papers]

        from sqlalchemy.orm import joinedload

        with get_session() as session:
            papers = (
                session.query(Paper)
                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                .filter(Paper.id.in_(paper_ids))
                .all()
            )
            paper_map = {p.id: p for p in papers}

            # Build results in score order (inside session for relationship access)
            results = []
            for paper_id, score in sorted_papers:
                paper = paper_map.get(paper_id)
                if paper:
                    result = cls.paper_to_result(paper, score=score)
                    # Add top matching chunks as preview
                    top_chunks = sorted(
                        paper_chunks.get(paper_id, []),
                        key=lambda c: c["score"],
                        reverse=True
                    )[:2]
                    result["matching_chunks"] = top_chunks
                    results.append(result)

        logger.info(
            f"Chunk search '{query}' returned {len(results)} papers "
            f"from {len(chunk_results)} chunk matches"
        )

        return SearchResults(
            query=query,
            search_type="semantic_chunk",
            results=results,
            count=len(results),
            matching_chunks=paper_chunks,
        )

    @classmethod
    async def _search_papers(
        cls,
        query: str,
        query_embedding,
        limit: int,
        min_similarity: float,
    ) -> SearchResults:
        """Search paper-level embeddings (title + abstract)."""
        from embeddings.vectorstore import get_vector_store

        vector_store = get_vector_store()

        # Search paper embeddings
        results = vector_store.search(
            query_embedding=query_embedding,
            top_k=limit,
            score_threshold=min_similarity,
        )

        if not results:
            logger.info(f"Paper search '{query}' returned 0 results")
            return SearchResults(
                query=query,
                search_type="semantic_paper",
                results=[],
                count=0,
            )

        # Extract paper IDs and scores
        paper_ids = []
        scores = {}
        for r in results:
            try:
                paper_id = int(r["id"])
                paper_ids.append(paper_id)
                scores[paper_id] = r.get("score", 0)
            except (ValueError, TypeError):
                continue

        # Fetch full paper objects with eager loading
        from sqlalchemy.orm import joinedload

        with get_session() as session:
            papers = (
                session.query(Paper)
                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                .filter(Paper.id.in_(paper_ids))
                .all()
            )
            paper_map = {p.id: p for p in papers}

            # Build results preserving score order (inside session)
            formatted = []
            for paper_id in paper_ids:
                paper = paper_map.get(paper_id)
                if paper:
                    formatted.append(cls.paper_to_result(paper, score=scores.get(paper_id)))

        logger.info(f"Paper search '{query}' returned {len(formatted)} results")

        return SearchResults(
            query=query,
            search_type="semantic_paper",
            results=formatted,
            count=len(formatted),
        )

    # =========================================================================
    # Entity-Based Search
    # =========================================================================

    @classmethod
    def search_by_author(
        cls,
        author_name: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> SearchResults:
        """Find all papers by a specific author.

        Args:
            author_name: Author name (partial match supported)
            limit: Maximum results to return

        Returns:
            SearchResults with matching papers
        """
        with get_session() as session:
            papers = (
                session.query(Paper)
                .join(Paper.authors)
                .filter(Author.name.ilike(f"%{author_name}%"))
                .order_by(Paper.year.desc())
                .limit(limit)
                .all()
            )

            logger.info(f"Author search '{author_name}' returned {len(papers)} results")
            return SearchResults(
                query=author_name,
                search_type="author",
                results=[cls.paper_to_result(p) for p in papers],
                count=len(papers),
            )

    @classmethod
    def search_by_tag(
        cls,
        tag_name: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        exact_match: bool = False,
    ) -> SearchResults:
        """Find all papers with a specific tag.

        Args:
            tag_name: Tag name to search for
            limit: Maximum results to return
            exact_match: If True, require exact tag name match.
                        If False (default), use case-insensitive partial matching.

        Returns:
            SearchResults with matching papers
        """
        with get_session() as session:
            query = session.query(Paper).join(Paper.tags)

            if exact_match:
                query = query.filter(Tag.name == tag_name)
            else:
                # Case-insensitive partial matching
                query = query.filter(Tag.name.ilike(f"%{tag_name}%"))

            papers = (
                query
                .order_by(Paper.year.desc())
                .limit(limit)
                .all()
            )

            logger.info(f"Tag search '{tag_name}' returned {len(papers)} results")
            return SearchResults(
                query=tag_name,
                search_type="tag",
                results=[cls.paper_to_result(p) for p in papers],
                count=len(papers),
            )

    @classmethod
    def search_by_doi(cls, doi: str) -> dict | None:
        """Find a paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            Paper dict if found, None otherwise
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.doi == doi).first()
            if paper:
                return cls.paper_to_result(paper)
            return None

    # =========================================================================
    # Discovery & Similarity
    # =========================================================================

    @classmethod
    async def find_similar_papers(
        cls,
        paper_id: int,
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> SearchResults:
        """Find papers similar to a given paper based on semantic similarity.

        Uses the paper's embedding to find semantically similar papers in the
        library. Excludes the source paper from results.

        Args:
            paper_id: ID of the paper to find similar papers for
            limit: Maximum number of similar papers to return
            min_similarity: Minimum similarity score (0-1)

        Returns:
            SearchResults with similar papers, ordered by similarity
        """
        from embeddings.vectorstore import get_vector_store
        from sqlalchemy.orm import joinedload

        vector_store = get_vector_store()

        # Get the source paper's embedding
        paper_data = vector_store.get(ids=[str(paper_id)], include=["embeddings"])

        # Check if we got valid data with an embedding
        has_embedding = (
            paper_data
            and len(paper_data) > 0
            and paper_data[0].get("embedding") is not None
        )
        if not has_embedding:
            # Paper not in vector store - try to get title/abstract and search
            with get_session() as session:
                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if not paper:
                    return SearchResults(
                        query=f"similar to paper {paper_id}",
                        search_type="similar",
                        results=[],
                        count=0,
                    )

                # Create query from title + abstract
                query = f"{paper.title or ''} {paper.abstract or ''}".strip()
                if not query:
                    return SearchResults(
                        query=f"similar to paper {paper_id}",
                        search_type="similar",
                        results=[],
                        count=0,
                    )

            # Use semantic search as fallback
            result = await cls.semantic_search(
                query=query,
                limit=limit + 1,  # +1 to exclude self
                min_similarity=min_similarity,
                search_level="paper",
            )

            # Filter out the source paper
            result.results = [r for r in result.results if r["id"] != paper_id][:limit]
            result.search_type = "similar"
            result.query = f"similar to paper {paper_id}"
            result.count = len(result.results)
            return result

        # Use the paper's embedding to find similar papers
        source_embedding = paper_data[0]["embedding"]

        results = vector_store.search(
            query_embedding=source_embedding,
            top_k=limit + 1,  # +1 to exclude self
            score_threshold=min_similarity,
        )

        # Filter out the source paper
        paper_ids = []
        scores = {}
        for r in results:
            try:
                pid = int(r["id"])
                if pid != paper_id:  # Exclude source paper
                    paper_ids.append(pid)
                    scores[pid] = r.get("score", 0)
            except (ValueError, TypeError):
                continue

        paper_ids = paper_ids[:limit]

        if not paper_ids:
            return SearchResults(
                query=f"similar to paper {paper_id}",
                search_type="similar",
                results=[],
                count=0,
            )

        # Fetch full paper objects
        with get_session() as session:
            papers = (
                session.query(Paper)
                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                .filter(Paper.id.in_(paper_ids))
                .all()
            )
            paper_map = {p.id: p for p in papers}

            # Build results preserving score order
            formatted = []
            for pid in paper_ids:
                paper = paper_map.get(pid)
                if paper:
                    formatted.append(cls.paper_to_result(paper, score=scores.get(pid)))

        logger.info(f"Similar papers search for {paper_id} returned {len(formatted)} results")

        return SearchResults(
            query=f"similar to paper {paper_id}",
            search_type="similar",
            results=formatted,
            count=len(formatted),
        )

    @classmethod
    async def find_papers_like_text(
        cls,
        text: str,
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> SearchResults:
        """Find papers matching free-form text description.

        Useful for finding papers relevant to a paragraph, research question,
        or concept description.

        Args:
            text: Free-form text to match against papers
            limit: Maximum number of papers to return
            min_similarity: Minimum similarity score (0-1)

        Returns:
            SearchResults with matching papers
        """
        # Delegate to semantic_search which handles embedding generation
        result = await cls.semantic_search(
            query=text,
            limit=limit,
            min_similarity=min_similarity,
            search_level="paper",
        )

        result.search_type = "text_similarity"
        return result

    @classmethod
    async def suggest_citations_for_text(
        cls,
        text: str,
        limit: int = 5,
        min_similarity: float = 0.4,
    ) -> SearchResults:
        """Suggest papers to cite for a given text snippet.

        Finds papers that are semantically relevant to the text and could
        serve as citations.

        Args:
            text: Text snippet that needs citations
            limit: Maximum number of suggestions
            min_similarity: Minimum relevance score (0-1)

        Returns:
            SearchResults with citation suggestions
        """
        # Use chunk-level search for more precise matching
        result = await cls.semantic_search(
            query=text,
            limit=limit,
            min_similarity=min_similarity,
            search_level="chunk",
        )

        result.search_type = "citation_suggestion"
        return result
