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
    """Session-scoped cleanup: shut down ALL JobQueue instances at the end of tests.
    
    This must be session-scoped to run AFTER all tests complete. Tests may create
    multiple JobQueue instances (especially test_job_queue.py), and each has a 
    non-daemon worker thread. We must shut down ALL of them before pytest exits.
    
    Semantics of shutdown(wait=True, timeout=5.0):
    - wait=True: Drain the queue (complete all pending jobs)
    - timeout=5.0: Wait up to 5 seconds for worker thread to terminate gracefully
    
    If ANY worker thread doesn't exit after timeout, this fixture will force exit
    the pytest process to prevent hanging indefinitely.
    """
    yield  # Let all tests run first
    
    logger = logging.getLogger("test.conftest")
    logger.debug("=== Session teardown: Starting JobQueue cleanup ===")
    
    try:
        from app.web.job_queue import _instances
        
        # Shut down ALL JobQueue instances, not just the global one
        queues_to_shutdown = list(_instances)  # Make a copy since _instances is weak
        logger.debug(f"Found {len(queues_to_shutdown)} JobQueue instances to shutdown")
        
        for i, queue in enumerate(queues_to_shutdown):
            try:
                logger.debug(f"Shutting down JobQueue instance {i+1}/{len(queues_to_shutdown)}")
                queue.shutdown(wait=True, timeout=2.0)
            except Exception as exc:
                logger.debug(f"JobQueue #{i+1} shutdown raised: {exc}")
        
        logger.debug(f"Active threads after shutdown: {[t.name for t in threading.enumerate()]}")
        
        # Check if worker threads actually exited
        worker_threads = [t for t in threading.enumerate() 
                         if '_worker_loop' in t.name and not t.daemon]
        if worker_threads:
            logger.warning(f"{len(worker_threads)} worker threads still alive after shutdown")
            logger.warning("Forcing pytest to exit to avoid hanging indefinitely...")
            # Give threads 2 more seconds, then force exit
            for _ in range(20):  # 2 seconds with 0.1s checks
                if not any(t for t in threading.enumerate() 
                          if '_worker_loop' in t.name and not t.daemon):
                    logger.debug("All worker threads finally exited")
                    break
                sys.stderr.flush()
                sys.stdout.flush()
                threading.Event().wait(0.1)
            else:
                logger.error(f"Worker threads STILL alive - forcing pytest exit!")
                sys.exit(0)  # Hard exit to prevent hanging
        
        logger.debug("=== Session teardown: JobQueue cleanup finished ===")
        
    except ImportError as exc:
        logger.debug(f"Could not import JobQueue cleanup (expected for minimal tests): {exc}")
        
    except Exception as exc:
        logger.debug(f"Unexpected error in cleanup_job_queue_at_session_end: {exc}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")


def pytest_sessionfinish(session, exitstatus):
    """Hook that runs after the entire test session ends, before pytest exits.
    
    With daemon=True for test JobQueues, we don't need to force exit.
    Just verify cleanup happened.
    """
    logger = logging.getLogger("test.conftest")
    
    non_daemon_threads = [t for t in threading.enumerate() if not t.daemon and t.name != 'MainThread']
    
    if non_daemon_threads:
        logger.error(f"WARNING: {len(non_daemon_threads)} non-daemon threads still alive!")
        for t in non_daemon_threads:
            logger.error(f"  - {t.name}")
    else:
        logger.debug("All non-daemon threads cleaned up successfully")
