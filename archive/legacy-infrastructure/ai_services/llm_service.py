"""
LLM service for interacting with Ollama/Qwen models.

Provides a high-level interface for generating responses with automatic
model management, GPU memory tracking, and response caching.
"""

import json
from typing import Optional, Dict, Any, List, AsyncIterator, Literal
from datetime import datetime

import httpx
from loguru import logger

from config.settings import settings
from src.utils.gpu_manager import get_gpu_manager
from src.utils.cache import get_cache_manager


class LLMService:
    """
    Service for interacting with Ollama LLM API.

    Features:
    - Model serialization (one at a time) for GPU memory management
    - Automatic model unloading based on keep-alive
    - Streaming and non-streaming generation
    - Response caching
    - Error handling and retries
    - Token counting and cost estimation
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 120,
        enable_cache: bool = True,
    ):
        """
        Initialize LLM service.

        Args:
            base_url: Ollama API base URL (default: from settings)
            timeout: Request timeout in seconds
            enable_cache: Enable response caching
        """
        self.base_url = base_url or settings.ollama.host
        self.timeout = timeout
        self.enable_cache = enable_cache

        # HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
        )

        # GPU manager and cache
        self.gpu_manager = get_gpu_manager()
        self.cache_manager = get_cache_manager() if enable_cache else None

        # Currently loaded model tracking
        self.current_model: Optional[str] = None
        self.last_used: Optional[datetime] = None

        logger.info(f"LLMService initialized: {self.base_url}")

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        format: Optional[Literal["json"]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate a response from the LLM.

        Args:
            prompt: User prompt
            model: Model name (default: writer model from settings)
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Enable streaming (returns AsyncIterator if True)
            format: Output format ("json" for structured output)
            **kwargs: Additional Ollama parameters

        Returns:
            Response dictionary with 'text', 'model', 'duration_ms', etc.
        """
        model = model or settings.ollama.writer_model

        # Check cache first (only for non-streaming)
        if not stream and self.enable_cache and self.cache_manager:
            cache_key = self.cache_manager.generate_key(
                "llm_response",
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                format=format,
            )
            cached = self.cache_manager.get(cache_key)
            if cached:
                logger.debug("Cache hit for LLM response")
                return cached

        # Ensure model is loaded
        await self._ensure_model_loaded(model)

        # Build request
        request_data = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature or settings.ollama.writer_temperature,
            },
        }

        if system:
            request_data["system"] = system

        if max_tokens:
            request_data["options"]["num_predict"] = max_tokens

        if format:
            request_data["format"] = format

        # Add any additional options
        request_data["options"].update(kwargs)

        # Make request
        try:
            start_time = datetime.utcnow()

            if stream:
                return self._stream_response(request_data, model, start_time)
            else:
                response = await self.client.post("/api/generate", json=request_data)
                response.raise_for_status()
                result = response.json()

                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Parse response
                parsed = self._parse_response(result, model, duration_ms)

                # Cache result
                if self.enable_cache and self.cache_manager:
                    self.cache_manager.set(cache_key, parsed)

                return parsed

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during generation: {e}")
            raise
        except Exception as e:
            logger.error(f"Error during generation: {e}")
            raise

    async def _stream_response(
        self,
        request_data: Dict,
        model: str,
        start_time: datetime,
    ) -> AsyncIterator[str]:
        """
        Stream response from Ollama.

        Args:
            request_data: Request payload
            model: Model name
            start_time: Request start time

        Yields:
            Response chunks as they arrive
        """
        async with self.client.stream("POST", "/api/generate", json=request_data) as response:
            response.raise_for_status()

            full_text = []

            async for line in response.aiter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    if "response" in chunk:
                        text = chunk["response"]
                        full_text.append(text)
                        yield text

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse streaming chunk: {line}")
                    continue

            # Log completion
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(
                f"Streaming complete: model={model}, "
                f"tokens={''.join(full_text).__len__()}, "
                f"duration={duration_ms:.0f}ms"
            )

    def _parse_response(
        self,
        response: Dict,
        model: str,
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Parse Ollama response into standard format.

        Args:
            response: Raw Ollama response
            model: Model name
            duration_ms: Request duration

        Returns:
            Parsed response dictionary
        """
        return {
            "text": response.get("response", ""),
            "model": model,
            "duration_ms": duration_ms,
            "prompt_tokens": response.get("prompt_eval_count", 0),
            "completion_tokens": response.get("eval_count", 0),
            "total_tokens": (
                response.get("prompt_eval_count", 0)
                + response.get("eval_count", 0)
            ),
            "done": response.get("done", False),
            "context": response.get("context", []),
        }

    async def _ensure_model_loaded(self, model: str):
        """
        Ensure the specified model is loaded.

        Implements model serialization: unloads other models if needed.

        Args:
            model: Model name to load
        """
        # If this model is already loaded, just update timestamp
        if self.current_model == model:
            self.last_used = datetime.utcnow()
            logger.debug(f"Model {model} already loaded")
            return

        # If a different model is loaded, unload it first
        if self.current_model and self.current_model != model:
            logger.info(f"Unloading model {self.current_model} to load {model}")
            await self._unload_model(self.current_model)

        # Load the new model
        logger.info(f"Loading model: {model}")

        # Register with GPU manager
        self.gpu_manager.register_model_loaded(model)

        # Warm up model with a simple request
        try:
            await self.client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": "Hello",
                    "stream": False,
                    "options": {"num_predict": 1},
                },
            )
            logger.info(f"Model {model} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model {model}: {e}")
            raise

        self.current_model = model
        self.last_used = datetime.utcnow()

    async def _unload_model(self, model: str):
        """
        Unload a model to free GPU memory.

        Args:
            model: Model name to unload
        """
        try:
            # Ollama unload via keep_alive=0
            await self.client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": "",
                    "keep_alive": 0,
                },
            )

            self.gpu_manager.register_model_unloaded(model)
            logger.info(f"Model {model} unloaded")

        except Exception as e:
            logger.warning(f"Failed to unload model {model}: {e}")

        if self.current_model == model:
            self.current_model = None
            self.last_used = None

    async def generate_json(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response.

        Args:
            prompt: User prompt
            model: Model name
            system: System prompt
            **kwargs: Additional parameters

        Returns:
            Parsed JSON response
        """
        response = await self.generate(
            prompt=prompt,
            model=model,
            system=system,
            format="json",
            **kwargs,
        )

        # Parse JSON from text
        try:
            return json.loads(response["text"])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response['text']}")
            raise ValueError(f"Invalid JSON response: {e}")

    async def check_model_availability(self, model: str) -> bool:
        """
        Check if a model is available.

        Args:
            model: Model name

        Returns:
            True if model is available
        """
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            available_models = [m["name"] for m in data.get("models", [])]
            return model in available_models

        except Exception as e:
            logger.error(f"Failed to check model availability: {e}")
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models.

        Returns:
            List of model information dictionaries
        """
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])

        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Returns:
            Health status dictionary
        """
        health = {
            "status": "unknown",
            "ollama_reachable": False,
            "current_model": self.current_model,
            "models_available": [],
        }

        try:
            # Check if Ollama is reachable
            response = await self.client.get("/api/version", timeout=5.0)
            response.raise_for_status()

            health["ollama_reachable"] = True
            health["ollama_version"] = response.json().get("version", "unknown")

            # List available models
            models = await self.list_models()
            health["models_available"] = [m["name"] for m in models]

            # Check if configured models are available
            required_models = [
                settings.ollama.writer_model,
                settings.ollama.triager_model,
                settings.ollama.reader_model,
            ]

            missing_models = [
                m for m in required_models if m not in health["models_available"]
            ]

            if missing_models:
                health["status"] = "degraded"
                health["missing_models"] = missing_models
            else:
                health["status"] = "healthy"

        except Exception as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)

        # Add GPU stats
        gpu_stats = self.gpu_manager.get_stats()
        if gpu_stats:
            health["gpu"] = gpu_stats.to_dict()

        return health

    async def close(self):
        """Close the HTTP client."""
        if self.current_model:
            await self._unload_model(self.current_model)

        await self.client.aclose()
        logger.info("LLMService closed")

    def __repr__(self) -> str:
        return (
            f"LLMService(base_url='{self.base_url}', "
            f"current_model='{self.current_model}')"
        )


# Global singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """
    Get global LLMService instance (singleton).

    Returns:
        Shared LLMService instance
    """
    global _llm_service

    if _llm_service is None:
        _llm_service = LLMService()

    return _llm_service


async def reset_llm_service():
    """Reset global LLM service (useful for testing)."""
    global _llm_service
    if _llm_service:
        await _llm_service.close()
    _llm_service = None
