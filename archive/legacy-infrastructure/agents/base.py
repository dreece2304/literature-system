"""
Base agent class for all LLM-powered agents.

Provides common functionality like prompt loading, LLM interaction,
and result formatting.
"""

import yaml
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from loguru import logger

from config.settings import settings, PROJECT_ROOT
from src.services.llm_service import get_llm_service


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Provides:
    - Prompt template loading
    - LLM service access
    - Common configuration
    - Result formatting
    """

    def __init__(self, agent_name: str):
        """
        Initialize base agent.

        Args:
            agent_name: Name of the agent (writer, triager, reader)
        """
        self.agent_name = agent_name
        self.llm_service = get_llm_service()

        # Load prompts
        self.prompts = self._load_prompts()

        # Get agent-specific model
        self.model = self._get_model()

        logger.info(f"{self.__class__.__name__} initialized with model {self.model}")

    def _load_prompts(self) -> Dict[str, Any]:
        """
        Load prompt templates for this agent.

        Returns:
            Prompts dictionary
        """
        prompt_file = PROJECT_ROOT / "config" / "prompts" / f"{self.agent_name}.yaml"

        if not prompt_file.exists():
            logger.warning(f"Prompt file not found: {prompt_file}")
            return {}

        try:
            with open(prompt_file, "r") as f:
                prompts = yaml.safe_load(f)
                logger.debug(f"Loaded prompts from {prompt_file}")
                return prompts
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            return {}

    def _get_model(self) -> str:
        """
        Get the model name for this agent.

        Returns:
            Model name
        """
        # Map agent names to model settings
        model_map = {
            "writer": settings.ollama.writer_model,
            "triager": settings.ollama.triager_model,
            "reader": settings.ollama.reader_model,
        }

        return model_map.get(self.agent_name, settings.ollama.writer_model)

    def _format_prompt(self, template_name: str, **kwargs) -> str:
        """
        Format a prompt template with variables.

        Args:
            template_name: Name of template in prompts dict
            **kwargs: Variables to substitute

        Returns:
            Formatted prompt string
        """
        template_data = self.prompts.get(template_name, {})

        if not template_data:
            logger.warning(f"Template not found: {template_name}")
            return ""

        template = template_data.get("template", "")

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return template

    def _get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent.

        Returns:
            System prompt string
        """
        return self.prompts.get("system_prompt", "")

    async def _generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate response from LLM.

        Args:
            prompt: User prompt
            system: System prompt (uses default if None)
            temperature: Sampling temperature
            format: Output format ("json" for structured output)

        Returns:
            LLM response dictionary
        """
        system = system or self._get_system_prompt()

        return await self.llm_service.generate(
            prompt=prompt,
            model=self.model,
            system=system,
            temperature=temperature,
            format=format,
        )

    async def _generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Generate JSON response from LLM.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Sampling temperature

        Returns:
            Parsed JSON response
        """
        system = system or self._get_system_prompt()

        return await self.llm_service.generate_json(
            prompt=prompt,
            model=self.model,
            system=system,
            temperature=temperature,
        )

    @abstractmethod
    async def process(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Main processing method for the agent.

        Must be implemented by subclasses.

        Returns:
            Agent response dictionary
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """
        Get agent information.

        Returns:
            Info dictionary
        """
        return {
            "agent_name": self.agent_name,
            "agent_type": self.__class__.__name__,
            "model": self.model,
            "prompts_loaded": len(self.prompts),
        }
