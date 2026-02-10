"""Unit tests for SettingsManager."""

from __future__ import annotations

import copy
import json
import pytest
from unittest.mock import patch

from app.services.settings_manager import (
    SettingsManager,
    get_settings,
    DEFAULT_SETTINGS,
)
from app.utils.errors import ValidationError

# Deep-copy the original defaults so we can restore after each test
_ORIGINAL_DEFAULTS = copy.deepcopy(DEFAULT_SETTINGS)


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    """Reset SettingsManager singleton and redirect file to tmp_path."""
    sf = tmp_path / "settings.json"
    monkeypatch.setattr("app.services.settings_manager.SETTINGS_FILE", sf)
    # Restore DEFAULT_SETTINGS to pristine state (shallow copy mutates nested dicts)
    import app.services.settings_manager as sm
    sm.DEFAULT_SETTINGS.clear()
    sm.DEFAULT_SETTINGS.update(copy.deepcopy(_ORIGINAL_DEFAULTS))
    SettingsManager._instance = None
    SettingsManager._settings = None
    yield sf
    SettingsManager._instance = None
    SettingsManager._settings = None
    # Restore again on teardown
    sm.DEFAULT_SETTINGS.clear()
    sm.DEFAULT_SETTINGS.update(copy.deepcopy(_ORIGINAL_DEFAULTS))


# ── TestSingleton ───────────────────────────────────────────────────────


class TestSingleton:
    """Tests for singleton pattern."""

    def test_same_instance_returned(self, settings_file):
        """Two SettingsManager() calls return same instance."""
        a = SettingsManager()
        b = SettingsManager()
        assert a is b

    def test_get_settings_matches(self, settings_file):
        """get_settings() returns the singleton."""
        # Also reset the module-level global
        import app.services.settings_manager as sm
        sm._settings_manager = None

        s = get_settings()
        assert isinstance(s, SettingsManager)


# ── TestLoad ────────────────────────────────────────────────────────────


class TestLoad:
    """Tests for _load() behavior."""

    def test_creates_defaults_when_no_file(self, settings_file):
        """Creates settings file with defaults when none exists."""
        SettingsManager()

        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "flaresolverr" in data

    def test_reads_existing_file(self, settings_file):
        """Reads settings from existing JSON file."""
        custom = copy.deepcopy(DEFAULT_SETTINGS)
        custom["flaresolverr"]["timeout"] = 999
        settings_file.write_text(json.dumps(custom))

        mgr = SettingsManager()

        assert mgr.get("flaresolverr.timeout") == 999

    def test_invalid_json_falls_back_to_defaults(self, settings_file):
        """Falls back to defaults on malformed JSON."""
        settings_file.write_text("{invalid json")

        mgr = SettingsManager()

        assert mgr.get("flaresolverr.timeout") == 60

    def test_schema_validation_failure_falls_back(self, settings_file):
        """Falls back to defaults when schema validation fails."""
        bad = copy.deepcopy(DEFAULT_SETTINGS)
        bad["flaresolverr"]["timeout"] = "not_a_number"
        settings_file.write_text(json.dumps(bad))

        mgr = SettingsManager()

        assert mgr.get("flaresolverr.timeout") == 60


# ── TestSave ────────────────────────────────────────────────────────────


class TestSave:
    """Tests for _save() behavior."""

    def test_writes_valid_json(self, settings_file):
        """Saves valid JSON to file."""
        mgr = SettingsManager()
        mgr.set("flaresolverr.timeout", 42)

        data = json.loads(settings_file.read_text())
        assert data["flaresolverr"]["timeout"] == 42

    def test_rejects_invalid_settings(self, settings_file):
        """Raises ValidationError for invalid settings."""
        mgr = SettingsManager()
        mgr._settings["flaresolverr"]["timeout"] = "bad"

        with pytest.raises(ValidationError):
            mgr._save()


# ── TestDotNotationGetSet ───────────────────────────────────────────────


class TestDotNotationGetSet:
    """Tests for get() and set() with dot-notation keys."""

    def test_existing_key(self, settings_file):
        """Gets value for existing key."""
        mgr = SettingsManager()
        assert mgr.get("flaresolverr.enabled") is False

    def test_missing_key_returns_default(self, settings_file):
        """Returns default for missing key."""
        mgr = SettingsManager()
        assert mgr.get("nonexistent.key", "fallback") == "fallback"

    def test_set_creates_nested_keys(self, settings_file):
        """Setting a deep key creates intermediate dicts."""
        mgr = SettingsManager()
        mgr.set("scrapers.test_scraper.cloudflare_enabled", True)

        assert mgr.get("scrapers.test_scraper.cloudflare_enabled") is True

    def test_set_persists_to_file(self, settings_file):
        """set() writes to disk."""
        mgr = SettingsManager()
        mgr.set("flaresolverr.timeout", 77)

        data = json.loads(settings_file.read_text())
        assert data["flaresolverr"]["timeout"] == 77


