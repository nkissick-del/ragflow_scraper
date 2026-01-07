import os
import shutil
import tempfile
from pathlib import Path

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
    """Session-scoped cleanup: shut down JobQueue gracefully at the end of all tests.
    
    This must be session-scoped to run AFTER all tests complete. The JobQueue
    is a singleton with a non-daemon worker thread, so we need to shut it down
    before pytest exits to avoid hanging.
    
    Semantics of shutdown(wait=True, timeout=5.0):
    - wait=True: Drain the queue (complete all pending jobs)
    - timeout=5.0: Wait up to 5 seconds for worker thread to terminate gracefully
    """
    yield  # Let all tests run first
    
    try:
        from app.web.runtime import job_queue
        try:
            logger = logging.getLogger("test.conftest")
            logger.debug("Session cleanup: Shutting down JobQueue with wait=True, timeout=5.0")
            job_queue.shutdown(wait=True, timeout=5.0)
        except Exception as exc:
            logger = logging.getLogger("test.conftest")
            logger.debug(f"JobQueue shutdown at session end raised exception: {exc}")
    except ImportError:
        # Runtime wasn't imported in this test session; no cleanup needed
        pass
    except Exception as exc:
        logger = logging.getLogger("test.conftest")
        logger.debug(f"Unexpected error in cleanup_job_queue_at_session_end: {exc}")
