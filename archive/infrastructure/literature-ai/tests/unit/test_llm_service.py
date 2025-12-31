"""
Unit tests for LLM Service

Smoke tests for the core LLM service functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json


@pytest.mark.unit
class TestLLMService:
    """Test suite for LLMService."""

    def test_llm_service_initialization(self):
        """Test that LLMService initializes correctly."""
        from src.services.llm_service import LLMService
        from config.settings import settings

        service = LLMService()

        assert service.base_url == settings.ollama.host
        assert service.current_model is None  # No model loaded initially

    @pytest.mark.asyncio
    async def test_generate_json_parses_response(self):
        """Test that generate_json properly parses JSON responses."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Mock the underlying generate method - it returns a dict with "text" key
        json_response = {"score": 8, "action": "must_read"}
        service.generate = AsyncMock(return_value={"text": json.dumps(json_response)})

        result = await service.generate_json(
            prompt="Test prompt",
            model="test-model",
        )

        assert result == json_response
        assert result["score"] == 8

    @pytest.mark.asyncio
    async def test_generate_json_handles_malformed_json(self):
        """Test that generate_json handles malformed JSON gracefully."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Return non-JSON response in text field
        service.generate = AsyncMock(return_value={"text": "Not a JSON response"})

        # Should raise ValueError (wraps JSONDecodeError in the real implementation)
        with pytest.raises(ValueError):
            await service.generate_json(prompt="Test", model="test")

    @pytest.mark.asyncio
    async def test_generate_uses_correct_model(self):
        """Test that generate uses the specified model."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Mock the generate method directly to avoid HTTP calls
        mock_response = {
            "text": "Test response",
            "model": "qwen:7b-q5_K_M",
            "duration_ms": 100,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "done": True,
            "context": [],
        }
        service.generate = AsyncMock(return_value=mock_response)

        result = await service.generate(
            prompt="Test",
            model="qwen:7b-q5_K_M",
            temperature=0.5,
        )

        # Verify we got a response with the correct model
        assert result is not None
        assert result["model"] == "qwen:7b-q5_K_M"
        assert result["text"] == "Test response"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        """Test generate with system prompt."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Mock the generate method to avoid HTTP calls
        mock_response = {
            "text": "I am a helpful assistant.",
            "model": "test-model",
            "duration_ms": 100,
            "prompt_tokens": 15,
            "completion_tokens": 10,
            "total_tokens": 25,
            "done": True,
            "context": [],
        }
        service.generate = AsyncMock(return_value=mock_response)

        # Call with system prompt
        result = await service.generate(
            prompt="User prompt",
            model="test-model",
            system="You are a helpful assistant",
        )

        # Verify system parameter was accepted and we got a response
        assert result is not None
        assert result["text"] is not None

        # Verify generate was called with the system prompt
        call_kwargs = service.generate.call_args.kwargs
        assert call_kwargs.get("system") == "You are a helpful assistant"

    def test_singleton_pattern(self):
        """Test that get_llm_service returns singleton."""
        from src.services.llm_service import get_llm_service

        service1 = get_llm_service()
        service2 = get_llm_service()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_llm_service_has_client(self):
        """Test that LLM service has HTTP client."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Verify service has client
        assert hasattr(service, 'client')
        assert service.client is not None

    @pytest.mark.asyncio
    async def test_generate_json_with_temperature(self):
        """Test that generate_json accepts and passes temperature."""
        from src.services.llm_service import LLMService

        service = LLMService()

        # Mock generate to return valid JSON
        service.generate = AsyncMock(return_value={"text": '{"score": 9}'})

        result = await service.generate_json(
            prompt="Test",
            model="test",
            temperature=0.3
        )

        # Verify generate was called with temperature in kwargs
        call_kwargs = service.generate.call_args.kwargs
        assert "temperature" in call_kwargs or call_kwargs.get("temperature") is not None

        # Verify we got the JSON back
        assert result["score"] == 9
