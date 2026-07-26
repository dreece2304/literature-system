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
from dataclasses import dataclass
from difflib import SequenceMatcher

from literature_core import get_logger

logger = get_logger(__name__)

FUZZY_THRESHOLD = 0.85

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?")


@dataclass
class QuoteMatch:
    """Result of matching a grounding quote against source text."""
    found: bool
    method: str          # "exact" | "numeric" | "fuzzy" | "none"
    score: float         # 0-1 match quality
    excerpt: str = ""    # matched source window (for evidence)


@dataclass
class NumberCheck:
    """One extracted number checked against source."""
    value: str           # as written in the claim
    matched: bool
    context: str = ""    # source window around the match


class VerificationService:
    """Stateless verification of extractions against source text."""

    ACCEPT_THRESHOLD = 0.85
    RETRY_THRESHOLD = 0.60

    W_NUMERIC, W_CLAIMS, W_QUOTES, W_JUDGE = 0.45, 0.35, 0.10, 0.10

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
                              excerpt=s_norm[max(0, idx - 50):idx + len(q_norm) + 50])

        nums = cls._numbers_in(quote)
        if nums and all(re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", s_norm) for n in nums):
            m = re.search(rf"(?<![\d.]){re.escape(nums[0])}(?![\d.])", s_norm)
            first = m.start() if m else 0
            return QuoteMatch(found=True, method="numeric", score=0.9,
                              excerpt=s_norm[max(0, first - 100):first + 150])

        best, best_pos = 0.0, 0
        window = max(len(q_norm), 40)
        step = max(window // 4, 10)
        for pos in range(0, max(len(s_norm) - window // 2, 1), step):
            ratio = SequenceMatcher(None, q_norm, s_norm[pos:pos + window]).ratio()
            if ratio > best:
                best, best_pos = ratio, pos
        if best >= FUZZY_THRESHOLD:
            return QuoteMatch(found=True, method="fuzzy", score=round(best, 3),
                              excerpt=s_norm[best_pos:best_pos + window])
        return QuoteMatch(found=False, method="none", score=round(best, 3))

    @staticmethod
    def _canonical_number(token: str) -> float | None:
        try:
            return float(token.replace(",", ""))
        except ValueError:
            return None

    @classmethod
    def _source_number_set(cls, source: str) -> dict[float, str]:
        out: dict[float, str] = {}
        for m in NUM_RE.finditer(source):
            v = cls._canonical_number(m.group())
            if v is not None and v not in out:
                out[v] = source[max(0, m.start() - 60):m.end() + 60]
        return out

    @classmethod
    def check_numbers(cls, claim_text: str, source: str) -> list[NumberCheck]:
        """Every number in claim_text must exist in source (normalized compare)."""
        source_nums = cls._source_number_set(source)
        checks = []
        for m in NUM_RE.finditer(claim_text):
            v = cls._canonical_number(m.group())
            if v is None:
                continue
            ctx = source_nums.get(v, "")
            checks.append(NumberCheck(value=m.group(), matched=v in source_nums, context=ctx))
        return checks

    @staticmethod
    def numeric_fidelity(checks: list[NumberCheck]) -> float:
        if not checks:
            return 1.0
        return sum(1 for c in checks if c.matched) / len(checks)

    @classmethod
    def composite_score(cls, numeric: float, claim_support: float, quote_grounding: float,
                        judge_pass: float, hard_gate_failed: bool) -> float:
        if hard_gate_failed:
            return 0.0
        return round(cls.W_NUMERIC * numeric + cls.W_CLAIMS * claim_support
                     + cls.W_QUOTES * quote_grounding + cls.W_JUDGE * judge_pass, 3)

    @classmethod
    def route(cls, score: float, retried: bool) -> str:
        if score >= cls.ACCEPT_THRESHOLD:
            return "accept"
        if score >= cls.RETRY_THRESHOLD and not retried:
            return "reextract"
        return "review"
