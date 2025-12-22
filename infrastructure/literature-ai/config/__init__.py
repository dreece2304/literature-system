"""
Configuration module for literature-ai service.

Provides centralized configuration management using Pydantic Settings
with support for environment variables and validation.
"""

from .settings import (
    settings,
    Settings,
    OllamaSettings,
    EmbeddingSettings,
    ChromaDBSettings,
    RedisSettings,
    CelerySettings,
    LiteratureDatabaseSettings,
    ClaudeSettings,
    APISettings,
    LoggingSettings,
    GPUSettings,
    PROJECT_ROOT,
    DATA_DIR,
    LOGS_DIR,
)

__all__ = [
    "settings",
    "Settings",
    "OllamaSettings",
    "EmbeddingSettings",
    "ChromaDBSettings",
    "RedisSettings",
    "CelerySettings",
    "LiteratureDatabaseSettings",
    "ClaudeSettings",
    "APISettings",
    "LoggingSettings",
    "GPUSettings",
    "PROJECT_ROOT",
    "DATA_DIR",
    "LOGS_DIR",
]
