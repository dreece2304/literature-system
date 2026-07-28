"""Tests for Tier 0 quote matching (exact -> numeric -> fuzzy -> paraphrase)."""
from __future__ import annotations

from services.verification_service import MiniCheckClient, VerificationService

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

    def test_paraphrase_fallback_accepts_reworded_quote(self):
        # 9B models reword "quotes"; content words still map to the source.
        m = VerificationService.match_quote(
            "modified films with zinc incorporation confirmed", SOURCE)
        assert m.found and m.method == "paraphrase"

    def test_hyphenation_and_quote_marks_normalized(self):
        # Model wraps in literal quotes and mangles hyphens vs the PDF source.
        src = "The metalorganic precursor reacted with the precursor-polymer system."
        m = VerificationService.match_quote(
            '"the metal-organic precursor reacted with the precursorpolymer system"', src)
        assert m.found

    def test_paraphrase_does_not_accept_fabrication(self):
        # Unrelated content words -> still rejected even with the fallback.
        m = VerificationService.match_quote(
            "the catalyst degraded rapidly under thermal cycling stress", SOURCE)
        assert not m.found


class TestBuildDocument:
    def test_concatenates_chunks_for_whole_paper_check(self):
        doc = VerificationService._build_document(["alpha beta", "gamma delta"])
        assert "alpha" in doc and "gamma" in doc

    def test_respects_char_budget(self):
        from services.verification_service import VERIFIER_DOC_CHAR_BUDGET
        huge = ["x" * 60000, "y" * 60000, "z" * 60000]
        doc = VerificationService._build_document(huge)
        assert len(doc) <= VERIFIER_DOC_CHAR_BUDGET

    def test_claim_support_checks_against_full_document(self):
        # The document handed to the verifier must contain ALL chunks, so a
        # synthesized claim spanning chunks can be supported.
        class Recorder(MiniCheckClient):
            def __init__(self):
                self.docs = []

            def check_claim(self, claim, document):
                self.docs.append(document)
                return True

        rec = Recorder()
        frac, _ = VerificationService.claim_support(
            ["synthesized claim"], ["intro chunk", "results chunk"], rec)
        assert frac == 1.0
        assert "intro chunk" in rec.docs[0] and "results chunk" in rec.docs[0]
