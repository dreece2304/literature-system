"""Logging configuration for literature management services.

Provides consistent logging setup across all components with:
- Structured log format for easy parsing
- Configurable log levels
- Automatic quieting of noisy third-party loggers

Usage:
    from literature_core.logging_config import setup_logging, get_logger

    # In service startup
    setup_logging(level="INFO")

    # In modules
    logger = get_logger(__name__)
    logger.info("Processing paper", extra={"paper_id": 123})
"""
import logging
import sys
from typing import Any


# Default log format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Detailed format for debugging
DEBUG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | "
    "%(funcName)s | %(message)s"
)

# JSON-like format for structured logging
STRUCTURED_FORMAT = (
    '{"time": "%(asctime)s", "level": "%(levelname)s", '
    '"logger": "%(name)s", "message": "%(message)s"}'
)


def setup_logging(
    level: str = "INFO",
    format_style: str = "default",
    log_file: str | None = None,
) -> None:
    """Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_style: Format style ("default", "debug", "structured")
        log_file: Optional file path to write logs to

    Example:
        # Basic setup
        setup_logging(level="INFO")

        # Debug mode with detailed format
        setup_logging(level="DEBUG", format_style="debug")

        # Production with file logging
        setup_logging(level="INFO", log_file="/var/log/literature.log")
    """
    # Select format
    if format_style == "debug":
        log_format = DEBUG_FORMAT
    elif format_style == "structured":
        log_format = STRUCTURED_FORMAT
    else:
        log_format = DEFAULT_FORMAT

    # Configure handlers
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        datefmt=DEFAULT_DATE_FORMAT,
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

    # Quiet noisy third-party loggers
    _quiet_noisy_loggers()

    # Log startup
    logger = get_logger("literature_core")
    logger.info(f"Logging configured: level={level}, format={format_style}")


def _quiet_noisy_loggers() -> None:
    """Reduce verbosity of third-party loggers."""
    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "chromadb",
        "sentence_transformers",
        "transformers",
        "huggingface_hub",
        "filelock",
        "sqlalchemy.engine",
        "asyncio",
        "parso",
    ]

    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name.

    Args:
        name: Logger name, typically __name__ of the calling module

    Returns:
        Configured Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
        logger.debug("Details", extra={"key": "value"})
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding temporary context to log messages.

    Usage:
        with LogContext(paper_id=123, operation="import"):
            logger.info("Starting import")  # Will include context
    """

    def __init__(self, **context: Any):
        self.context = context
        self._old_factory = None

    def __enter__(self):
        self._old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self._old_factory)
        return False


def log_operation(
    logger: logging.Logger,
    operation: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    **extra: Any,
) -> None:
    """Log an operation with structured extra data.

    Args:
        logger: Logger instance
        operation: Operation name (e.g., "create", "update", "delete")
        entity_type: Type of entity (e.g., "paper", "collection")
        entity_id: ID of the entity
        **extra: Additional context to log

    Example:
        log_operation(logger, "create", "paper", 123, doi="10.1234/...")
    """
    msg_parts = [operation]
    if entity_type:
        msg_parts.append(entity_type)
    if entity_id:
        msg_parts.append(str(entity_id))

    message = " ".join(msg_parts)

    extra_data = {"operation": operation}
    if entity_type:
        extra_data["entity_type"] = entity_type
    if entity_id:
        extra_data["entity_id"] = entity_id
    extra_data.update(extra)

    logger.info(message, extra=extra_data)


def log_error(
    logger: logging.Logger,
    error: Exception,
    operation: str | None = None,
    **context: Any,
) -> None:
    """Log an error with structured context.

    Args:
        logger: Logger instance
        error: The exception that occurred
        operation: Operation that was being performed
        **context: Additional context

    Example:
        try:
            process_paper(paper_id)
        except Exception as e:
            log_error(logger, e, operation="process_paper", paper_id=paper_id)
    """
    error_type = type(error).__name__
    error_msg = str(error)

    msg_parts = [f"{error_type}: {error_msg}"]
    if operation:
        msg_parts.insert(0, f"Error in {operation}:")

    message = " ".join(msg_parts)

    extra_data = {
        "error_type": error_type,
        "error_message": error_msg,
    }
    if operation:
        extra_data["operation"] = operation
    extra_data.update(context)

    logger.error(message, extra=extra_data, exc_info=True)
