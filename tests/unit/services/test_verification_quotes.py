# tests/unit/services/test_verification_quotes.py
"""Tests for Tier 0 quote matching (exact -> numeric -> fuzzy)."""
from __future__ import annotations

from services.verification_service import VerificationService

SOURCE = (
    "The membrane exhibited a water flux of 42.7 L/m2/h at 5 bar. "
    "Contact angle decreased from 78.3 degrees to 45.1 degrees after coating. "
    "XPS confirmed zinc incorporation of 12.4 at.% in the modified films."
)


class TestMatchQuote:
    def test_exact_match(self):
        m = VerificationService.match_quote("water flux of 42.7 L/m2/h at 5 bar", SOURCE)
        assert m.found and m.method == "exact" and m.score == 1.0

    def test_numeric_match_survives_paraphrase(self):
        # Quote paraphrased but numbers preserved
        m = VerificationService.match_quote("flux was 42.7 at a pressure of 5 bar", SOURCE)
        assert m.found and m.method in ("numeric", "fuzzy")

    def test_fuzzy_match_minor_ocr_noise(self):
        m = VerificationService.match_quote("Contact angle decreased frorn 78.3 degrees to 45.1 degrees", SOURCE)
        assert m.found and m.score >= 0.85

    def test_fabricated_quote_rejected(self):
        m = VerificationService.match_quote("thermal stability improved by 300 percent", SOURCE)
        assert not m.found and m.method == "none"

    def test_empty_quote_rejected(self):
        m = VerificationService.match_quote("", SOURCE)
        assert not m.found
