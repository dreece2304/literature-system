"""Unified Search Service - Single entry point for all search operations.

Consolidates keyword, semantic, hybrid, and smart search into one interface.
Includes query preprocessing (spell correction, acronym expansion, synonyms).

Usage:
    from services.unified_search_service import UnifiedSearchService

    # Smart search (default) - typo correction, acronym expansion, hybrid
    results = await UnifiedSearchService.search("ALD thin films")

    # Keyword only - exact FTS5 matching
    results = await UnifiedSearchService.search("photoresist", mode="keyword")

    # Semantic only - embedding similarity
    results = await UnifiedSearchService.search("how atoms deposit", mode="semantic")

    # Hybrid - balanced keyword + semantic
    results = await UnifiedSearchService.search("EUV", mode="hybrid", alpha=0.7)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from literature_core import DEFAULT_SEARCH_LIMIT
from services.search_constants import (
    ACRONYM_EXPANSIONS,
    SCIENTIFIC_SYNONYMS,
    DEFAULT_ALPHA,
    DEFAULT_MIN_SIMILARITY,
)

logger = logging.getLogger(__name__)

SearchMode = Literal["smart", "keyword", "semantic", "hybrid", "exact"]


@dataclass
class UnifiedSearchResults:
    """Results from unified search."""
    query: str
    mode: str
    results: list[dict]
    count: int

    # Mode-specific metadata
    search_type: str = ""

    # Smart mode info
    spell_corrected: str | None = None
    acronyms_expanded: list[str] = field(default_factory=list)
    final_query: str = ""

    # Hybrid mode info
    alpha: float | None = None
    keyword_results_count: int = 0
    semantic_results_count: int = 0

    # Semantic mode info
    search_level: str | None = None

    # General
    strategies_used: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None


@dataclass
class QueryExpansion:
    """Result of query expansion/preprocessing."""
    original: str
    normalized: str
    spell_corrected: str | None = None
    expanded_terms: list[str] = field(default_factory=list)
    acronyms_expanded: list[str] = field(default_factory=list)
    synonyms_added: list[str] = field(default_factory=list)
    final_query: str = ""


class UnifiedSearchService:
    """Unified search service combining all search strategies."""

    # =========================================================================
    # Spell Checking
    # =========================================================================

    _spell_checker = None

    @classmethod
    def _get_spell_checker(cls):
        """Get or create spell checker instance (lazy initialization)."""
        if cls._spell_checker is None:
            try:
                from spellchecker import SpellChecker
                cls._spell_checker = SpellChecker()
                # Add scientific terms to dictionary
                scientific_terms = set()
                for terms in ACRONYM_EXPANSIONS.values():
                    for term in terms:
                        scientific_terms.update(term.lower().split())
                for term in SCIENTIFIC_SYNONYMS.keys():
                    scientific_terms.add(term.lower())
                cls._spell_checker.word_frequency.load_words(scientific_terms)
            except ImportError:
                logger.warning("spellchecker not installed, spell correction disabled")
                return None
        return cls._spell_checker

    # =========================================================================
    # Query Preprocessing
    # =========================================================================

    @classmethod
    def preprocess_query(cls, query: str) -> str:
        """Normalize and clean query.

        - Normalize whitespace
        - Remove problematic characters (keep hyphens and apostrophes)
        """
        # Normalize whitespace
        query = " ".join(query.split())

        # Remove problematic characters but keep hyphens and apostrophes
        query = re.sub(r'[^\w\s\-\'\"]', ' ', query)

        # Normalize whitespace again
        query = " ".join(query.split())

        return query

    @classmethod
    def correct_spelling(cls, query: str) -> tuple[str, list[str]]:
        """Correct spelling mistakes in query.

        Returns:
            Tuple of (corrected_query, list of corrections made)
        """
        spell = cls._get_spell_checker()
        if spell is None:
            return query, []

        words = query.split()
        corrected_words = []
        corrections = []

        for word in words:
            # Skip if it's an acronym (all caps) or very short
            if word.isupper() or len(word) <= 2:
                corrected_words.append(word)
                continue

            # Check if word is misspelled
            word_lower = word.lower()
            if word_lower not in spell:
                correction = spell.correction(word_lower)
                if correction and correction != word_lower:
                    corrected_words.append(correction)
                    corrections.append(f"{word} -> {correction}")
                else:
                    corrected_words.append(word)
            else:
                corrected_words.append(word)

        return " ".join(corrected_words), corrections

    @classmethod
    def expand_acronyms(cls, query: str) -> tuple[str, list[str]]:
        """Expand acronyms in query.

        Returns:
            Tuple of (expanded_query, list of expansions)
        """
        words = query.lower().split()
        expanded_terms = []
        expansions_made = []

        for word in words:
            if word in ACRONYM_EXPANSIONS:
                # Add original acronym
                expanded_terms.append(word.upper())
                for expansion in ACRONYM_EXPANSIONS[word]:
                    # Quote multi-word expansions and escape hyphens for FTS5
                    safe_expansion = expansion.replace("-", " ")
                    if " " in safe_expansion:
                        expanded_terms.append(f'"{safe_expansion}"')
                    else:
                        expanded_terms.append(safe_expansion)
                    expansions_made.append(f"{word.upper()} -> {expansion}")
            else:
                expanded_terms.append(word)

        return " ".join(expanded_terms), expansions_made

    @classmethod
    def add_synonyms(
        cls,
        query: str,
        use_wordnet: bool = True,
        use_scientific: bool = True,
        max_synonyms_per_word: int = 2,
    ) -> tuple[list[str], list[str]]:
        """Add synonyms to expand query.

        Returns:
            Tuple of (list of synonym terms, list of additions made)
        """
        words = query.lower().split()
        synonyms = []
        additions = []

        for word in words:
            word_synonyms = set()

            # Scientific domain synonyms (prioritized)
            if use_scientific and word in SCIENTIFIC_SYNONYMS:
                for syn in SCIENTIFIC_SYNONYMS[word][:max_synonyms_per_word]:
                    word_synonyms.add(syn)

            # WordNet synonyms
            if use_wordnet and len(word_synonyms) < max_synonyms_per_word:
                try:
                    from nltk.corpus import wordnet
                    synsets = wordnet.synsets(word)
                    for synset in synsets[:2]:
                        for lemma in synset.lemmas()[:3]:
                            syn = lemma.name().replace("_", " ").lower()
                            if syn != word and len(syn) > 2:
                                word_synonyms.add(syn)
                                if len(word_synonyms) >= max_synonyms_per_word:
                                    break
                        if len(word_synonyms) >= max_synonyms_per_word:
                            break
                except Exception:
                    pass  # WordNet not available

            if word_synonyms:
                synonyms.extend(word_synonyms)
                additions.append(f"{word} + [{', '.join(word_synonyms)}]")

        return synonyms, additions

    @classmethod
    def expand_query(
        cls,
        query: str,
        correct_spelling: bool = True,
        expand_acronyms: bool = True,
        add_synonyms: bool = True,
    ) -> QueryExpansion:
        """Fully expand a query with all enhancements.

        Args:
            query: Original search query
            correct_spelling: Fix typos
            expand_acronyms: Expand acronyms like ALD, EUV
            add_synonyms: Add synonyms for key terms

        Returns:
            QueryExpansion with all transformations
        """
        expansion = QueryExpansion(original=query, normalized="")

        # Step 1: Preprocess
        normalized = cls.preprocess_query(query)
        expansion.normalized = normalized

        current_query = normalized

        # Step 2: Spell correction
        if correct_spelling:
            corrected, corrections = cls.correct_spelling(current_query)
            if corrections:
                expansion.spell_corrected = corrected
                current_query = corrected
                logger.debug(f"Spell corrections: {corrections}")

        # Step 3: Acronym expansion
        if expand_acronyms:
            expanded, expansions = cls.expand_acronyms(current_query)
            if expansions:
                expansion.acronyms_expanded = expansions
                current_query = expanded
                logger.debug(f"Acronym expansions: {expansions}")

        # Step 4: Synonym expansion
        if add_synonyms:
            synonyms, additions = cls.add_synonyms(current_query)
            if synonyms:
                expansion.synonyms_added = additions
                expansion.expanded_terms = synonyms
                current_query = current_query + " " + " ".join(synonyms)
                logger.debug(f"Synonyms added: {additions}")

        expansion.final_query = current_query
        return expansion

    # =========================================================================
    # Main Search Entry Point
    # =========================================================================

    @classmethod
    async def search(
        cls,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        mode: SearchMode = "smart",

        # Smart mode options
        correct_spelling: bool = True,
        expand_acronyms: bool = True,
        add_synonyms: bool = False,

        # Hybrid/balance options
        alpha: float = 0.65,

        # Semantic options
        search_level: str = "chunk",
        min_similarity: float = 0.35,

        # Re-ranking options
        rerank: bool | None = None,  # None = use settings default

        # Filters
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> UnifiedSearchResults:
        """Execute unified search with configurable mode.

        Args:
            query: Search query string
            limit: Maximum results to return
            mode: Search mode - "smart", "keyword", "semantic", "hybrid", or "exact"

            # Smart mode options (mode="smart")
            correct_spelling: Auto-correct typos
            expand_acronyms: Expand acronyms (ALD, EUV, etc.)
            add_synonyms: Add WordNet/scientific synonyms

            # Hybrid options (mode="hybrid" or "smart")
            alpha: Semantic weight (0=keyword only, 1=semantic only, 0.65=balanced)

            # Semantic options (mode="semantic")
            search_level: "chunk" for full-text, "paper" for title+abstract
            min_similarity: Minimum similarity score (0-1)

            # Re-ranking options
            rerank: Enable cross-encoder re-ranking (None = use settings default)

            # Filters (all modes)
            year_min: Minimum publication year
            year_max: Maximum publication year

        Returns:
            UnifiedSearchResults with results and metadata
        """
        if mode == "smart":
            return await cls._smart_search(
                query=query,
                limit=limit,
                correct_spelling=correct_spelling,
                expand_acronyms=expand_acronyms,
                add_synonyms=add_synonyms,
                rerank=rerank,
                year_min=year_min,
                year_max=year_max,
            )
        elif mode == "keyword":
            return await cls._keyword_search(
                query=query,
                limit=limit,
                rerank=rerank,
                year_min=year_min,
                year_max=year_max,
            )
        elif mode == "semantic":
            return await cls._semantic_search(
                query=query,
                limit=limit,
                search_level=search_level,
                min_similarity=min_similarity,
                rerank=rerank,
            )
        elif mode == "hybrid":
            return await cls._hybrid_search(
                query=query,
                limit=limit,
                alpha=alpha,
                min_similarity=min_similarity,
                rerank=rerank,
                year_min=year_min,
                year_max=year_max,
            )
        elif mode == "exact":
            # Exact mode doesn't use re-ranking (it's for fast lookups)
            return await cls._exact_search(
                query=query,
                limit=limit,
                year_min=year_min,
                year_max=year_max,
            )
        else:
            raise ValueError(f"Unknown search mode: {mode}. Use 'smart', 'keyword', 'semantic', 'hybrid', or 'exact'")

    # =========================================================================
    # Re-ranking Helpers
    # =========================================================================

    @classmethod
    def _should_rerank(cls, rerank: bool | None) -> bool:
        """Determine if re-ranking should be applied.

        Args:
            rerank: Explicit override (None = use settings default)

        Returns:
            True if re-ranking should be applied
        """
        from config.ai_settings import settings

        if rerank is not None:
            return rerank
        return settings.reranker.enabled

    @classmethod
    def _apply_reranking(
        cls,
        query: str,
        results: list[dict],
        limit: int,
    ) -> list[dict]:
        """Apply cross-encoder re-ranking to results.

        Args:
            query: The search query
            results: List of result dicts
            limit: Maximum results to return

        Returns:
            Re-ranked results
        """
        try:
            from services.reranking_service import RerankerService

            if not RerankerService.is_available():
                logger.debug("Re-ranker not available, skipping")
                return results

            reranked = RerankerService.rerank(
                query=query,
                results=results,
                top_k=limit,
            )
            logger.debug(f"Re-ranked {len(results)} results -> {len(reranked)}")
            return reranked

        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}")
            return results

    @classmethod
    async def _smart_search(
        cls,
        query: str,
        limit: int,
        correct_spelling: bool,
        expand_acronyms: bool,
        add_synonyms: bool,
        rerank: bool | None,
        year_min: int | None,
        year_max: int | None,
    ) -> UnifiedSearchResults:
        """Smart search with query enhancement.

        Preprocesses the query (spell correction, acronym expansion, synonyms)
        then executes hybrid search with the expanded query.
        """
        # Step 1: Expand the query
        expansion = cls.expand_query(
            query=query,
            correct_spelling=correct_spelling,
            expand_acronyms=expand_acronyms,
            add_synonyms=add_synonyms,
        )

        # Step 2: Execute hybrid search with expanded query
        hybrid_result = await cls._hybrid_search(
            query=expansion.final_query,
            limit=limit,
            alpha=DEFAULT_ALPHA,
            min_similarity=DEFAULT_MIN_SIMILARITY,
            rerank=rerank,
            year_min=year_min,
            year_max=year_max,
        )

        return UnifiedSearchResults(
            query=query,
            mode="smart",
            results=hybrid_result.results,
            count=hybrid_result.count,
            search_type="smart",
            spell_corrected=expansion.spell_corrected,
            acronyms_expanded=expansion.acronyms_expanded,
            final_query=expansion.final_query,
            alpha=hybrid_result.alpha,
            keyword_results_count=hybrid_result.keyword_results_count,
            semantic_results_count=hybrid_result.semantic_results_count,
            strategies_used=hybrid_result.strategies_used,
            fallback_used=hybrid_result.fallback_used,
            fallback_reason=hybrid_result.fallback_reason,
        )

    @classmethod
    async def _keyword_search(
        cls,
        query: str,
        limit: int,
        rerank: bool | None,
        year_min: int | None,
        year_max: int | None,
    ) -> UnifiedSearchResults:
        """FTS5 keyword search."""
        from services.search_service import SearchService

        result = SearchService.keyword_search(
            query=query,
            limit=limit,
            year_min=year_min,
            year_max=year_max,
        )

        # Apply re-ranking if enabled
        results = result.results
        strategies = ["fts5_keyword"]
        if cls._should_rerank(rerank) and results:
            results = cls._apply_reranking(query, results, limit)
            strategies.append("reranked")

        return UnifiedSearchResults(
            query=query,
            mode="keyword",
            results=results,
            count=len(results),
            search_type=result.search_type,
            strategies_used=strategies,
        )

    @classmethod
    async def _semantic_search(
        cls,
        query: str,
        limit: int,
        search_level: str,
        min_similarity: float,
        rerank: bool | None,
    ) -> UnifiedSearchResults:
        """Semantic embedding search."""
        from services.search_service import SearchService

        result = await SearchService.semantic_search(
            query=query,
            limit=limit,
            min_similarity=min_similarity,
            search_level=search_level,
        )

        # Apply re-ranking if enabled
        results = result.results
        strategies = ["semantic"]
        if cls._should_rerank(rerank) and results:
            results = cls._apply_reranking(query, results, limit)
            strategies.append("reranked")

        return UnifiedSearchResults(
            query=query,
            mode="semantic",
            results=results,
            count=len(results),
            search_type=result.search_type,
            search_level=search_level,
            strategies_used=strategies,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
        )

    @classmethod
    async def _hybrid_search(
        cls,
        query: str,
        limit: int,
        alpha: float,
        min_similarity: float,
        rerank: bool | None,
        year_min: int | None,
        year_max: int | None,
    ) -> UnifiedSearchResults:
        """Hybrid keyword + semantic search using RRF fusion.

        Combines FTS5 keyword search (BM25) with semantic vector search
        using Reciprocal Rank Fusion for result merging.
        Optionally applies cross-encoder re-ranking for improved precision.
        """
        from services.search_service import SearchService
        from sqlalchemy.orm import joinedload
        from literature_core import get_session, Paper

        keyword_results: list[tuple[int, float]] = []  # (paper_id, score)
        semantic_results: list[tuple[int, float]] = []
        strategies = []
        fallback_used = False
        fallback_reason = None

        # Fetch more results than limit for better fusion
        fetch_limit = limit * 3

        # Step 1: FTS5 Keyword Search
        try:
            from literature_core.fts import search_fts, is_fts_available

            if is_fts_available():
                fts_results = search_fts(
                    query=query,
                    limit=fetch_limit,
                    year_min=year_min,
                    year_max=year_max,
                )
                keyword_results = [
                    (r.paper_id, r.bm25_score) for r in fts_results
                ]
                if keyword_results:
                    strategies.append("fts5_keyword")
                logger.debug(f"FTS5 returned {len(keyword_results)} results")
            else:
                # Fallback to SQL LIKE search
                with get_session() as session:
                    search_pattern = f"%{query}%"
                    db_query = session.query(Paper.id).filter(
                        (Paper.title.ilike(search_pattern))
                        | (Paper.abstract.ilike(search_pattern))
                    )
                    if year_min:
                        db_query = db_query.filter(Paper.year >= year_min)
                    if year_max:
                        db_query = db_query.filter(Paper.year <= year_max)
                    results = db_query.order_by(Paper.year.desc()).limit(fetch_limit).all()
                    keyword_results = [(r[0], 1.0) for r in results]

                if keyword_results:
                    strategies.append("keyword_fallback")
                fallback_used = True
                fallback_reason = "FTS5 not available"

        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")

        # Step 2: Semantic Search (if alpha > 0)
        if alpha > 0:
            try:
                from embeddings.generator import get_embedding_generator
                from embeddings.vectorstore import get_chunk_store, get_vector_store

                generator = get_embedding_generator()
                query_embedding = generator.generate(query)

                # Try chunk-level search first
                try:
                    chunk_store = get_chunk_store()
                    chunk_results = chunk_store.search_chunks(
                        query_embedding=query_embedding,
                        limit=fetch_limit,
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

                        semantic_results = sorted(
                            paper_scores.items(),
                            key=lambda x: x[1],
                            reverse=True
                        )[:fetch_limit]

                except Exception as chunk_error:
                    logger.debug(f"Chunk search failed, trying paper-level: {chunk_error}")

                    # Fallback to paper-level search
                    vector_store = get_vector_store()
                    paper_results = vector_store.search(
                        query_embedding=query_embedding,
                        top_k=fetch_limit,
                        score_threshold=min_similarity,
                    )
                    semantic_results = [
                        (int(r["id"]), r.get("score", 0.0))
                        for r in paper_results
                        if r.get("id")
                    ]

                if semantic_results:
                    strategies.append("semantic")
                logger.debug(f"Semantic search returned {len(semantic_results)} results")

            except Exception as e:
                logger.warning(f"Semantic search failed: {e}")

        # Step 3: Merge with RRF
        if keyword_results or semantic_results:
            merged_ids = SearchService.reciprocal_rank_fusion(
                ranked_lists=[keyword_results, semantic_results],
                weights=[1.0 - alpha, alpha],  # keyword weight, semantic weight
            )
            merged_ids = merged_ids[:limit]
        else:
            merged_ids = []

        # Step 4: Fetch full paper data
        paper_ids = [pid for pid, _ in merged_ids]
        score_map = {pid: score for pid, score in merged_ids}

        results = []
        if paper_ids:
            with get_session() as session:
                papers = (
                    session.query(Paper)
                    .options(joinedload(Paper.authors), joinedload(Paper.tags))
                    .filter(Paper.id.in_(paper_ids))
                    .all()
                )
                paper_map = {p.id: p for p in papers}

                # Build results in merged order
                for paper_id in paper_ids:
                    if paper_id in paper_map:
                        paper = paper_map[paper_id]
                        results.append(SearchService.paper_to_result(
                            paper,
                            score=score_map.get(paper_id)
                        ))

        # Step 5: Apply re-ranking if enabled
        if cls._should_rerank(rerank) and results:
            results = cls._apply_reranking(query, results, limit)
            strategies.append("reranked")

        logger.info(
            f"Hybrid search '{query}' returned {len(results)} results "
            f"(keyword={len(keyword_results)}, semantic={len(semantic_results)}, reranked={cls._should_rerank(rerank)})"
        )

        return UnifiedSearchResults(
            query=query,
            mode="hybrid",
            results=results,
            count=len(results),
            search_type="hybrid",
            alpha=alpha,
            keyword_results_count=len(keyword_results),
            semantic_results_count=len(semantic_results),
            strategies_used=strategies,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    @classmethod
    async def _exact_search(
        cls,
        query: str,
        limit: int,
        year_min: int | None,
        year_max: int | None,
    ) -> UnifiedSearchResults:
        """Exact search optimized for known paper lookups.

        Strategy:
        1. Try exact title match (case-insensitive)
        2. Try FTS5 phrase search (exact phrase in title or abstract)
        3. Fall back to keyword search with AND logic

        This mode skips semantic search entirely for speed.
        """
        from services.search_service import SearchService
        from literature_core import get_session, Paper
        from sqlalchemy.orm import joinedload

        strategies = []
        results = []

        # Step 1: Try exact title match (fastest for known papers)
        with get_session() as session:
            db_query = session.query(Paper).options(
                joinedload(Paper.authors),
                joinedload(Paper.tags)
            )

            # Case-insensitive exact title match
            db_query = db_query.filter(Paper.title.ilike(f"%{query}%"))

            if year_min:
                db_query = db_query.filter(Paper.year >= year_min)
            if year_max:
                db_query = db_query.filter(Paper.year <= year_max)

            papers = db_query.order_by(Paper.year.desc()).limit(limit).all()

            if papers:
                strategies.append("exact_title_match")
                # Score: prioritize exact matches, then contains
                for i, paper in enumerate(papers):
                    # Boost score if title starts with query or is exact match
                    title_lower = paper.title.lower() if paper.title else ""
                    query_lower = query.lower()
                    if title_lower == query_lower:
                        score = 1.0
                    elif title_lower.startswith(query_lower):
                        score = 0.95
                    else:
                        score = 0.9 - (i * 0.01)  # Slightly decrease for order

                    results.append(SearchService.paper_to_result(paper, score=score))

        # Step 2: If no results, try FTS5 phrase search
        if not results:
            try:
                from literature_core.fts import search_fts_phrase, is_fts_available

                if is_fts_available():
                    fts_results = search_fts_phrase(
                        phrase=query,
                        limit=limit,
                    )

                    if fts_results:
                        strategies.append("fts5_phrase")
                        paper_ids = [r.paper_id for r in fts_results]
                        score_map = {r.paper_id: r.bm25_score for r in fts_results}

                        with get_session() as session:
                            papers = (
                                session.query(Paper)
                                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                                .filter(Paper.id.in_(paper_ids))
                                .all()
                            )
                            paper_map = {p.id: p for p in papers}

                            for paper_id in paper_ids:
                                if paper_id in paper_map:
                                    results.append(SearchService.paper_to_result(
                                        paper_map[paper_id],
                                        score=score_map.get(paper_id)
                                    ))

            except Exception as e:
                logger.warning(f"FTS5 phrase search failed: {e}")

        # Step 3: If still no results, fall back to keyword search with AND logic
        if not results:
            try:
                from literature_core.fts import search_fts, is_fts_available

                if is_fts_available():
                    # Use AND logic for multi-word queries (more precise)
                    words = query.split()
                    if len(words) > 1:
                        and_query = " AND ".join(words)
                    else:
                        and_query = query

                    fts_results = search_fts(
                        query=and_query,
                        limit=limit,
                        year_min=year_min,
                        year_max=year_max,
                        use_or_for_multiword=False,  # Force AND logic
                    )

                    if fts_results:
                        strategies.append("fts5_keyword_and")
                        paper_ids = [r.paper_id for r in fts_results]
                        score_map = {r.paper_id: r.bm25_score for r in fts_results}

                        with get_session() as session:
                            papers = (
                                session.query(Paper)
                                .options(joinedload(Paper.authors), joinedload(Paper.tags))
                                .filter(Paper.id.in_(paper_ids))
                                .all()
                            )
                            paper_map = {p.id: p for p in papers}

                            for paper_id in paper_ids:
                                if paper_id in paper_map:
                                    results.append(SearchService.paper_to_result(
                                        paper_map[paper_id],
                                        score=score_map.get(paper_id)
                                    ))

            except Exception as e:
                logger.warning(f"FTS5 AND search failed: {e}")

        logger.info(
            f"Exact search '{query}' returned {len(results)} results "
            f"(strategies: {strategies})"
        )

        return UnifiedSearchResults(
            query=query,
            mode="exact",
            results=results,
            count=len(results),
            search_type="exact",
            strategies_used=strategies,
        )


# Convenience function
async def search(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    mode: SearchMode = "smart",
    **kwargs,
) -> UnifiedSearchResults:
    """Convenience function for unified search."""
    return await UnifiedSearchService.search(query, limit=limit, mode=mode, **kwargs)
