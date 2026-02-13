"""Tests for app.utils.config_validation — JSON schema validation and migration helpers."""

import json

import pytest

from app.utils.config_validation import (
    DEFAULT_SETTINGS,
    SCRAPER_SCHEMA,
    SETTINGS_SCHEMA,
    _collect_errors,
    load_json,
    migrate_settings,
    validate_scraper,
    validate_scraper_file,
    validate_settings,
    validate_settings_file,
    write_json,
)
from jsonschema import Draft202012Validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_settings():
    """Return a minimal valid settings dict (deep copy of DEFAULT_SETTINGS)."""
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def _valid_scraper():
    """Return a minimal valid scraper config dict."""
    return {
        "name": "test_scraper",
        "description": "A test scraper",
        "enabled": True,
        "base_url": "https://example.com",
        "settings": {
            "documents_per_page": 10,
            "total_pages": 5,
            "request_delay": 1.0,
            "download_timeout": 30,
            "retry_attempts": 3,
        },
        "filters": {
            "excluded_tags": [],
            "include_extensions": [".pdf"],
            "min_file_size": None,
            "max_file_size": None,
        },
        "schedule": {
            "enabled": False,
            "cron": "0 0 * * *",
            "description": "Daily at midnight",
        },
    }


# ===========================================================================
# TestCollectErrors
# ===========================================================================
class TestCollectErrors:
    def test_valid_data_returns_empty_list(self):
        validator = Draft202012Validator(SETTINGS_SCHEMA)
        errors = _collect_errors(validator, _valid_settings())
        assert errors == []

    def test_invalid_data_returns_error_messages_with_paths(self):
        validator = Draft202012Validator(SETTINGS_SCHEMA)
        data = _valid_settings()
        data["flaresolverr"]["timeout"] = "not_a_number"
        errors = _collect_errors(validator, data)
        assert len(errors) > 0
        assert any("timeout" in e.lower() or "flaresolverr" in e.lower() for e in errors)


# ===========================================================================
# TestValidateSettings
# ===========================================================================
class TestValidateSettings:
    def test_valid_settings(self):
        errors = validate_settings(_valid_settings())
        assert errors == []

    def test_missing_required_section(self):
        data = _valid_settings()
        del data["scheduler"]
        errors = validate_settings(data)
        assert len(errors) > 0
        assert any("scheduler" in e.lower() for e in errors)

    def test_invalid_type_timeout_as_string(self):
        data = _valid_settings()
        data["scraping"]["default_timeout"] = "sixty"
        errors = validate_settings(data)
        assert len(errors) > 0


# ===========================================================================
# TestValidateScraper
# ===========================================================================
class TestValidateScraper:
    def test_valid_scraper_config(self):
        errors = validate_scraper(_valid_scraper())
        assert errors == []

    def test_missing_required_fields(self):
        data = _valid_scraper()
        del data["name"]
        del data["enabled"]
        errors = validate_scraper(data)
        assert len(errors) >= 2

    def test_invalid_name_empty_string(self):
        data = _valid_scraper()
        data["name"] = ""
        errors = validate_scraper(data)
        assert len(errors) > 0


# ===========================================================================
# TestValidateSettingsFile
# ===========================================================================
class TestValidateSettingsFile:
    def test_valid_file(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(_valid_settings()))
        data, errors = validate_settings_file(path)
        assert errors == []
        assert "flaresolverr" in data

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{bad json")
        with pytest.raises(json.JSONDecodeError):
            validate_settings_file(path)


# ===========================================================================
# TestValidateScraperFile
# ===========================================================================
class TestValidateScraperFile:
    def test_valid_file(self, tmp_path):
        path = tmp_path / "scraper.json"
        path.write_text(json.dumps(_valid_scraper()))
        data, errors = validate_scraper_file(path)
        assert errors == []
        assert data["name"] == "test_scraper"

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        with pytest.raises(json.JSONDecodeError):
            validate_scraper_file(path)


# ===========================================================================
# TestMigrateSettings
# ===========================================================================
class TestMigrateSettings:
    def test_empty_data_gets_defaults(self):
        result = migrate_settings({})
        assert result == DEFAULT_SETTINGS

    def test_partial_data_merged_with_defaults(self):
        result = migrate_settings({"scraping": {"default_timeout": 120}})
        # The partial section should be merged into the default section
        assert result["scraping"]["default_timeout"] == 120
        # Other keys in the section should still have defaults
        assert result["scraping"]["default_retry_attempts"] == 3

    def test_extra_keys_preserved(self):
        result = migrate_settings({"custom_section": "custom_value"})
        assert result["custom_section"] == "custom_value"
        # Defaults still present
        assert "flaresolverr" in result

    def test_nested_dict_updates_not_replaces(self):
        partial = {
            "ragflow": {
                "auto_upload": True,
            }
        }
        result = migrate_settings(partial)
        # The provided key should be updated
        assert result["ragflow"]["auto_upload"] is True
        # Other keys in ragflow should still have default values
        assert result["ragflow"]["default_chunk_method"] == "paper"
        assert result["ragflow"]["wait_for_parsing"] is False


# ===========================================================================
# TestLoadJson
# ===========================================================================
class TestLoadJson:
    def test_valid_json_file(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text('{"key": "value"}')
        result = load_json(path)
        assert result == {"key": "value"}

    def test_file_not_found_raises(self, tmp_path):
        path = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            load_json(path)


# ===========================================================================
# TestWriteJson
# ===========================================================================
class TestWriteJson:
    def test_writes_formatted_json(self, tmp_path):
        path = tmp_path / "output.json"
        data = {"key": "value", "nested": {"a": 1}}
        write_json(path, data)
        content = path.read_text()
        assert json.loads(content) == data
        # Should be indented (pretty-printed)
        assert "\n" in content

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "output.json"
        write_json(path, {"old": True})
        write_json(path, {"new": True})
        result = json.loads(path.read_text())
        assert result == {"new": True}
        assert "old" not in result
