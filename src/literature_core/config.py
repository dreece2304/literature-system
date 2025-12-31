"""Configuration using Pydantic Settings with environment variable support.

The settings module provides centralized configuration for the literature management
system. Settings are loaded from environment variables with the LITCORE_ prefix.

Usage:
    from literature_core import settings

    # Access database URL
    engine = create_engine(settings.database_url)

    # Check API keys
    if settings.zotero_api_key:
        sync_with_zotero()

Environment Variables:
    LITCORE_DATABASE_PATH - Path to SQLite database
    LITCORE_PDF_STORAGE_PATH - Path to PDF storage
    LITCORE_ZOTERO_API_KEY - Zotero API key
    LITCORE_LOG_LEVEL - Logging level (DEBUG, INFO, WARNING, ERROR)
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


# Default base directories for data storage
_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent / "infrastructure/literature-database/data"
_AI_DATA_DIR = Path(__file__).parent.parent.parent / "infrastructure/literature-ai/data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All paths can be overridden via environment variables with LITCORE_ prefix.
    For example: LITCORE_DATABASE_PATH=/path/to/database.db
    """

    model_config = SettingsConfigDict(
        env_prefix="LITCORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database - default to infrastructure/literature-database/data/metadata/literature.db
    database_path: Path = _DEFAULT_DATA_DIR / "metadata/literature.db"

    # ChromaDB for semantic search (in literature-ai data directory)
    chroma_path: Path = _AI_DATA_DIR / "vectorstore"

    # PDF storage
    pdf_storage_path: Path = _DEFAULT_DATA_DIR / "pdfs"

    # Search index (Whoosh)
    search_index_path: Path = _DEFAULT_DATA_DIR / "whoosh"

    # Zotero integration
    zotero_api_key: Optional[str] = None
    zotero_library_id: Optional[str] = None
    zotero_library_type: str = "user"

    # External API keys
    semantic_scholar_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    log_file: Optional[Path] = None

    # Embedding settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 32
    embedding_device: str = "cuda"
    embedding_normalize: bool = True

    # Chunking parameters
    chunk_size: int = 512
    chunk_overlap: int = 128

    # ChromaDB settings
    chroma_collection_name: str = "papers"
    chroma_distance_metric: str = "cosine"
    chroma_top_k: int = 10
    chroma_score_threshold: float = 0.35  # Discovery-focused threshold

    @property
    def database_url(self) -> str:
        """Get SQLAlchemy database URL."""
        return f"sqlite:///{self.database_path.absolute()}"

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.pdf_storage_path.mkdir(parents=True, exist_ok=True)
        self.search_index_path.mkdir(parents=True, exist_ok=True)
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
