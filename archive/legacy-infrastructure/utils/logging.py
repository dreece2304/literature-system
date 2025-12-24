"""
Logging configuration and utilities.

Provides structured logging with loguru, context tracking, and performance monitoring.
"""

import sys
import json
from typing import Dict, Any, Optional
from contextvars import ContextVar
from loguru import logger

from config.settings import settings


# Context variables for request tracking
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def serialize_record(record: Dict[str, Any]) -> str:
    """
    Serialize log record to JSON.

    Args:
        record: Log record dictionary

    Returns:
        JSON string
    """
    subset = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }

    # Add context if available
    if request_id := request_id_ctx.get():
        subset["request_id"] = request_id

    if user_id := user_id_ctx.get():
        subset["user_id"] = user_id

    # Add extra fields
    if record["extra"]:
        subset["extra"] = record["extra"]

    # Add exception if present
    if record["exception"]:
        subset["exception"] = {
            "type": record["exception"].type.__name__,
            "value": str(record["exception"].value),
            "traceback": record["exception"].traceback,
        }

    return json.dumps(subset)


def configure_logging():
    """Configure loguru logging based on settings."""
    # Remove default handler
    logger.remove()

    # Console handler (always enabled)
    if settings.logging.json_logs:
        # JSON format for production
        logger.add(
            sys.stderr,
            level=settings.logging.level,
            serialize=True,
        )
    else:
        # Pretty format for development
        logger.add(
            sys.stderr,
            level=settings.logging.level,
            format=settings.logging.format,
            colorize=True,
        )

    # File handler
    logger.add(
        settings.logging.log_file,
        level=settings.logging.level,
        format=settings.logging.format if not settings.logging.json_logs else serialize_record,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        compression=settings.logging.compression,
        enqueue=True,  # Async logging
    )

    logger.info(
        f"Logging configured: level={settings.logging.level}, "
        f"file={settings.logging.log_file}, json={settings.logging.json_logs}"
    )


def set_request_context(request_id: str, user_id: Optional[str] = None):
    """
    Set request context for structured logging.

    Args:
        request_id: Unique request identifier
        user_id: Optional user identifier
    """
    request_id_ctx.set(request_id)
    if user_id:
        user_id_ctx.set(user_id)


def clear_request_context():
    """Clear request context."""
    request_id_ctx.set(None)
    user_id_ctx.set(None)


def log_performance(operation: str, duration_ms: float, **kwargs):
    """
    Log performance metrics.

    Args:
        operation: Operation name
        duration_ms: Duration in milliseconds
        **kwargs: Additional context
    """
    logger.info(
        f"Performance: {operation}",
        extra={
            "operation": operation,
            "duration_ms": duration_ms,
            "metrics": kwargs,
        },
    )


def log_api_call(method: str, endpoint: str, status_code: int, duration_ms: float):
    """
    Log API call.

    Args:
        method: HTTP method
        endpoint: API endpoint
        status_code: Response status code
        duration_ms: Request duration in milliseconds
    """
    logger.info(
        f"API {method} {endpoint} -> {status_code}",
        extra={
            "api_call": True,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "duration_ms": duration_ms,
        },
    )


# Initialize logging on import
configure_logging()
