"""Tests for ChunkProcessingState forward context (facts only) and checkpoints."""
from __future__ import annotations

from literature_core import get_session
from literature_core.models import ExtractionMetadata, Paper
from services.extraction_service import ChunkProcessingState


class TestForwardContext:
    def test_glossary_accumulates_from_chunk(self):
        state = ChunkProcessingState(paper_id=1)
        state.update_from_chunk({"defined_terms": {"DEZ": "diethylzinc"},
                                 "sections_in_chunk": ["Introduction"],
                                 "key_findings": [{"finding": "X", "quote": "X"}]})
        assert state.glossary == {"DEZ": "diethylzinc"}
        assert "Introduction" in state.sections_seen
        assert state.chunks_processed == 1

    def test_prompt_context_contains_facts_never_findings(self):
        state = ChunkProcessingState(paper_id=1)
        state.update_from_chunk({"defined_terms": {"DEZ": "diethylzinc"},
                                 "key_findings": [{"finding": "SECRET FINDING", "quote": "q"}]})
        ctx = state.to_prompt_context()
        assert "DEZ" in ctx and "diethylzinc" in ctx
        assert "SECRET FINDING" not in ctx  # findings are never forwarded


class TestCheckpoints:
    def test_save_and_load_roundtrip(self, db):
        with get_session() as s:
            p = Paper(title="T")
            s.add(p)
            s.flush()
            s.add(ExtractionMetadata(paper_id=p.id, extraction_method="test"))
            s.commit()
            pid = p.id
        state = ChunkProcessingState(paper_id=pid, chunks_processed=2,
                                     glossary={"ALD": "atomic layer deposition"})
        state.save_checkpoint()
        loaded = ChunkProcessingState.load_checkpoint(pid)
        assert loaded is not None
        assert loaded.chunks_processed == 2 and loaded.glossary["ALD"] == "atomic layer deposition"

    def test_load_missing_returns_none(self, db):
        assert ChunkProcessingState.load_checkpoint(999999) is None
