import os
import shutil
import tempfile
from pathlib import Path
import sys
import threading

import pytest
import logging

# Import application config and settings manager if available. During lightweight
# test runs (e.g. CI without all env deps) these imports can fail; in that
# case provide minimal stubs so tests that don't rely on full runtime still run.
try:
    from app.config import Config
    import app.services.settings_manager as settings_manager
except (ImportError, ModuleNotFoundError):
    logging.info("Using stub Config and settings_manager (real modules not available)")

    class _StubConfig:
        DOWNLOAD_DIR = Path("data/scraped")
        METADATA_DIR = Path("data/metadata")
        STATE_DIR = Path("data/state")
        LOG_DIR = Path("data/logs")
        SCRAPERS_CONFIG_DIR = Path("config") / "scrapers"

        @classmethod
        def ensure_directories(cls):
            for d in [
                cls.DOWNLOAD_DIR,
                cls.METADATA_DIR,
                cls.STATE_DIR,
                cls.LOG_DIR,
                cls.SCRAPERS_CONFIG_DIR,
            ]:
                d.mkdir(parents=True, exist_ok=True)

    class _StubSettingsManager:
        """Lightweight stub mirroring the real SettingsManager API."""
        _instance = None

    Config = _StubConfig
    settings_manager = type('settings_manager', (), {
        'SETTINGS_FILE': Config.SCRAPERS_CONFIG_DIR / "settings.json",
        '_settings_manager': None,
        'SettingsManager': _StubSettingsManager,
    })()


@pytest.fixture
def temp_data_dir():
    """Create an isolated temporary data directory for tests."""
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, temp_data_dir):
    """Redirect Config paths and settings file into the temp directory."""
    monkeypatch.setattr(Config, "DOWNLOAD_DIR", temp_data_dir / "scraped")
    monkeypatch.setattr(Config, "METADATA_DIR", temp_data_dir / "metadata")
    monkeypatch.setattr(Config, "STATE_DIR", temp_data_dir / "state")
    monkeypatch.setattr(Config, "LOG_DIR", temp_data_dir / "logs")
    monkeypatch.setattr(Config, "SCRAPERS_CONFIG_DIR", temp_data_dir / "config" / "scrapers")

    settings_file = temp_data_dir / "config" / "settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings_manager, "SETTINGS_FILE", settings_file)
    settings_manager._settings_manager = None
    settings_manager.SettingsManager._instance = None

    Config.ensure_directories()
    yield


@pytest.fixture
def reset_registry():
    """Reset the scraper registry before and after a test."""
    from app.scrapers.scraper_registry import ScraperRegistry

    ScraperRegistry.reset()
    yield
    ScraperRegistry.reset()


RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS", "0") == "1"


@pytest.fixture(scope="session", autouse=True)
def cleanup_job_queue_at_session_end():
    """Session-scoped cleanup for JobQueue.
    
    During testing, JobQueue instances use daemon=True (set via PYTEST_CURRENT_TEST
    env var detection in app/web/runtime.py). Daemon threads are automatically killed
    when pytest exits, so we don't need explicit shutdown cleanup.
    
    This fixture exists as a safety net for debugging if needed.
    """
    yield  # Let all tests run first
    
    logger = logging.getLogger("test.conftest")
    logger.debug("Session teardown: Tests completed, daemon threads will auto-cleanup")


def pytest_sessionfinish(session, exitstatus):
    """Hook that runs after the entire test session ends.
    
    With daemon threads, we don't need to do anything - they'll be killed
    automatically by Python when pytest exits.
    
    Force an explicit exit to prevent hanging in container environments.
    """
    # Force pytest to exit immediately - prevents hanging in Docker/container environments
    # where background processes or event loops might otherwise keep the process alive
    sys.exit(exitstatus)
