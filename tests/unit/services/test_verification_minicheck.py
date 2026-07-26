"""Tests for Tier 1 claim support via MiniCheck (mocked HTTP)."""
from __future__ import annotations

from unittest.mock import patch

from services.verification_service import MiniCheckClient, VerificationService


class FakeMiniCheck(MiniCheckClient):
    """Answers Yes iff the claim's first 5 words appear in the document."""
    def __init__(self, answers: dict[str, bool]):
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def check_claim(self, claim: str, document: str) -> bool | None:
        self.calls.append((claim, document))
        return self.answers.get(claim)


class TestClaimSupport:
    def test_supported_fraction(self):
        client = FakeMiniCheck({"claim A": True, "claim B": False})
        frac, evidence = VerificationService.claim_support(
            ["claim A", "claim B"], ["chunk one text", "chunk two text"], client)
        assert frac == 0.5
        assert evidence[0]["supported"] is True and evidence[1]["supported"] is False

    def test_claim_checked_against_best_chunks_first(self):
        client = FakeMiniCheck({"the zinc film grew fast": True})
        frac, _ = VerificationService.claim_support(
            ["the zinc film grew fast"],
            ["unrelated text about solvents", "zinc film growth was rapid"], client)
        assert frac == 1.0
        # First document tried should be the token-overlap-ranked best chunk
        assert "zinc" in client.calls[0][1]

    def test_failed_calls_dont_count_as_supported(self):
        client = FakeMiniCheck({})  # returns None for everything
        frac, evidence = VerificationService.claim_support(["c1"], ["chunk"], client)
        assert frac == 0.0 and evidence[0]["supported"] is None

    def test_no_claims_is_full_support(self):
        client = FakeMiniCheck({})
        frac, evidence = VerificationService.claim_support([], ["chunk"], client)
        assert frac == 1.0 and evidence == []


class TestMiniCheckClientParse:
    @patch("services.verification_service.MiniCheckClient._generate")
    def test_yes_parsed(self, mock_gen):
        mock_gen.return_value = "Yes"
        assert MiniCheckClient().check_claim("c", "d") is True

    @patch("services.verification_service.MiniCheckClient._generate")
    def test_no_parsed(self, mock_gen):
        mock_gen.return_value = "No, the document does not support this."
        assert MiniCheckClient().check_claim("c", "d") is False

    @patch("services.verification_service.MiniCheckClient._generate")
    def test_error_returns_none(self, mock_gen):
        mock_gen.return_value = None
        assert MiniCheckClient().check_claim("c", "d") is None
