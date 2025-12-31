"""Hybrid Search Service - Combines keyword (BM25) and semantic search with RRF.

This service provides industry-standard hybrid search by combining:
- SQLite FTS5 with BM25 ranking for keyword search
- ChromaDB for semantic/vector search
- Reciprocal Rank Fusion (RRF) for result merging

Research shows hybrid retrieval is the production standard for enterprise RAG
systems, providing "insurance" - if vectors fail, BM25 catches it, and vice versa.

Usage:
    from services import HybridSearchService

    # Basic hybrid search (balanced keyword + semantic)
    results = await HybridSearchService.search("machine learning", limit=10)

    # Semantic-weighted search
    results = await HybridSearchService.search("neural networks", alpha=0.8)

    # Keyword-only search using FTS5
    results = await HybridSearchService.search("BERT", alpha=0.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import joinedload

from literature_core import (
    get_session,
    Paper,
    DEFAULT_SEARCH_LIMIT,
)
from literature_core.fts import search_fts, is_fts_available, get_fts_status

logger = logging.getLogger(__name__)


# Default parameters based on research
DEFAULT_RRF_K = 60  # Standard RRF constant
DEFAULT_ALPHA = 0.65  # Slight semantic preference (0.65 semantic, 0.35 keyword)
DEFAULT_MIN_SIMILARITY = 0.35  # Discovery-focused threshold


@dataclass
class HybridSearchResult:
    """A single hybrid search result."""
    id: int
    title: str
    year: int | None
    authors: list[str]
    abstract: str | None
    doi: str | None
    tags: list[str]
    score: float
    keyword_rank: int | None = None
    semantic_rank: int | None = None
    keyword_score: float | None = None
    semantic_score: float | None = None


@dataclass
class HybridSearchDiagnostics:
    """Diagnostics for hybrid search execution."""
    fts_available: bool
    semantic_available: bool
    keyword_results_count: int
    semantic_results_count: int
    merged_count: int
    fallback_used: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class HybridSearchResults:
    """Collection of hybrid search results with diagnostics."""
    query: str
    results: list[dict]
    count: int
    diagnostics: HybridSearchDiagnostics
    alpha: float
    search_modes: list[str]


class HybridSearchService:
    """Service for hybrid search combining keyword and semantic search."""

    # =========================================================================
    # Configuration
    # =========================================================================

    DEFAULT_K = DEFAULT_RRF_K
    DEFAULT_ALPHA = DEFAULT_ALPHA
    DEFAULT_MIN_SIMILARITY = DEFAULT_MIN_SIMILARITY

    # =========================================================================
    # Main Search Method
    # =========================================================================

    @classmethod
    async def search(
        cls,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        alpha: float = DEFAULT_ALPHA,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        year_min: int | None = None,
        year_max: int | None = None,
        search_modes: list[str] | None = None,
    ) -> HybridSearchResults:
        """Execute hybrid search with configurable weights.

        Combines FTS5 keyword search (BM25) with semantic vector search
        using Reciprocal Rank Fusion for result merging.

        Args:
            query: Search query (natural language or keywords)
            limit: Maximum results to return
            alpha: Semantic weight (0-1). 0.65=balanced, 0=keyword only, 1=semantic only
            min_similarity: Minimum similarity for semantic results (0.35 recommended)
            year_min: Minimum publication year filter
            year_max: Maximum publication year filter
            search_modes: Which modes to use ["keyword", "semantic"]. Default: both

        Returns:
            HybridSearchResults with merged results and diagnostics
        """
        if search_modes is None:
            search_modes = ["keyword", "semantic"]

        diagnostics = HybridSearchDiagnostics(
            fts_available=False,
            semantic_available=False,
            keyword_results_count=0,
            semantic_results_count=0,
            merged_count=0,
        )

        keyword_results: list[tuple[int, float]] = []  # (paper_id, score)
        semantic_results: list[tuple[int, float]] = []

        # Fetch more results than limit for better fusion
        fetch_limit = limit * 3

        # =====================================================================
        # Step 1: FTS5 Keyword Search (BM25)
        # =====================================================================
        if "keyword" in search_modes:
            try:
                fts_status = get_fts_status()
                diagnostics.fts_available = fts_status.is_available

                if fts_status.is_available:
                    fts_results = search_fts(
                        query=query,
                        limit=fetch_limit,
                        year_min=year_min,
                        year_max=year_max,
                    )
                    keyword_results = [
                        (r.paper_id, r.bm25_score) for r in fts_results
                    ]
                    diagnostics.keyword_results_count = len(keyword_results)
                    logger.debug(f"FTS5 returned {len(keyword_results)} results")
                else:
                    diagnostics.warnings.append("FTS5 not available, using fallback")
                    # Fallback to SQL LIKE search
                    keyword_results = cls._fallback_keyword_search(
                        query, fetch_limit, year_min, year_max
                    )
                    diagnostics.keyword_results_count = len(keyword_results)
                    diagnostics.fallback_used = True
                    diagnostics.fallback_reason = "FTS5 not available"

            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
                diagnostics.warnings.append(f"Keyword search error: {str(e)}")

        # =====================================================================
        # Step 2: Semantic Search (Vector)
        # =====================================================================
        if "semantic" in search_modes and alpha > 0:
            try:
                semantic_results = await cls._semantic_search(
                    query=query,
                    limit=fetch_limit,
                    min_similarity=min_similarity,
                    year_min=year_min,
                    year_max=year_max,
                )
                diagnostics.semantic_available = len(semantic_results) > 0
                diagnostics.semantic_results_count = len(semantic_results)
                logger.debug(f"Semantic search returned {len(semantic_results)} results")

            except Exception as e:
                logger.warning(f"Semantic search failed: {e}")
                diagnostics.warnings.append(f"Semantic search error: {str(e)}")
                diagnostics.semantic_available = False

        # =====================================================================
        # Step 3: Merge with Reciprocal Rank Fusion
        # =====================================================================
        if keyword_results or semantic_results:
            merged_ids = cls.reciprocal_rank_fusion(
                ranked_lists=[keyword_results, semantic_results],
                k=cls.DEFAULT_K,
                weights=[1.0 - alpha, alpha],  # keyword weight, semantic weight
            )
            # Take top `limit` results
            merged_ids = merged_ids[:limit]
            diagnostics.merged_count = len(merged_ids)
        else:
            merged_ids = []

        # =====================================================================
        # Step 4: Fetch Full Paper Data
        # =====================================================================
        paper_ids = [pid for pid, _ in merged_ids]
        score_map = {pid: score for pid, score in merged_ids}

        # Create rank maps for diagnostics
        keyword_rank_map = {pid: rank + 1 for rank, (pid, _) in enumerate(keyword_results)}
        semantic_rank_map = {pid: rank + 1 for rank, (pid, _) in enumerate(semantic_results)}
        keyword_score_map = {pid: score for pid, score in keyword_results}
        semantic_score_map = {pid: score for pid, score in semantic_results}

        results = []
        if paper_ids:
            with get_session() as session:
                papers = (
                    session.query(Paper)
                    .options(joinedload(Paper.authors), joinedload(Paper.tags))
                    .filter(Paper.id.in_(paper_ids))
                    .all()
                )

                # Create lookup
                paper_map = {p.id: p for p in papers}

                # Build results in merged order
                for paper_id in paper_ids:
                    if paper_id in paper_map:
                        paper = paper_map[paper_id]
                        result = cls._paper_to_result(
                            paper=paper,
                            score=score_map.get(paper_id),
                            keyword_rank=keyword_rank_map.get(paper_id),
                            semantic_rank=semantic_rank_map.get(paper_id),
                            keyword_score=keyword_score_map.get(paper_id),
                            semantic_score=semantic_score_map.get(paper_id),
                        )
                        results.append(result)

        logger.info(
            f"Hybrid search '{query}' returned {len(results)} results "
            f"(keyword={diagnostics.keyword_results_count}, "
            f"semantic={diagnostics.semantic_results_count})"
        )

        return HybridSearchResults(
            query=query,
            results=results,
            count=len(results),
            diagnostics=diagnostics,
            alpha=alpha,
            search_modes=search_modes,
        )

    # =========================================================================
    # Reciprocal Rank Fusion
    # =========================================================================

    @staticmethod
    def reciprocal_rank_fusion(
        ranked_lists: list[list[tuple[int, float]]],
        k: int = DEFAULT_RRF_K,
        weights: list[float] | None = None,
    ) -> list[tuple[int, float]]:
        """Merge multiple ranked lists using Reciprocal Rank Fusion.

        RRF formula: score(d) = sum(weight_i * 1/(k + rank_i(d)))

        This is the standard fusion method used in production search systems
        because it's robust to score differences between ranking methods.

        Args:
            ranked_lists: List of ranked results, each as [(paper_id, score), ...]
            k: RRF constant (default 60, standard value)
            weights: Optional weights for each ranked list (default: equal)

        Returns:
            Merged results sorted by RRF score: [(paper_id, rrf_score), ...]
        """
        if weights is None:
            weights = [1.0] * len(ranked_lists)

        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]

        # Calculate RRF scores
        rrf_scores: dict[int, float] = {}

        for list_idx, ranked_list in enumerate(ranked_lists):
            weight = weights[list_idx]
            for rank, (paper_id, _) in enumerate(ranked_list):
                # RRF score contribution
                rrf_contribution = weight * (1.0 / (k + rank + 1))
                rrf_scores[paper_id] = rrf_scores.get(paper_id, 0.0) + rrf_contribution

        # Sort by RRF score descending
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_results

    # =========================================================================
    # Score Normalization (Alternative to RRF)
    # =========================================================================

    @staticmethod
    def normalize_scores(
        results: list[tuple[int, float]],
        method: str = "minmax"
    ) -> list[tuple[int, float]]:
        """Normalize scores to 0-1 range.

        Args:
            results: [(paper_id, score), ...]
            method: "minmax" for min-max normalization

        Returns:
            Results with normalized scores
        """
        if not results:
            return []

        scores = [score for _, score in results]
        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [(pid, 1.0) for pid, _ in results]

        return [
            (pid, (score - min_score) / (max_score - min_score))
            for pid, score in results
        ]

    # =========================================================================
    # Internal Methods
    # =========================================================================

    @classmethod
    def _fallback_keyword_search(
        cls,
        query: str,
        limit: int,
        year_min: int | None,
        year_max: int | None,
    ) -> list[tuple[int, float]]:
        """Fallback to SQL LIKE search when FTS5 unavailable."""
        with get_session() as session:
            search_pattern = f"%{query}%"
            db_query = session.query(Paper.id).filter(
                (Paper.title.ilike(search_pattern))
                | (Paper.abstract.ilike(search_pattern))
                | (Paper.full_text.ilike(search_pattern))
            )

            if year_min:
                db_query = db_query.filter(Paper.year >= year_min)
            if year_max:
                db_query = db_query.filter(Paper.year <= year_max)

            results = db_query.order_by(Paper.year.desc()).limit(limit).all()

            # Return with uniform scores (no BM25 available)
            return [(r[0], 1.0) for r in results]

    @classmethod
    async def _semantic_search(
        cls,
        query: str,
        limit: int,
        min_similarity: float,
        year_min: int | None,
        year_max: int | None,
    ) -> list[tuple[int, float]]:
        """Execute semantic search using embeddings.

        Returns:
            List of (paper_id, similarity_score) tuples
        """
        try:
            # Import embedding components
            from embeddings.generator import get_embedding_generator
            from embeddings.vectorstore import get_chunk_store, get_vector_store

            generator = get_embedding_generator()
            query_embedding = generator.generate(query)

            # Try chunk-level search first (more detailed)
            try:
                chunk_store = get_chunk_store()
                chunk_results = chunk_store.search_chunks(
                    query_embedding=query_embedding,
                    limit=limit * 2,
                    min_score=min_similarity,
                )

                if chunk_results:
                    # Deduplicate by paper_id, keeping best score
                    paper_scores: dict[int, float] = {}
                    for chunk in chunk_results:
                        paper_id = chunk.get("paper_id")
                        score = chunk.get("score", 0.0)
                        if paper_id and (paper_id not in paper_scores or score > paper_scores[paper_id]):
                            paper_scores[paper_id] = score

                    # Sort by score descending
                    results = sorted(
                        paper_scores.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:limit]

                    return results

            except Exception as chunk_error:
                logger.debug(f"Chunk search failed, trying paper-level: {chunk_error}")

            # Fallback to paper-level search
            vector_store = get_vector_store()
            paper_results = vector_store.search(
                query_embedding=query_embedding,
                top_k=limit,
                score_threshold=min_similarity,
            )

            return [
                (int(r["id"]), r.get("score", 0.0))
                for r in paper_results
                if r.get("id")
            ]

        except ImportError as e:
            logger.warning(f"Embeddings not available: {e}")
            return []
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    @staticmethod
    def _paper_to_result(
        paper: Paper,
        score: float | None = None,
        keyword_rank: int | None = None,
        semantic_rank: int | None = None,
        keyword_score: float | None = None,
        semantic_score: float | None = None,
    ) -> dict[str, Any]:
        """Convert Paper to search result dict with hybrid metadata."""
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
            result["score"] = round(score, 4)
        if keyword_rank is not None:
            result["keyword_rank"] = keyword_rank
        if semantic_rank is not None:
            result["semantic_rank"] = semantic_rank
        if keyword_score is not None:
            result["keyword_score"] = round(keyword_score, 4)
        if semantic_score is not None:
            result["semantic_score"] = round(semantic_score, 4)

        return result


# Convenience function for direct import
async def hybrid_search(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    alpha: float = DEFAULT_ALPHA,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    **kwargs
) -> HybridSearchResults:
    """Convenience function for hybrid search."""
    return await HybridSearchService.search(
        query=query,
        limit=limit,
        alpha=alpha,
        min_similarity=min_similarity,
        **kwargs
    )
