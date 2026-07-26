"""Tests for AI settings defaults (enrichment pipeline models)."""
from __future__ import annotations

from config.ai_settings import OllamaSettings


class TestOllamaModelDefaults:
    def test_extractor_models_updated(self):
        s = OllamaSettings()
        assert s.deep_extractor_model == "qwen3.5:9b"
        assert s.quick_extractor_model == "qwen3:4b-instruct-2507-q4_K_M"
        assert s.reader_model == "qwen3.5:9b"

    def test_new_pipeline_models(self):
        s = OllamaSettings()
        assert s.verifier_model == "bespoke-minicheck:7b"
        assert s.judge_model == "llama3.1:8b"
        assert s.vision_model == "qwen3.5:9b"

    def test_context_windows(self):
        s = OllamaSettings()
        assert s.chunk_num_ctx == 16384
        assert s.consolidation_num_ctx == 32768