# ── TestSections ────────────────────────────────────────────────────────


class TestSections:
    """Tests for get_section() and update_section()."""

    def test_get_section_returns_copy(self, settings_file):
        """get_section() returns a copy, not a reference."""
        mgr = SettingsManager()
        section = mgr.get_section("flaresolverr")

        section["timeout"] = 999
        assert mgr.get("flaresolverr.timeout") != 999

    def test_update_section_merges_values(self, settings_file):
        """update_section() merges new values."""
        mgr = SettingsManager()
        mgr.update_section("flaresolverr", {"timeout": 30, "enabled": True})

        assert mgr.get("flaresolverr.timeout") == 30
        assert mgr.get("flaresolverr.enabled") is True


# ── TestMergeDefaults ───────────────────────────────────────────────────


class TestMergeDefaults:
    """Tests for _merge_defaults()."""

    def test_fills_missing_keys(self, settings_file):
        """Missing keys are filled from defaults."""
        mgr = SettingsManager()
        partial = {"flaresolverr": {"timeout": 99}}
        result = mgr._merge_defaults(partial, DEFAULT_SETTINGS)

        # Custom value preserved
        assert result["flaresolverr"]["timeout"] == 99
        # Missing key filled
        assert result["flaresolverr"]["enabled"] is False
        # Other sections filled
        assert "ragflow" in result

    def test_preserves_existing_values(self, settings_file):
        """Existing values are not overwritten."""
        mgr = SettingsManager()
        full = copy.deepcopy(DEFAULT_SETTINGS)
        full["flaresolverr"]["timeout"] = 42
        result = mgr._merge_defaults(full, DEFAULT_SETTINGS)

        assert result["flaresolverr"]["timeout"] == 42


# ── TestProperties ──────────────────────────────────────────────────────


class TestProperties:
    """Tests for convenience properties."""

    @patch("app.services.settings_manager.Config")
    def test_flaresolverr_enabled_requires_url(self, mock_config, settings_file):
        """flaresolverr_enabled requires both setting=True and Config URL."""
        mock_config.FLARESOLVERR_URL = "http://flaresolverr:8191"

        mgr = SettingsManager()
        mgr.set("flaresolverr.enabled", True)

        assert mgr.flaresolverr_enabled is True

    @patch("app.services.settings_manager.Config")
    def test_flaresolverr_disabled_without_url(self, mock_config, settings_file):
        """flaresolverr_enabled is False without URL."""
        mock_config.FLARESOLVERR_URL = ""

        mgr = SettingsManager()
        mgr.set("flaresolverr.enabled", True)

        assert mgr.flaresolverr_enabled is False

    @patch("app.services.settings_manager.Config")
    def test_ragflow_session_configured(self, mock_config, settings_file):
        """ragflow_session_configured checks Config credentials."""
        mock_config.RAGFLOW_USERNAME = "user"
        mock_config.RAGFLOW_PASSWORD = "pass"

        mgr = SettingsManager()
        assert mgr.ragflow_session_configured is True


# ── TestScraperSettings ─────────────────────────────────────────────────


class TestScraperSettings:
    """Tests for per-scraper settings."""

    @patch("app.services.settings_manager.Config")
    def test_get_set_cloudflare_enabled(self, mock_config, settings_file):
        """set/get scraper cloudflare enabled."""
        mock_config.FLARESOLVERR_URL = "http://flaresolverr:8191"

        mgr = SettingsManager()
        mgr.set("flaresolverr.enabled", True)
        mgr.set_scraper_cloudflare_enabled("aemo", True)

        assert mgr.get_scraper_cloudflare_enabled("aemo") is True

    def test_get_scraper_ragflow_settings_with_fallbacks(self, settings_file):
        """get_scraper_ragflow_settings falls back to global defaults."""
        mgr = SettingsManager()
        mgr.update_section("ragflow", {"default_dataset_id": "global-ds"})

        settings = mgr.get_scraper_ragflow_settings("aemo")

        assert settings["dataset_id"] == "global-ds"
        assert settings["chunk_method"] == "paper"  # default
