"""Logging configuration for the literature database."""
import sys
from pathlib import Path
from loguru import logger
import yaml
import os


def setup_logging(config_path: str = None) -> None:
    """
    Configure logging using loguru.

    Args:
        config_path: Optional path to configuration file
    """
    # Load configuration
    if config_path is None:
        config_path = os.getenv('LITDB_CONFIG_PATH', 'config/settings.yml')

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logging_config = config.get('logging', {})
    except FileNotFoundError:
        logging_config = {}

    # Get configuration values with defaults
    log_level = logging_config.get('level', 'INFO')
    log_file = logging_config.get('file', 'logs/litdb.log')

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Add console handler with colors
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True
    )

    # Add file handler
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )

    logger.info(f"Logging initialized - Level: {log_level}, File: {log_file}")


def get_logger(name: str = None):
    """
    Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger
