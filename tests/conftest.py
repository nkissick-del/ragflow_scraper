import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.config import Config
import app.services.settings_manager as settings_manager


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
