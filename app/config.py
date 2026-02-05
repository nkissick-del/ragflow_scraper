"""
Configuration management for the PDF Scraper application.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", BASE_DIR / "config"))


def _parse_proxy_count(raw: str) -> int:
    """Validate TRUST_PROXY_COUNT as a bounded non-negative integer."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid Config.TRUST_PROXY_COUNT: must be an integer, got '{raw}'"
        )

    if value < 0 or value > 10:
        raise ValueError(
            f"Invalid Config.TRUST_PROXY_COUNT: must be between 0 and 10 inclusive, got '{value}'"
        )

    return value


def _parse_timeout(
    raw: str, param_name: str, min_val: int = 1, max_val: int = 600
) -> int:
    """Validate timeout parameter as a bounded positive integer.

    Args:
        raw: Raw value from environment variable
        param_name: Name of the parameter for error messages
        min_val: Minimum allowed value (default 1)
        max_val: Maximum allowed value (default 600)

    Returns:
        Validated integer timeout value

    Raises:
        ValueError: If value is not an integer or out of range
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid Config.{param_name}: must be an integer, got '{raw}'"
        )

    if value < min_val or value > max_val:
        raise ValueError(
            f"Invalid Config.{param_name}: must be between {min_val} and {max_val} inclusive, got '{value}'"
        )
    return value


class Config:
    """Application configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    BASIC_AUTH_ENABLED = os.getenv("BASIC_AUTH_ENABLED", "false").lower() == "true"
    BASIC_AUTH_USERNAME = os.getenv("BASIC_AUTH_USERNAME", "")
    BASIC_AUTH_PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "")

    # Paperless-ngx
    PAPERLESS_API_URL = os.getenv("PAPERLESS_API_URL", "http://localhost:8000")
    PAPERLESS_API_TOKEN = os.getenv("PAPERLESS_API_TOKEN", "")

    # RAGFlow
    RAGFLOW_API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
    RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "")
    RAGFLOW_DATASET_ID = os.getenv("RAGFLOW_DATASET_ID", "")

    # RAGFlow Session Auth (for model listing and admin APIs)
    RAGFLOW_USERNAME = os.getenv("RAGFLOW_USERNAME", "")
    RAGFLOW_PASSWORD = os.getenv("RAGFLOW_PASSWORD", "")

    # RAGFlow Metadata Settings
    RAGFLOW_PUSH_METADATA = os.getenv("RAGFLOW_PUSH_METADATA", "true").lower() == "true"
    RAGFLOW_METADATA_TIMEOUT = float(os.getenv("RAGFLOW_METADATA_TIMEOUT", "10.0"))
    RAGFLOW_METADATA_POLL_INTERVAL = float(
        os.getenv("RAGFLOW_METADATA_POLL_INTERVAL", "0.5")
    )
    RAGFLOW_METADATA_RETRIES = int(os.getenv("RAGFLOW_METADATA_RETRIES", "3"))
    RAGFLOW_CHECK_DUPLICATES = (
        os.getenv("RAGFLOW_CHECK_DUPLICATES", "true").lower() == "true"
    )

    # AnythingLLM (alternative RAG backend)
    ANYTHINGLLM_API_URL = os.getenv("ANYTHINGLLM_API_URL", "")
    ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
    ANYTHINGLLM_WORKSPACE_ID = os.getenv("ANYTHINGLLM_WORKSPACE_ID", "")

    # Backend Selection
    PARSER_BACKEND = (
        os.getenv("PARSER_BACKEND", "docling").strip().lower()
    )  # docling, mineru, tika
    ARCHIVE_BACKEND = (
        os.getenv("ARCHIVE_BACKEND", "paperless").strip().lower()
    )  # paperless, s3, local
    RAG_BACKEND = (
        os.getenv("RAG_BACKEND", "ragflow").strip().lower()
    )  # ragflow, anythingllm
    METADATA_MERGE_STRATEGY = (
        os.getenv("METADATA_MERGE_STRATEGY", "smart").strip().lower()
    )  # smart, parser_wins, scraper_wins

    # Selenium
    SELENIUM_REMOTE_URL = os.getenv(
        "SELENIUM_REMOTE_URL", "http://localhost:4444/wd/hub"
    )
    SELENIUM_HEADLESS = os.getenv("SELENIUM_HEADLESS", "true").lower() == "true"

    # FlareSolverr (enabled/disabled is controlled via UI settings, not env)
    FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "")
    FLARESOLVERR_TIMEOUT = _parse_timeout(
        os.getenv("FLARESOLVERR_TIMEOUT", "60"),
        "FLARESOLVERR_TIMEOUT",
        min_val=1,
        max_val=600,
    )
    FLARESOLVERR_MAX_TIMEOUT = _parse_timeout(
        os.getenv("FLARESOLVERR_MAX_TIMEOUT", "120"),
        "FLARESOLVERR_MAX_TIMEOUT",
        min_val=1,
        max_val=600,
    )

    # Guardian Open Platform API
    GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")

    # Directories
    DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", DATA_DIR / "scraped"))
    METADATA_DIR = Path(os.getenv("METADATA_DIR", DATA_DIR / "metadata"))
    STATE_DIR = Path(os.getenv("STATE_DIR", DATA_DIR / "state"))
    LOG_DIR = Path(os.getenv("LOG_DIR", DATA_DIR / "logs"))
    SCRAPERS_CONFIG_DIR = CONFIG_DIR / "scrapers"

    # Scraper settings
    MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 3))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 60))
    RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", 3))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_JSON_FORMAT = os.getenv("LOG_JSON_FORMAT", "true").lower() == "true"
    LOG_FILE_MAX_BYTES = int(os.getenv("LOG_FILE_MAX_BYTES", 10 * 1024 * 1024))
    LOG_FILE_BACKUP_COUNT = int(os.getenv("LOG_FILE_BACKUP_COUNT", 5))
    LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"

    # Proxy handling (for correct host/proto when behind reverse proxies)
    TRUST_PROXY_COUNT = _parse_proxy_count(os.getenv("TRUST_PROXY_COUNT", "0"))

    @classmethod
    def ensure_directories(cls):
        """Create required directories if they don't exist."""
        for dir_path in [
            cls.DOWNLOAD_DIR,
            cls.METADATA_DIR,
            cls.STATE_DIR,
            cls.LOG_DIR,
            cls.SCRAPERS_CONFIG_DIR,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls):
        """Validate config invariants and fail fast on misconfiguration."""
        if cls.BASIC_AUTH_ENABLED:
            if not cls.BASIC_AUTH_USERNAME or not cls.BASIC_AUTH_PASSWORD:
                raise ValueError(
                    "Invalid Config: BASIC_AUTH_ENABLED=true requires both BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD"
                )

        if cls.RAG_BACKEND == "anythingllm":
            if not cls.ANYTHINGLLM_API_URL or not cls.ANYTHINGLLM_API_KEY:
                raise ValueError(
                    "Invalid Config: RAG_BACKEND='anythingllm' requires both ANYTHINGLLM_API_URL and ANYTHINGLLM_API_KEY"
                )

        if cls.FLARESOLVERR_MAX_TIMEOUT < cls.FLARESOLVERR_TIMEOUT:
            raise ValueError(
                f"Invalid Config: FLARESOLVERR_MAX_TIMEOUT ({cls.FLARESOLVERR_MAX_TIMEOUT}) "
                f"must be greater than or equal to FLARESOLVERR_TIMEOUT ({cls.FLARESOLVERR_TIMEOUT})"
            )

        # Validate backend selections
        valid_parsers = ["docling", "mineru", "tika"]
        if cls.PARSER_BACKEND not in valid_parsers:
            raise ValueError(
                f"Invalid PARSER_BACKEND '{cls.PARSER_BACKEND}'. "
                f"Must be one of: {', '.join(valid_parsers)}"
            )

        valid_archives = ["paperless", "s3", "local"]
        if cls.ARCHIVE_BACKEND not in valid_archives:
            raise ValueError(
                f"Invalid ARCHIVE_BACKEND '{cls.ARCHIVE_BACKEND}'. "
                f"Must be one of: {', '.join(valid_archives)}"
            )

        valid_rags = ["ragflow", "anythingllm"]
        if cls.RAG_BACKEND not in valid_rags:
            raise ValueError(
                f"Invalid RAG_BACKEND '{cls.RAG_BACKEND}'. "
                f"Must be one of: {', '.join(valid_rags)}"
            )

        valid_strategies = ["smart", "parser_wins", "scraper_wins"]
        if cls.METADATA_MERGE_STRATEGY not in valid_strategies:
            raise ValueError(
                f"Invalid METADATA_MERGE_STRATEGY '{cls.METADATA_MERGE_STRATEGY}'. "
                f"Must be one of: {', '.join(valid_strategies)}"
            )

    @classmethod
    def get_scraper_config_path(cls, scraper_name: str) -> Path:
        """Get the configuration file path for a scraper."""
        return cls.SCRAPERS_CONFIG_DIR / f"{scraper_name}.json"


# Ensure directories exist on import
Config.ensure_directories()
Config.validate()
