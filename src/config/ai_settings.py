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

# Data directory (consolidated location for all runtime data)
# Previously used LEGACY_AI_DATA_DIR for infrastructure/literature-ai/data


class OllamaSettings(BaseSettings):
    """Ollama service configuration."""

    host: str = Field(default="http://localhost:11434", description="Ollama API URL")
    timeout: int = Field(default=300, description="Request timeout in seconds (300s for large papers)")
    keep_alive: int = Field(default=60, description="Model keep-alive time in seconds")

    # Model specifications
    writer_model: str = Field(default="qwen:7b-q5_K_M", description="Model for writing assistance")
    triager_model: str = Field(default="qwen:7b-q4_K_M", description="Model for paper triage")
    reader_model: str = Field(default="qwen2.5:7b-instruct-q5_K_M", description="Model for Q&A and extraction")

    # Extraction-specific models (two-tier system)
    quick_extractor_model: str = Field(
        default="qwen2.5:3b-instruct-q4_K_M",
        description="Fast model for quick extraction (abstract-only: type, topics, summary)"
    )
    deep_extractor_model: str = Field(
        default="qwen2.5:7b-instruct-q5_K_M",
        description="Full model for deep extraction (PDF: findings, methodology, claims)"
    )

    # Model parameters
    writer_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    triager_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reader_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    max_context_length: int = Field(default=28000, description="Maximum context window (28K for qwen2.5)")
    num_predict: int = Field(default=3000, description="Maximum tokens to generate in response")

    model_config = SettingsConfigDict(env_prefix="OLLAMA_")


class EmbeddingSettings(BaseSettings):
    """Embedding model configuration.

    Dual-model architecture:
    - Paper-level: SPECTER2 for scientific paper similarity
    - Chunk-level: BGE for full-text retrieval
    """

    # Legacy single model (for backwards compatibility during migration)
    model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Legacy model (deprecated, use paper_model_name/chunk_model_name)"
    )
    dimension: int = Field(default=384, description="Legacy dimension (deprecated)")

    # Paper-level embeddings (SPECTER2)
    paper_model_name: str = Field(
        default="allenai/specter2_base",
        description="Model for paper-level similarity (title+abstract)"
    )
    paper_dimension: int = Field(default=768, description="SPECTER2 embedding dimension")

    # Chunk-level embeddings (BGE)
    chunk_model_name: str = Field(
        default="BAAI/bge-base-en-v1.5",
        description="Model for chunk-level retrieval (full-text)"
    )
    chunk_dimension: int = Field(default=768, description="BGE embedding dimension")

    # Dual model feature flag (enable to use new models)
    use_dual_models: bool = Field(
        default=False,
        description="Enable dual model architecture (SPECTER2 + BGE). Set True after re-indexing."
    )

    batch_size: int = Field(default=64, description="Batch size for embedding generation (was 32)")
    device: str = Field(default="cuda", description="Device: 'cuda' or 'cpu'")
    normalize: bool = Field(default=True, description="L2 normalize embeddings")

    # Chunking parameters (improved settings)
    chunk_size: int = Field(default=768, description="Tokens per chunk (was 512)")
    chunk_overlap: int = Field(default=192, description="Overlap between chunks (was 128)")

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
    score_threshold: float = Field(default=0.35, description="Minimum similarity score (discovery-focused)")

    # HNSW index tuning (improved settings)
    hnsw_ef_construction: int = Field(
        default=200,
        description="HNSW ef_construction - higher = better index quality (was ~100)"
    )
    hnsw_ef_search: int = Field(
        default=64,
        description="HNSW ef at query time - higher = better recall (was ~10)"
    )
    hnsw_m: int = Field(
        default=32,
        description="HNSW M - connections per node - higher = better recall (was ~16)"
    )

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
    # ai_settings.py is at src/config/ai_settings.py, so parent.parent.parent = research/
    database_path: Path = Field(
        default=PROJECT_ROOT / "data" / "literature.db",
        description="Path to SQLite database file"
    )

    timeout: int = Field(default=30, description="Database query timeout in seconds")

    model_config = SettingsConfigDict(env_prefix="LITDB_")


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


class RerankerSettings(BaseSettings):
    """Cross-encoder re-ranking configuration.

    Re-ranking improves precision by scoring (query, document) pairs directly.
    Used after initial retrieval to refine top results.
    """

    model_name: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model for re-ranking"
    )
    enabled: bool = Field(
        default=False,
        description="Enable re-ranking (requires model download)"
    )
    top_k_candidates: int = Field(
        default=50,
        description="Number of candidates to fetch for re-ranking"
    )
    top_k_results: int = Field(
        default=20,
        description="Number of results to return after re-ranking"
    )
    device: str = Field(default="cuda", description="Device: 'cuda' or 'cpu'")

    model_config = SettingsConfigDict(env_prefix="RERANKER_")


class ClaudeSettings(BaseSettings):
    """Claude API settings for AI extraction.

    Uses Anthropic API for paper extraction. Token-efficient strategy:
    - Haiku for most papers (fast, cheap, good for structured extraction)
    - Sonnet for complex/long papers requiring deeper analysis
    - Caches abstracts-only extraction to avoid re-processing
    """

    api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    default_model: str = Field(
        default="claude-haiku-4-20250514",
        description="Default model for extraction (Haiku for efficiency)"
    )
    complex_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model for complex papers (Sonnet for depth)"
    )
    timeout: int = Field(default=120, description="Request timeout in seconds")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="Sampling temperature")
    max_tokens: int = Field(default=4096, description="Maximum tokens in response")

    # Token efficiency settings
    max_input_chars: int = Field(
        default=50000,
        description="Max chars to send (approx 12.5K tokens)"
    )
    abstract_only_threshold: int = Field(
        default=500,
        description="If abstract > this length, skip full text for basic extraction"
    )
    use_tiered_models: bool = Field(
        default=True,
        description="Use Haiku for simple papers, Sonnet for complex"
    )

    model_config = SettingsConfigDict(env_prefix="CLAUDE_")


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
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    gpu: GPUSettings = Field(default_factory=GPUSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    claude: ClaudeSettings = Field(default_factory=ClaudeSettings)

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
    "MCPSettings",
    "LoggingSettings",
    "GPUSettings",
    "RerankerSettings",
    "ClaudeSettings",
    "PROJECT_ROOT",
    "DATA_DIR",
    "LOGS_DIR",
]
