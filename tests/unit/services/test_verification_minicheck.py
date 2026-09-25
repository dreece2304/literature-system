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
        support = VerificationService.claim_support(
            ["claim A", "claim B"], ["chunk one text", "chunk two text"], client)
        assert support.fraction == 0.5
        assert support.checked == 2 and support.unchecked == 0
        assert support.evidence[0]["supported"] is True
        assert support.evidence[1]["supported"] is False

    def test_claim_checked_against_best_chunks_first(self):
        client = FakeMiniCheck({"the zinc film grew fast": True})
        support = VerificationService.claim_support(
            ["the zinc film grew fast"],
            ["unrelated text about solvents", "zinc film growth was rapid"], client)
        assert support.fraction == 1.0
        # First document tried should be the token-overlap-ranked best chunk
        assert "zinc" in client.calls[0][1]

    def test_unreachable_verifier_is_not_scored_as_unsupported(self):
        """A None verdict means "could not check", NOT "claim is false".

        Scoring None as unsupported is what let an Ollama outage write
        plausible-looking low scores over 49 good extractions.
        """
        client = FakeMiniCheck({})  # returns None for everything
        support = VerificationService.claim_support(["c1"], ["chunk"], client)
        assert support.checked == 0 and support.unchecked == 1
        assert support.verifier_down is True
        assert support.evidence[0]["supported"] is None

    def test_partial_failure_scores_only_checked_claims(self):
        client = FakeMiniCheck({"c1": True, "c2": False})  # c3 -> None
        support = VerificationService.claim_support(["c1", "c2", "c3"], ["chunk"], client)
        assert support.checked == 2 and support.unchecked == 1
        assert support.fraction == 0.5          # 1 of 2 checked, c3 excluded
        assert support.verifier_down is False

    def test_no_claims_is_full_support(self):
        client = FakeMiniCheck({})
        support = VerificationService.claim_support([], ["chunk"], client)
        assert support.fraction == 1.0 and support.evidence == []
        assert support.verifier_down is False   # nothing to check != verifier down


class TestWindowedChecking:
    """A claim is checked against VRAM-sized windows, best match first."""

    def test_supported_by_a_later_window_still_counts(self):
        from services.verification_service import VERIFIER_WINDOW_CHARS

        # Only the tail of the paper mentions zinc; the claim must still pass.
        chunks = ["filler about solvents. " * 2000, "the zinc film grew rapidly"]
        assert len("".join(chunks)) > VERIFIER_WINDOW_CHARS

        class OnlyZinc(MiniCheckClient):
            def __init__(self):
                self.calls = []

            def check_claim(self, claim, document):
                self.calls.append(document)
                return "zinc" in document

        client = OnlyZinc()
        support = VerificationService.claim_support(
            ["the zinc film grew rapidly"], chunks, client)
        assert support.fraction == 1.0 and support.checked == 1

    def test_stops_at_the_first_supporting_window(self):
        chunks = ["zinc film growth was rapid. " * 3000]

        class AlwaysYes(MiniCheckClient):
            def __init__(self):
                self.calls = []

            def check_claim(self, claim, document):
                self.calls.append(document)
                return True

        client = AlwaysYes()
        VerificationService.claim_support(["zinc film growth"], chunks, client)
        assert len(client.calls) == 1, "should not sweep windows once supported"

    def test_all_windows_unanswerable_is_unchecked_not_unsupported(self):
        chunks = ["some long paper text. " * 3000]
        client = FakeMiniCheck({})  # every window returns None
        support = VerificationService.claim_support(["a claim"], chunks, client)
        assert support.verifier_down is True and support.checked == 0


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
