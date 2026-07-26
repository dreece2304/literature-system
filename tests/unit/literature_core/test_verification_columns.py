"""Tests for verification_score and extraction_checkpoint columns."""
from __future__ import annotations

from literature_core.models import ExtractionMetadata, PaperContent


class TestVerificationColumns:
    def test_paper_content_has_verification_score(self, db):
        content = PaperContent(paper_id=1, verification_score=0.87)
        assert content.verification_score == 0.87

    def test_extraction_metadata_has_checkpoint(self, db):
        meta = ExtractionMetadata(paper_id=1, extraction_checkpoint={"chunks_processed": 3})
        assert meta.extraction_checkpoint == {"chunks_processed": 3}
