"""Configuration management for literature-database service."""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from loguru import logger

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.warning("PyYAML not available. Legacy YAML config loading disabled.")


@dataclass
class ServiceConfig:
    """Service configuration settings."""
    port: int = 8001
    host: str = "0.0.0.0"
    name: str = "literature-database"
    debug: bool = False
    reload: bool = False


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    url: str = "sqlite:///data/metadata/literature.db"
    
    @property
    def is_sqlite(self) -> bool:
        """Check if database is SQLite."""
        return self.url.startswith("sqlite:")


@dataclass
class RedisConfig:
    """Redis configuration settings."""
    url: str = "redis://localhost:6379"
    enabled: bool = True


@dataclass
class ZoteroConfig:
    """Zotero integration configuration."""
    windows_path: str = "/mnt/c/Users/dreec/Zotero"
    library_type: str = "user"


@dataclass
class PDFConfig:
    """PDF processing configuration."""
    storage_path: str = "data/pdfs"
    extract_text: bool = True
    extract_images: bool = False
    ocr_enabled: bool = False


@dataclass
class SearchConfig:
    """Search configuration."""
    index_path: str = "data/cache/search_index"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "logs/litdb.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    max_size: int = 10485760  # 10MB
    backup_count: int = 5


@dataclass
class CORSConfig:
    """CORS configuration."""
    origins: List[str] = None
    
    def __post_init__(self):
        if self.origins is None:
            self.origins = ["http://localhost:3000", "http://localhost:8000"]


@dataclass
class LiteratureDatabaseConfig:
    """Complete configuration for literature-database service."""
    service: ServiceConfig
    database: DatabaseConfig
    redis: RedisConfig
    zotero: ZoteroConfig
    pdf: PDFConfig
    search: SearchConfig
    logging: LoggingConfig
    cors: CORSConfig


def parse_cors_origins(origins_str: str) -> List[str]:
    """Parse CORS origins from environment string."""
    try:
        # Try parsing as JSON list
        return json.loads(origins_str)
    except json.JSONDecodeError:
        # Fall back to comma-separated
        return [origin.strip() for origin in origins_str.split(",")]


def str_to_bool(value: str) -> bool:
    """Convert string to boolean."""
    return value.lower() in ("true", "1", "yes", "on")


def load_env_config() -> LiteratureDatabaseConfig:
    """Load configuration from environment variables."""
    return LiteratureDatabaseConfig(
        service=ServiceConfig(
            port=int(os.getenv("SERVICE_PORT", "8001")),
            host=os.getenv("SERVICE_HOST", "0.0.0.0"),
            name=os.getenv("SERVICE_NAME", "literature-database"),
            debug=str_to_bool(os.getenv("DEBUG", "false")),
            reload=str_to_bool(os.getenv("RELOAD", "false"))
        ),
        database=DatabaseConfig(
            url=os.getenv("DATABASE_URL", "sqlite:///data/metadata/literature.db")
        ),
        redis=RedisConfig(
            url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            enabled=str_to_bool(os.getenv("REDIS_ENABLED", "true"))
        ),
        zotero=ZoteroConfig(
            windows_path=os.getenv("ZOTERO_WINDOWS_PATH", "/mnt/c/Users/dreec/Zotero"),
            library_type=os.getenv("ZOTERO_LIBRARY_TYPE", "user")
        ),
        pdf=PDFConfig(
            storage_path=os.getenv("PDF_STORAGE_PATH", "data/pdfs"),
            extract_text=str_to_bool(os.getenv("PDF_EXTRACT_TEXT", "true")),
            extract_images=str_to_bool(os.getenv("PDF_EXTRACT_IMAGES", "false")),
            ocr_enabled=str_to_bool(os.getenv("PDF_OCR_ENABLED", "false"))
        ),
        search=SearchConfig(
            index_path=os.getenv("SEARCH_INDEX_PATH", "data/cache/search_index")
        ),
        logging=LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            file=os.getenv("LOG_FILE", "logs/litdb.log"),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            max_size=int(os.getenv("LOG_MAX_SIZE", "10485760")),
            backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5"))
        ),
        cors=CORSConfig(
            origins=parse_cors_origins(os.getenv("CORS_ORIGINS", '["http://localhost:3000", "http://localhost:8000"]'))
        )
    )


def load_yaml_config(config_path: str) -> Optional[Dict[str, Any]]:
    """Load legacy YAML configuration file."""
    if not YAML_AVAILABLE:
        logger.warning("PyYAML not available. Cannot load YAML config.")
        return None
        
    config_file = Path(config_path)
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_path}")
        return None
    
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load YAML config from {config_path}: {e}")
        return None


def merge_yaml_with_env_config(yaml_config: Dict[str, Any], env_config: LiteratureDatabaseConfig) -> LiteratureDatabaseConfig:
    """Merge YAML config with environment config, prioritizing environment."""
    
    # Environment config takes precedence, but fill in missing values from YAML
    if not yaml_config:
        return env_config
    
    # Only override if environment variable is default (not explicitly set)
    def get_yaml_value(yaml_path: List[str], default=None):
        """Get nested value from YAML config."""
        current = yaml_config
        for key in yaml_path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    # Update database config if using default SQLite path
    if env_config.database.url == "sqlite:///data/metadata/literature.db":
        yaml_db_path = get_yaml_value(["database", "path"])
        if yaml_db_path:
            env_config.database.url = f"sqlite:///{yaml_db_path}"
    
    # Update Zotero path if using default
    if env_config.zotero.windows_path == "/mnt/c/Users/dreec/Zotero":
        yaml_zotero_path = get_yaml_value(["zotero", "windows_path"])
        if yaml_zotero_path:
            env_config.zotero.windows_path = yaml_zotero_path
    
    # Update PDF storage path if using default
    if env_config.pdf.storage_path == "data/pdfs":
        yaml_pdf_path = get_yaml_value(["pdf", "storage_path"])
        if yaml_pdf_path:
            env_config.pdf.storage_path = yaml_pdf_path
    
    # Update search index path if using default
    if env_config.search.index_path == "data/cache/search_index":
        yaml_search_path = get_yaml_value(["search", "index_path"])
        if yaml_search_path:
            env_config.search.index_path = yaml_search_path
    
    return env_config


def load_config() -> LiteratureDatabaseConfig:
    """Load configuration with environment precedence over YAML."""
    
    # Load from environment first
    config = load_env_config()
    
    # Try to load legacy YAML config
    yaml_config_path = os.getenv("LITDB_CONFIG_PATH", "config/settings.yml")
    yaml_config = load_yaml_config(yaml_config_path)
    
    # Merge YAML into env config (env takes precedence)
    config = merge_yaml_with_env_config(yaml_config, config)
    
    logger.debug(f"Loaded configuration - Service: {config.service.name}:{config.service.port}")
    
    return config


# Global configuration instance
_config: Optional[LiteratureDatabaseConfig] = None


def get_config() -> LiteratureDatabaseConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> LiteratureDatabaseConfig:
    """Reload configuration from environment and files."""
    global _config
    _config = None
    return get_config()


# Convenience functions for common config access
def get_database_url() -> str:
    """Get database URL."""
    return get_config().database.url


def get_redis_url() -> str:
    """Get Redis URL."""
    return get_config().redis.url


def is_redis_enabled() -> bool:
    """Check if Redis is enabled."""
    return get_config().redis.enabled


def get_service_port() -> int:
    """Get service port."""
    return get_config().service.port


def get_service_name() -> str:
    """Get service name."""
    return get_config().service.name


def get_zotero_path() -> str:
    """Get Zotero path."""
    return get_config().zotero.windows_path