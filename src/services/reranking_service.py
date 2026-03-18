"""Re-ranking Service - Cross-encoder re-ranking for search results.

Uses a cross-encoder model to re-rank search results by scoring each
(query, document) pair directly. This improves precision over bi-encoder
embeddings alone.

Usage:
    from services.reranking_service import RerankerService

    # Re-rank search results
    reranked = RerankerService.rerank(
        query="ALD thin films",
        results=[{"id": 1, "title": "...", "abstract": "..."}, ...],
        top_k=20
    )

    # Check if re-ranking is available
    if RerankerService.is_available():
        results = RerankerService.rerank(query, results)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from config.ai_settings import settings

logger = logging.getLogger(__name__)

# Lazy-loaded model
_reranker_model = None
_model_load_attempted = False


@dataclass
class RerankedResult:
    """Result with re-ranking score."""
    original_result: dict
    rerank_score: float
    original_rank: int


class RerankerService:
    """Cross-encoder re-ranking service."""

    @classmethod
    def is_available(cls) -> bool:
        """Check if re-ranking is enabled and model is available."""
        if not settings.reranker.enabled:
            return False

        try:
            cls._get_model()
            return True
        except Exception:
            return False

    @classmethod
    def _get_model(cls):
        """Get or load the cross-encoder model (lazy initialization)."""
        global _reranker_model, _model_load_attempted

        if _reranker_model is not None:
            return _reranker_model

        if _model_load_attempted:
            raise RuntimeError("Re-ranker model failed to load previously")

        _model_load_attempted = True

        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading re-ranker model: {settings.reranker.model_name}")
            _reranker_model = CrossEncoder(
                settings.reranker.model_name,
                max_length=512,
                device=settings.reranker.device,
            )
            logger.info("Re-ranker model loaded successfully")
            return _reranker_model

        except ImportError:
            logger.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Failed to load re-ranker model: {e}")
            raise

    @classmethod
    def rerank(
        cls,
        query: str,
        results: list[dict],
        top_k: int | None = None,
        text_fields: list[str] | None = None,
    ) -> list[dict]:
        """Re-rank search results using cross-encoder.

        Args:
            query: The search query
            results: List of result dicts (must have text content)
            top_k: Number of results to return (default: settings.reranker.top_k_results)
            text_fields: Fields to use for document text (default: ["title", "abstract"])

        Returns:
            Re-ranked results with added "rerank_score" field
        """
        if not results:
            return results

        if not settings.reranker.enabled:
            logger.debug("Re-ranking disabled, returning original results")
            return results

        top_k = top_k or settings.reranker.top_k_results
        text_fields = text_fields or ["title", "abstract"]

        try:
            model = cls._get_model()
        except Exception as e:
            logger.warning(f"Re-ranker not available, returning original results: {e}")
            return results

        # Build (query, document) pairs
        pairs = []
        for result in results:
            # Combine text fields
            doc_parts = []
            for field in text_fields:
                if field in result and result[field]:
                    doc_parts.append(str(result[field]))
            doc_text = "\n\n".join(doc_parts)

            if doc_text:
                pairs.append((query, doc_text))
            else:
                # No text to re-rank, use empty string (will get low score)
                pairs.append((query, ""))

        # Score all pairs
        try:
            scores = model.predict(pairs)
        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            return results

        # Combine results with scores
        scored_results = []
        for i, (result, score) in enumerate(zip(results, scores)):
            result_copy = result.copy()
            result_copy["rerank_score"] = float(score)
            result_copy["original_rank"] = i + 1
            scored_results.append(result_copy)

        # Sort by re-rank score (higher is better)
        scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Return top_k
        return scored_results[:top_k]

    @classmethod
    def rerank_with_details(
        cls,
        query: str,
        results: list[dict],
        top_k: int | None = None,
    ) -> tuple[list[dict], dict[str, Any]]:
        """Re-rank with additional metadata about the re-ranking.

        Returns:
            Tuple of (reranked_results, metadata)
        """
        if not results:
            return results, {"reranked": False, "reason": "no_results"}

        if not settings.reranker.enabled:
            return results, {"reranked": False, "reason": "disabled"}

        top_k = top_k or settings.reranker.top_k_results
        original_count = len(results)

        try:
            reranked = cls.rerank(query, results, top_k=top_k)

            # Calculate rank changes
            rank_changes = []
            for new_rank, result in enumerate(reranked, 1):
                old_rank = result.get("original_rank", new_rank)
                change = old_rank - new_rank
                rank_changes.append(change)

            metadata = {
                "reranked": True,
                "model": settings.reranker.model_name,
                "input_count": original_count,
                "output_count": len(reranked),
                "avg_rank_change": sum(rank_changes) / len(rank_changes) if rank_changes else 0,
                "max_promotion": max(rank_changes) if rank_changes else 0,
                "max_demotion": min(rank_changes) if rank_changes else 0,
            }

            return reranked, metadata

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            return results, {"reranked": False, "reason": str(e)}

    @classmethod
    def get_status(cls) -> dict[str, Any]:
        """Get re-ranker status and configuration."""
        status = {
            "enabled": settings.reranker.enabled,
            "model_name": settings.reranker.model_name,
            "device": settings.reranker.device,
            "top_k_candidates": settings.reranker.top_k_candidates,
            "top_k_results": settings.reranker.top_k_results,
            "model_loaded": _reranker_model is not None,
        }

        if settings.reranker.enabled and _reranker_model is None:
            # Try to check if model can be loaded
            try:
                from sentence_transformers import CrossEncoder  # noqa: F401
                status["model_available"] = True
            except ImportError:
                status["model_available"] = False
                status["error"] = "sentence-transformers not installed"

        return status


# Convenience function
def rerank(query: str, results: list[dict], top_k: int | None = None) -> list[dict]:
    """Re-rank search results."""
    return RerankerService.rerank(query, results, top_k=top_k)
