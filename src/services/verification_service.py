# src/services/verification_service.py
"""Verification Service - scores LLM extractions against source text.

Tiered design (spec 2026-07-24): Tier 0 deterministic (quotes, numbers),
Tier 1 NLI claim support (bespoke-minicheck), Tier 2 cross-family judge for
borderline papers. Composite 0-1 score persisted to PaperContent.

Usage:
    from services.verification_service import VerificationService

    m = VerificationService.match_quote(quote, source_text)
    result = VerificationService.verify_paper(paper_id)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from literature_core import get_logger

logger = get_logger(__name__)

FUZZY_THRESHOLD = 0.85


@dataclass
class QuoteMatch:
    """Result of matching a grounding quote against source text."""
    found: bool
    method: str          # "exact" | "numeric" | "fuzzy" | "none"
    score: float         # 0-1 match quality
    excerpt: str = ""    # matched source window (for evidence)


class VerificationService:
    """Stateless verification of extractions against source text."""

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def _numbers_in(text: str) -> list[str]:
        return re.findall(r"\d+(?:[.,]\d+)?", text)

    @classmethod
    def match_quote(cls, quote: str, source: str) -> QuoteMatch:
        """Match a quote: exact substring -> all-numbers-present -> fuzzy window."""
        if not quote or not quote.strip():
            return QuoteMatch(found=False, method="none", score=0.0)
        q_norm, s_norm = cls._normalize(quote), cls._normalize(source)

        idx = s_norm.find(q_norm)
        if idx != -1:
            return QuoteMatch(found=True, method="exact", score=1.0,
                              excerpt=source[max(0, idx - 50):idx + len(quote) + 50])

        nums = cls._numbers_in(quote)
        if nums and all(n in s_norm for n in nums):
            first = s_norm.find(nums[0])
            return QuoteMatch(found=True, method="numeric", score=0.9,
                              excerpt=source[max(0, first - 100):first + 150])

        best, best_pos = 0.0, 0
        window = max(len(q_norm), 40)
        step = max(window // 4, 10)
        for pos in range(0, max(len(s_norm) - window // 2, 1), step):
            ratio = SequenceMatcher(None, q_norm, s_norm[pos:pos + window]).ratio()
            if ratio > best:
                best, best_pos = ratio, pos
        if best >= FUZZY_THRESHOLD:
            return QuoteMatch(found=True, method="fuzzy", score=round(best, 3),
                              excerpt=source[best_pos:best_pos + window])
        return QuoteMatch(found=False, method="none", score=round(best, 3))
