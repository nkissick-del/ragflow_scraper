"""
Logging configuration for the PDF Scraper application.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import Config


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

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        log_file = Config.LOG_DIR / f"{name}_{datetime.now():%Y%m%d}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
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
