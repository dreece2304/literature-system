"""
Caching utilities for LLM responses and embeddings.

Provides Redis-backed caching with TTL support and cache key generation.
"""

import hashlib
import json
from typing import Any, Optional, Dict
from functools import wraps

import redis
from loguru import logger

from config.settings import settings


class CacheManager:
    """
    Manages caching for LLM responses and embeddings.

    Features:
    - Redis-backed storage
    - Configurable TTL
    - Cache key generation from parameters
    - Optional cache bypass
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        enabled: bool = True,
        default_ttl: int = 3600,
    ):
        """
        Initialize cache manager.

        Args:
            redis_client: Redis client instance (creates new if None)
            enabled: Enable caching
            default_ttl: Default time-to-live in seconds
        """
        self.enabled = enabled and settings.redis.cache_enabled
        self.default_ttl = default_ttl or settings.redis.cache_ttl

        if self.enabled:
            self.redis = redis_client or redis.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=settings.redis.password,
                decode_responses=True,
            )
            logger.info("CacheManager initialized with Redis")
        else:
            self.redis = None
            logger.info("CacheManager initialized (caching disabled)")

    def generate_key(self, namespace: str, **params) -> str:
        """
        Generate a cache key from parameters.

        Args:
            namespace: Cache namespace (e.g., 'llm_response', 'embedding')
            **params: Parameters to include in key

        Returns:
            Cache key string
        """
        # Sort params for consistency
        sorted_params = sorted(params.items())

        # Create hash
        param_str = json.dumps(sorted_params, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]

        return f"{namespace}:{param_hash}"

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self.enabled or not self.redis:
            return None

        try:
            value = self.redis.get(key)
            if value:
                logger.debug(f"Cache hit: {key}")
                return json.loads(value)
            else:
                logger.debug(f"Cache miss: {key}")
                return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ):
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if not self.enabled or not self.redis:
            return

        ttl = ttl or self.default_ttl

        try:
            serialized = json.dumps(value)
            self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")

    def delete(self, key: str):
        """
        Delete value from cache.

        Args:
            key: Cache key
        """
        if not self.enabled or not self.redis:
            return

        try:
            self.redis.delete(key)
            logger.debug(f"Cache delete: {key}")
        except Exception as e:
            logger.warning(f"Cache delete failed: {e}")

    def clear_namespace(self, namespace: str):
        """
        Clear all keys in a namespace.

        Args:
            namespace: Namespace prefix
        """
        if not self.enabled or not self.redis:
            return

        try:
            pattern = f"{namespace}:*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} keys from namespace: {namespace}")
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Statistics dictionary
        """
        if not self.enabled or not self.redis:
            return {"enabled": False}

        try:
            info = self.redis.info("stats")
            return {
                "enabled": True,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0)
                    / max(
                        info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0),
                        1,
                    )
                    * 100
                ),
            }
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"enabled": True, "error": str(e)}


# Global instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Get global CacheManager instance (singleton).

    Returns:
        Shared CacheManager instance
    """
    global _cache_manager

    if _cache_manager is None:
        _cache_manager = CacheManager(
            enabled=settings.redis.cache_enabled,
            default_ttl=settings.redis.cache_ttl,
        )

    return _cache_manager


def reset_cache_manager():
    """Reset global cache manager (useful for testing)."""
    global _cache_manager
    _cache_manager = None


def cached(namespace: str, ttl: Optional[int] = None):
    """
    Decorator for caching function results.

    Args:
        namespace: Cache namespace
        ttl: Time-to-live in seconds

    Example:
        @cached("llm_response", ttl=3600)
        def generate_response(prompt, model):
            return llm.generate(prompt, model)
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_manager()

            if not cache.enabled:
                return func(*args, **kwargs)

            # Generate cache key from function args
            cache_params = {
                "function": func.__name__,
                "args": args,
                **kwargs,
            }
            key = cache.generate_key(namespace, **cache_params)

            # Try to get from cache
            cached_result = cache.get(key)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            cache.set(key, result, ttl=ttl)

            return result

        return wrapper

    return decorator
