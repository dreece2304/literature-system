# tests/unit/services/test_extract_and_verify.py
"""Tests for the auto re-extract-once loop (mocked extractor + verifier)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.verification_service import VerificationService


@pytest.mark.asyncio
class TestExtractAndVerify:
    async def test_accept_first_pass_no_retry(self):
        extractor = AsyncMock(return_value={"success": True})
        with patch.object(VerificationService, "verify_paper",
                          return_value={"score": 0.9, "routing": "accept", "failures": []}) as vp:
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["attempts"] == 1 and result["routing"] == "accept"
        extractor.assert_awaited_once()
        assert vp.call_count == 1

    async def test_borderline_retries_once_with_corrections(self):
        extractor = AsyncMock(return_value={"success": True})
        verdicts = [{"score": 0.7, "routing": "reextract", "failures": ["number unmatched: 99.9"]},
                    {"score": 0.88, "routing": "accept", "failures": []}]
        with patch.object(VerificationService, "verify_paper", side_effect=verdicts):
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["attempts"] == 2 and result["routing"] == "accept"
        assert extractor.await_count == 2
        # second extraction got the failure feedback
        assert "99.9" in extractor.await_args_list[1].kwargs["corrections"]

    async def test_still_bad_after_retry_goes_review(self):
        extractor = AsyncMock(return_value={"success": True})
        verdicts = [{"score": 0.7, "routing": "reextract", "failures": ["f"]},
                    {"score": 0.65, "routing": "review", "failures": ["f"]}]
        with patch.object(VerificationService, "verify_paper", side_effect=verdicts):
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["routing"] == "review" and result["attempts"] == 2

    async def test_failed_extraction_short_circuits(self):
        extractor = AsyncMock(return_value={"success": False, "error": "timeout"})
        result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["error"] == "timeout" and result["attempts"] == 1
