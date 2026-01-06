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


class Config:
    """Application configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

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
    RAGFLOW_METADATA_POLL_INTERVAL = float(os.getenv("RAGFLOW_METADATA_POLL_INTERVAL", "0.5"))
    RAGFLOW_METADATA_RETRIES = int(os.getenv("RAGFLOW_METADATA_RETRIES", "3"))
    RAGFLOW_CHECK_DUPLICATES = os.getenv("RAGFLOW_CHECK_DUPLICATES", "true").lower() == "true"

    # Selenium
    SELENIUM_REMOTE_URL = os.getenv("SELENIUM_REMOTE_URL", "http://localhost:4444/wd/hub")
    SELENIUM_HEADLESS = os.getenv("SELENIUM_HEADLESS", "true").lower() == "true"

    # FlareSolverr (enabled/disabled is controlled via UI settings, not env)
    FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "")

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
    def get_scraper_config_path(cls, scraper_name: str) -> Path:
        """Get the configuration file path for a scraper."""
        return cls.SCRAPERS_CONFIG_DIR / f"{scraper_name}.json"


# Ensure directories exist on import
Config.ensure_directories()
