"""
Claude API service for content extraction.

Provides a high-level interface for generating structured extractions
from papers using Claude.
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime

import httpx
from loguru import logger

from config.settings import settings


class ClaudeService:
    """
    Service for interacting with Anthropic Claude API.

    Features:
    - Structured JSON extraction
    - Error handling and retries
    - Token tracking
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        Initialize Claude service.

        Args:
            api_key: Anthropic API key (default: from settings)
            model: Model name (default: from settings)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or settings.claude.api_key
        self.model = model or settings.claude.model
        self.timeout = timeout
        self.base_url = "https://api.anthropic.com/v1"

        if not self.api_key:
            logger.warning("Claude API key not configured - extraction will fail")

        # HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        logger.info(f"ClaudeService initialized with model {self.model}")

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Response dictionary with 'text', 'model', 'usage', etc.
        """
        if not self.api_key:
            raise ValueError("Claude API key not configured")

        # Build request
        request_data = {
            "model": self.model,
            "max_tokens": max_tokens or settings.claude.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system:
            request_data["system"] = system

        if temperature is not None:
            request_data["temperature"] = temperature
        else:
            request_data["temperature"] = settings.claude.temperature

        # Make request
        try:
            start_time = datetime.utcnow()

            response = await self.client.post("/messages", json=request_data)
            response.raise_for_status()
            result = response.json()

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Parse response
            text = ""
            if result.get("content"):
                for block in result["content"]:
                    if block.get("type") == "text":
                        text += block.get("text", "")

            parsed = {
                "text": text,
                "model": result.get("model", self.model),
                "duration_ms": duration_ms,
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
                "stop_reason": result.get("stop_reason"),
            }

            logger.info(
                f"Claude generation complete: model={self.model}, "
                f"input_tokens={parsed['input_tokens']}, "
                f"output_tokens={parsed['output_tokens']}, "
                f"duration={duration_ms:.0f}ms"
            )

            return parsed

        except httpx.HTTPStatusError as e:
            logger.error(f"Claude API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error during Claude generation: {e}")
            raise

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response from Claude.

        Args:
            prompt: User prompt (should request JSON output)
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Parsed JSON response
        """
        # Add JSON instruction to system prompt if not present
        if system and "JSON" not in system:
            system += "\n\nRespond with valid JSON only, no markdown or explanation."
        elif not system:
            system = "You are an expert assistant. Respond with valid JSON only, no markdown or explanation."

        response = await self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Parse JSON from text
        text = response["text"].strip()

        # Handle markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {text}")
            raise ValueError(f"Invalid JSON response: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Returns:
            Health status dictionary
        """
        health = {
            "status": "unknown",
            "api_key_configured": bool(self.api_key),
            "model": self.model,
        }

        if not self.api_key:
            health["status"] = "unconfigured"
            return health

        try:
            # Make a minimal request to check API is working
            response = await self.generate(
                prompt="Say 'ok' only.",
                max_tokens=10,
            )
            health["status"] = "healthy"
            health["test_response"] = response["text"][:50]

        except Exception as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)

        return health

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("ClaudeService closed")


# Global singleton instance
_claude_service: Optional[ClaudeService] = None


def get_claude_service() -> ClaudeService:
    """
    Get global ClaudeService instance (singleton).

    Returns:
        Shared ClaudeService instance
    """
    global _claude_service

    if _claude_service is None:
        _claude_service = ClaudeService()

    return _claude_service


async def reset_claude_service():
    """Reset global Claude service (useful for testing)."""
    global _claude_service
    if _claude_service:
        await _claude_service.close()
    _claude_service = None
