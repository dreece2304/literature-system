"""Tests for Tier 0 numeric fidelity (normalization + source alignment)."""
from __future__ import annotations

from services.verification_service import VerificationService

SOURCE = "Conversion reached 87.5% after 2h. The film thickness was 1,250 nm (1.25e3 nm nominal)."


class TestCheckNumbers:
    def test_plain_and_percent(self):
        checks = VerificationService.check_numbers("conversion of 87.5%", SOURCE)
        assert len(checks) == 1 and checks[0].matched

    def test_thousands_separator_normalized(self):
        checks = VerificationService.check_numbers("thickness of 1250 nm", SOURCE)
        assert checks[0].matched  # 1250 matches "1,250"

    def test_scientific_notation_normalized(self):
        checks = VerificationService.check_numbers("nominal 1.25e3 nm", SOURCE)
        assert checks[0].matched

    def test_hallucinated_number_flagged(self):
        checks = VerificationService.check_numbers("yield of 99.9%", SOURCE)
        assert not checks[0].matched

    def test_fidelity_score(self):
        checks = VerificationService.check_numbers("87.5% and 99.9%", SOURCE)
        assert VerificationService.numeric_fidelity(checks) == 0.5

    def test_fidelity_no_numbers_is_one(self):
        assert VerificationService.numeric_fidelity([]) == 1.0
