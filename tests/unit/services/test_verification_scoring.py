"""Tests for composite verification score and routing policy."""
from __future__ import annotations

import pytest

from services.verification_service import VerificationService


class TestCompositeScore:
    def test_weights(self):
        s = VerificationService.composite_score(1.0, 1.0, 1.0, 1.0, hard_gate_failed=False)
        assert s == 1.0
        s = VerificationService.composite_score(1.0, 0.0, 0.0, 0.0, hard_gate_failed=False)
        assert s == pytest.approx(0.45)

    def test_hard_gate_zeroes(self):
        s = VerificationService.composite_score(1.0, 1.0, 1.0, 1.0, hard_gate_failed=True)
        assert s == 0.0


class TestRouting:
    def test_accept(self):
        assert VerificationService.route(0.9, retried=False) == "accept"

    def test_borderline_first_pass_reextracts(self):
        assert VerificationService.route(0.7, retried=False) == "reextract"

    def test_borderline_after_retry_reviews(self):
        assert VerificationService.route(0.7, retried=True) == "review"

    def test_low_always_reviews(self):
        assert VerificationService.route(0.3, retried=False) == "review"
