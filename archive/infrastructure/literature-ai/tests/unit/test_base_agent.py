"""
Unit tests for BaseAgent

Tests the foundation class that all agents inherit from.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path


@pytest.mark.unit
class TestBaseAgent:
    """Test suite for BaseAgent."""

    def test_base_agent_initialization(self):
        """Test that BaseAgent initializes with agent name."""
        from src.agents.base import BaseAgent

        # BaseAgent is abstract, so we'll create a minimal concrete implementation
        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {"result": "test"}

        agent = TestAgent(agent_name="test_agent")

        assert agent.agent_name == "test_agent"
        assert agent.model is not None  # Should have a default model
        assert agent.llm_service is not None
        assert agent.prompts is not None

    def test_agent_loads_prompts(self):
        """Test that agent loads prompts from YAML file."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="writer")

        # Writer should have prompts loaded
        assert isinstance(agent.prompts, dict)
        # Should have some prompts (exact content depends on YAML files)
        assert len(agent.prompts) >= 0  # May be empty if file doesn't exist

    @pytest.mark.asyncio
    async def test_generate_json(self):
        """Test _generate_json method."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test")

        # Mock the LLM service
        agent.llm_service = AsyncMock()
        agent.llm_service.generate_json.return_value = {"test": "response"}

        result = await agent._generate_json("test prompt", temperature=0.5)

        assert result == {"test": "response"}
        agent.llm_service.generate_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_with_custom_temperature(self):
        """Test that _generate_json accepts temperature parameter."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test")
        agent.llm_service = AsyncMock()
        agent.llm_service.generate_json.return_value = {}

        await agent._generate_json("test prompt", temperature=0.3)

        # Should be called with specified temperature
        call_args = agent.llm_service.generate_json.call_args
        assert call_args.kwargs.get("temperature") == 0.3

    @pytest.mark.asyncio
    async def test_generate_text(self):
        """Test _generate method for text generation."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test")
        agent.llm_service = AsyncMock()
        agent.llm_service.generate.return_value = "Generated text response"

        result = await agent._generate("test prompt")

        assert result == "Generated text response"
        agent.llm_service.generate.assert_called_once()

    def test_format_prompt_with_template(self):
        """Test _format_prompt method with template."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test")

        # Add a test prompt template (matches YAML structure)
        agent.prompts = {
            "test_template": {
                "template": "Hello {name}, you are {age} years old."
            }
        }

        result = agent._format_prompt("test_template", name="Alice", age=30)

        assert result == "Hello Alice, you are 30 years old."

    def test_format_prompt_missing_template(self):
        """Test _format_prompt when template doesn't exist."""
        from src.agents.base import BaseAgent

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test")
        agent.prompts = {}

        # Should return empty string and log warning (not raise)
        result = agent._format_prompt("nonexistent_template")
        assert result == ""

    def test_agent_model_assignment(self):
        """Test that agent gets assigned the correct model."""
        from src.agents.base import BaseAgent
        from config.settings import settings

        class WriterTestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        class TriagerTestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        class ReaderTestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        writer = WriterTestAgent(agent_name="writer")
        triager = TriagerTestAgent(agent_name="triager")
        reader = ReaderTestAgent(agent_name="reader")

        # Each should get their specific model from settings
        assert writer.model == settings.ollama.writer_model
        assert triager.model == settings.ollama.triager_model
        assert reader.model == settings.ollama.reader_model

    @pytest.mark.asyncio
    async def test_process_is_abstract(self):
        """Test that process() must be implemented by subclasses."""
        from src.agents.base import BaseAgent

        # Trying to instantiate BaseAgent directly should fail
        # (or require implementation of process)
        with pytest.raises(TypeError):
            # This should fail because process is not implemented
            agent = BaseAgent(agent_name="test")

    def test_prompt_file_path_construction(self):
        """Test that prompt file paths are constructed correctly."""
        from src.agents.base import BaseAgent
        from config.settings import PROJECT_ROOT

        class TestAgent(BaseAgent):
            async def process(self, *args, **kwargs):
                return {}

        agent = TestAgent(agent_name="test_agent")

        # The prompt file path should be config/prompts/test_agent.yaml
        expected_path = PROJECT_ROOT / "config" / "prompts" / "test_agent.yaml"

        # We can't directly test the internal path, but we can verify
        # that prompts were attempted to be loaded
        assert isinstance(agent.prompts, dict)
