"""Logging configuration for RFMP daemon."""

import logging
import logging.handlers
import structlog
from pathlib import Path
from typing import Optional


def setup_logging(log_level: str = "INFO",
                   log_file: Optional[str] = None,
                   max_size: int = 10485760,
                   backup_count: int = 5):
    """
    Set up logging configuration.

    Args:
        log_level: Logging level
        log_file: Optional log file path
        max_size: Maximum log file size in bytes
        backup_count: Number of backup files to keep
    """
    # Configure standard logging
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers
    )

    # Configure structlog for structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.dict_tracebacks,
            structlog.dev.ConsoleRenderer() if log_level == "DEBUG" else structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)