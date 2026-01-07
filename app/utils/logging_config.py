"""
Logging configuration for the PDF Scraper application.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

from app.config import Config


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "lineno": record.lineno,
        }

        # Include exception info when present
        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        # Preserve any structured extras on the record (passed via `extra={...}`)
        extra_payload = getattr(record, "extra", None)
        if isinstance(extra_payload, dict):
            log_entry.update(extra_payload)

        return json.dumps(log_entry, ensure_ascii=True)


def setup_logging(
    name: str = "scraper",
    level: Optional[str] = None,
    log_to_file: bool = True,
) -> logging.Logger:
    """
    Set up logging with console and optional file output.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to also log to a file

    Returns:
        Configured logger instance
    """
    level = level or Config.LOG_LEVEL
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console handler (human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with rotation and optional JSON format
    if log_to_file and Config.LOG_TO_FILE:
        log_file = Config.LOG_DIR / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=Config.LOG_FILE_MAX_BYTES,
            backupCount=Config.LOG_FILE_BACKUP_COUNT,
        )
        file_handler.setLevel(getattr(logging, level.upper()))

        if Config.LOG_JSON_FORMAT:
            file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        else:
            file_format = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_format)

        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with the given name.

    Args:
        name: Logger name (will be prefixed with 'scraper.')

    Returns:
        Logger instance
    """
    full_name = f"scraper.{name}" if not name.startswith("scraper") else name
    logger = logging.getLogger(full_name)

    # If parent logger is set up, this logger inherits its configuration
    if not logger.handlers and not logging.getLogger("scraper").handlers:
        setup_logging()

    return logger


def log_exception(logger: logging.Logger, exc: BaseException, message: str, **context: Any) -> None:
    """Log exceptions with structured context and full traceback."""
    logger.error(
        message,
        exc_info=exc,
        extra={"extra": context} if context else None,
    )


def log_event(logger: logging.Logger, level: str, message: str, **context: Any) -> None:
    """Emit a structured log event with optional context payload."""
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message, extra={"extra": context} if context else None)
