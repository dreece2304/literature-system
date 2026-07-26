"""Tests for grounding-quote requirements in extraction prompts."""
from __future__ import annotations

from services.extraction_prompts import (
    get_chunk_extraction_prompt,
    get_consolidation_prompt,
)


class TestGroundedPrompts:
    def test_chunk_prompt_requires_quotes(self):
        p = get_chunk_extraction_prompt(title="T", chunk_text="text", chunk_number=1, total_chunks=2)
        assert "quote" in p.lower()
        assert "verbatim" in p.lower()
        assert "defined_terms" in p

    def test_consolidation_prompt_preserves_quotes(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[{"key_findings": []}])
        assert "quote" in p.lower()

    def test_consolidation_corrections_section(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[], corrections="number 99.9 unmatched")
        assert "CORRECTIONS" in p and "99.9" in p

    def test_no_corrections_no_section(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[])
        assert "CORRECTIONS" not in p
