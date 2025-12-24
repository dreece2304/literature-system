"""
Configuration management using Pydantic Settings.

This module provides centralized configuration for the literature-ai service,
with support for environment variables, defaults, and validation.
"""

from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Base paths - adjusted for consolidated structure
PROJECT_ROOT = Path(__file__).parent.parent.parent  # research/
SRC_DIR = Path(__file__).parent.parent              # src/
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


class OllamaSettings(BaseSettings):
    """Ollama service configuration."""

    host: str = Field(default="http://localhost:11434", description="Ollama API URL")
    timeout: int = Field(default=120, description="Request timeout in seconds")
    keep_alive: int = Field(default=60, description="Model keep-alive time in seconds")

    # Model specifications
    writer_model: str = Field(default="qwen:7b-q5_K_M", description="Model for writing assistance")
    triager_model: str = Field(default="qwen:7b-q4_K_M", description="Model for paper triage")
    reader_model: str = Field(default="qwen:7b-q5_K_M", description="Model for Q&A")

    # Model parameters
    writer_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    triager_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reader_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    max_context_length: int = Field(default=8192, description="Maximum context window")

    model_config = SettingsConfigDict(env_prefix="OLLAMA_")


class EmbeddingSettings(BaseSettings):
    """Embedding model configuration."""

    model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace model identifier"
    )
    dimension: int = Field(default=384, description="Embedding vector dimension")
    batch_size: int = Field(default=32, description="Batch size for embedding generation")
    device: str = Field(default="cuda", description="Device: 'cuda' or 'cpu'")
    normalize: bool = Field(default=True, description="L2 normalize embeddings")

    # Chunking parameters
    chunk_size: int = Field(default=512, description="Tokens per chunk")
    chunk_overlap: int = Field(default=128, description="Overlap between chunks")

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")


class ChromaDBSettings(BaseSettings):
    """ChromaDB vector store configuration."""

    persist_directory: Path = Field(
        default=DATA_DIR / "vectorstore",
        description="ChromaDB persistence directory"
    )
    collection_name: str = Field(default="papers", description="Collection name")
    distance_metric: Literal["cosine", "l2", "ip"] = Field(
        default="cosine",
        description="Distance metric: cosine, l2, or ip (inner product)"
    )

    # Search parameters
    top_k: int = Field(default=10, description="Default number of results")
    score_threshold: float = Field(default=0.7, description="Minimum similarity score")

    model_config = SettingsConfigDict(env_prefix="CHROMA_")

    @field_validator("persist_directory")
    @classmethod
    def ensure_directory(cls, v: Path) -> Path:
        """Ensure the persistence directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v


class RedisSettings(BaseSettings):
    """Redis configuration for events and caching."""

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")

    # Event channels
    paper_events_channel: str = Field(default="paper.events", description="Paper event channel")

    # Cache settings
    cache_ttl: int = Field(default=3600, description="Cache TTL in seconds")
    cache_enabled: bool = Field(default=True, description="Enable response caching")

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    @property
    def url(self) -> str:
        """Construct Redis URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class CelerySettings(BaseSettings):
    """Celery task queue configuration."""

    broker_url: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    result_backend: str = Field(default="redis://localhost:6379/0", description="Result backend URL")

    # Task configuration
    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    accept_content: list[str] = Field(default=["json"])
    timezone: str = Field(default="UTC")
    enable_utc: bool = Field(default=True)

    # Worker configuration
    worker_prefetch_multiplier: int = Field(default=1, description="Tasks to prefetch")
    worker_max_tasks_per_child: int = Field(default=100, description="Tasks before worker restart")

    model_config = SettingsConfigDict(env_prefix="CELERY_")


class LiteratureDatabaseSettings(BaseSettings):
    """Literature database configuration.

    NOTE (Dec 2024): The HTTP API layer has been removed.
    The MCP server now accesses the database directly via services.
    """

    # DEPRECATED: api_url no longer used - keeping for backwards compatibility
    api_url: str = Field(
        default="http://localhost:8001",
        description="DEPRECATED: No longer used. MCP uses direct DB access."
    )

    # Database path (used by service layer)
    database_path: Path = Field(
        default=Path(__file__).parent.parent.parent.parent / "literature-database" / "data" / "literature.db",
        description="Path to SQLite database file"
    )

    timeout: int = Field(default=30, description="Database query timeout in seconds")

    model_config = SettingsConfigDict(env_prefix="LITDB_")


class ClaudeSettings(BaseSettings):
    """Anthropic Claude API configuration for extraction."""

    api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    model: str = Field(default="claude-sonnet-4-20250514", description="Claude model to use")
    max_tokens: int = Field(default=4096, description="Maximum tokens in response")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="Sampling temperature")
    timeout: int = Field(default=120, description="Request timeout in seconds")

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")


class MCPSettings(BaseSettings):
    """MCP Server settings.

    NOTE (Dec 2024): Replaced FastAPI APISettings.
    The MCP server communicates via stdio, not HTTP.
    """

    service_name: str = Field(default="literature")
    version: str = Field(default="0.1.0")
    description: str = Field(default="MCP server for literature management")

    # Logging level for MCP operations
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    model_config = SettingsConfigDict(env_prefix="MCP_")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"  # noqa: E501
    )

    # File logging
    log_file: Path = Field(default=LOGS_DIR / "literature-ai.log")
    rotation: str = Field(default="100 MB", description="Log rotation size")
    retention: str = Field(default="30 days", description="Log retention period")
    compression: str = Field(default="zip")

    # Structured logging
    json_logs: bool = Field(default=False, description="Output JSON-formatted logs")

    model_config = SettingsConfigDict(env_prefix="LOG_")

    @field_validator("log_file")
    @classmethod
    def ensure_log_directory(cls, v: Path) -> Path:
        """Ensure the log directory exists."""
        v.parent.mkdir(parents=True, exist_ok=True)
        return v


class GPUSettings(BaseSettings):
    """GPU memory management settings."""

    enable_monitoring: bool = Field(default=True, description="Enable GPU monitoring")
    max_vram_usage: float = Field(default=7.5, description="Max VRAM in GB")
    memory_threshold: float = Field(default=0.9, description="Warning threshold (0-1)")

    # Model serialization
    unload_delay: int = Field(default=60, description="Seconds before unloading model")
    force_serialize: bool = Field(default=True, description="Force model serialization")

    model_config = SettingsConfigDict(env_prefix="GPU_")


class Settings(BaseSettings):
    """Master settings aggregating all configuration sections."""

    # Environment
    environment: Literal["development", "production", "testing"] = Field(default="development")
    debug: bool = Field(default=False)

    # Service name
    service_name: str = Field(default="literature-ai")

    # Sub-settings
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    chromadb: ChromaDBSettings = Field(default_factory=ChromaDBSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    litdb: LiteratureDatabaseSettings = Field(default_factory=LiteratureDatabaseSettings)
    claude: ClaudeSettings = Field(default_factory=ClaudeSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    gpu: GPUSettings = Field(default_factory=GPUSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()


# Convenience exports
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
    "MCPSettings",
    "LoggingSettings",
    "GPUSettings",
    "PROJECT_ROOT",
    "DATA_DIR",
    "LOGS_DIR",
]
