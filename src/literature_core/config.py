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
    LITCORE_PROJECT_ROOT - Project root directory (auto-detected if not set)
    LITCORE_DATABASE_PATH - Path to SQLite database
    LITCORE_PDF_STORAGE_PATH - Path to PDF storage
    LITCORE_CHROMA_PATH - Path to ChromaDB vectorstore
    LITCORE_ZOTERO_API_KEY - Zotero API key
    LITCORE_LOG_LEVEL - Logging level (DEBUG, INFO, WARNING, ERROR)
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Find project root by looking for marker files.

    Searches upward from current file for:
    1. LITCORE_PROJECT_ROOT environment variable (highest priority)
    2. .git directory (best indicator of repo root)
    3. data/ directory with literature.db (indicates correct root)
    4. Falls back to parent of src/ directory

    Note: pyproject.toml is NOT used as a marker because it may exist
    in subdirectories like src/.
    """
    # Check environment variable first
    env_root = os.environ.get("LITCORE_PROJECT_ROOT")
    if env_root:
        return Path(env_root)

    # Start from the config.py file location
    current = Path(__file__).resolve().parent

    # Search upward for markers (prioritize .git)
    for _ in range(10):  # Limit search depth
        if (current / ".git").exists():
            return current
        # Check for data directory with database (strong indicator)
        if (current / "data" / "literature.db").exists():
            return current
        if current.parent == current:  # Reached filesystem root
            break
        current = current.parent

    # Fallback: assume src/literature_core/config.py structure
    # Go up 3 levels: config.py -> literature_core -> src -> project_root
    return Path(__file__).resolve().parent.parent.parent


# Project root (auto-detected or from environment)
PROJECT_ROOT = _find_project_root()

# Default data directory: {PROJECT_ROOT}/data/
_DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


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

    # Database - default to {PROJECT_ROOT}/data/literature.db
    database_path: Path = _DEFAULT_DATA_DIR / "literature.db"

    # ChromaDB for semantic search
    chroma_path: Path = _DEFAULT_DATA_DIR / "vectorstore"

    # PDF storage
    pdf_storage_path: Path = _DEFAULT_DATA_DIR / "pdfs"

    # Search index cache
    search_index_path: Path = _DEFAULT_DATA_DIR / "cache" / "search_index"

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
