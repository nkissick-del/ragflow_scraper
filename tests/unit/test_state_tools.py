"""Tests for app.utils.state_tools — state validation, repair, and reporting."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.state_tools import (
    STATE_TEMPLATE,
    _fresh_state,
    _is_int,
    build_state_report,
    load_state_file,
    repair_state_dict,
    scan_state_files,
    summarize_state,
    validate_state_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_state(scraper_name="test"):
    """Return a minimal valid state dict."""
    return {
        "scraper_name": scraper_name,
        "created_at": "2026-01-01T00:00:00",
        "last_updated": "2026-01-02T00:00:00",
        "processed_urls": {
            "https://example.com/a.pdf": {"status": "downloaded"},
        },
        "statistics": {
            "total_processed": 5,
            "total_downloaded": 3,
            "total_skipped": 1,
            "total_failed": 1,
        },
    }


# ===========================================================================
# TestFreshState
# ===========================================================================
class TestFreshState:
    def test_has_required_keys(self):
        state = _fresh_state("my_scraper")
        for key in STATE_TEMPLATE:
            assert key in state

    def test_sets_scraper_name_and_created_at(self):
        state = _fresh_state("my_scraper")
        assert state["scraper_name"] == "my_scraper"
        assert isinstance(state["created_at"], str)
        assert len(state["created_at"]) > 0


# ===========================================================================
# TestIsInt
# ===========================================================================
class TestIsInt:
    def test_valid_int(self):
        assert _is_int(42) is True

    def test_valid_string_int(self):
        assert _is_int("123") is True

    def test_invalid_values(self):
        assert _is_int(None) is False
        assert _is_int("abc") is False
        assert _is_int(3.14) is True  # int(3.14) succeeds -> True


# ===========================================================================
# TestValidateStateDict
# ===========================================================================
class TestValidateStateDict:
    def test_valid_state_returns_empty(self):
        errors = validate_state_dict(_make_valid_state("test"), "test")
        assert errors == []

    def test_non_dict_returns_error(self):
        errors = validate_state_dict("not a dict", "test")  # type: ignore[arg-type]
        assert errors == ["State is not a JSON object"]

    def test_wrong_scraper_name(self):
        state = _make_valid_state("other_scraper")
        errors = validate_state_dict(state, "test")
        assert len(errors) == 1
        assert "scraper_name" in errors[0]

    def test_invalid_stats_non_integer(self):
        state = _make_valid_state("test")
        state["statistics"]["total_processed"] = "not_a_number"
        errors = validate_state_dict(state, "test")
        assert any("total_processed" in e for e in errors)

    def test_invalid_created_at_type(self):
        state = _make_valid_state("test")
        state["created_at"] = 12345
        errors = validate_state_dict(state, "test")
        assert any("created_at" in e for e in errors)


# ===========================================================================
# TestRepairStateDict
# ===========================================================================
class TestRepairStateDict:
    def test_repairs_missing_keys(self):
        state = {"scraper_name": "test"}
        repaired = repair_state_dict(state, "test")
        for key in STATE_TEMPLATE:
            assert key in repaired

    def test_preserves_created_at(self):
        state = _make_valid_state("test")
        original_created = state["created_at"]
        repaired = repair_state_dict(state, "test")
        assert repaired["created_at"] == original_created

    def test_coerces_negative_stats_to_zero(self):
        state = _make_valid_state("test")
        state["statistics"]["total_processed"] = -5
        repaired = repair_state_dict(state, "test")
        assert repaired["statistics"]["total_processed"] == 0

    def test_handles_non_dict_stats(self):
        state = _make_valid_state("test")
        state["statistics"] = "broken"
        repaired = repair_state_dict(state, "test")
        # Should fall back to template defaults
        assert isinstance(repaired["statistics"], dict)
        assert repaired["statistics"]["total_processed"] == 0

    def test_preserves_auxiliary_keys(self):
        state = _make_valid_state("test")
        state["custom_field"] = "custom_value"
        repaired = repair_state_dict(state, "test")
        assert repaired["custom_field"] == "custom_value"


# ===========================================================================
# TestSummarizeState
# ===========================================================================
class TestSummarizeState:
    def test_with_data(self):
        state = _make_valid_state("test")
        summary = summarize_state(state)
        assert summary["processed_count"] == 1  # one URL in processed_urls
        assert summary["statistics"]["total_processed"] == 5

    def test_empty_or_non_dict_state(self):
        summary = summarize_state("not a dict")  # type: ignore[arg-type]
        assert summary["processed_count"] == 0
        assert summary["statistics"]["total_processed"] == 0


# ===========================================================================
# TestLoadStateFile
# ===========================================================================
class TestLoadStateFile:
    def test_valid_file(self, tmp_path):
        path = tmp_path / "test_state.json"
        state = _make_valid_state("test")
        path.write_text(json.dumps(state))
        data, errors = load_state_file(path)
        assert data == state
        assert errors == []

    def test_file_not_found(self, tmp_path):
        path = tmp_path / "missing_state.json"
        data, errors = load_state_file(path)
        assert data == {}
        assert "File not found" in errors

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "broken_state.json"
        path.write_text("{bad json")
        data, errors = load_state_file(path)
        assert data == {}
        assert any("JSON decode error" in e for e in errors)


# ===========================================================================
# TestScanStateFiles
# ===========================================================================
class TestScanStateFiles:
    def test_finds_matching_files(self, tmp_path):
        (tmp_path / "aemo_state.json").write_text("{}")
        (tmp_path / "guardian_state.json").write_text("{}")
        (tmp_path / "other_config.json").write_text("{}")
        with patch("app.utils.state_tools.Config") as MockConfig:
            MockConfig.STATE_DIR = tmp_path
            files = scan_state_files()
        assert len(files) == 2
        names = [f.name for f in files]
        assert "aemo_state.json" in names
        assert "guardian_state.json" in names

    def test_specific_scraper_filter(self, tmp_path):
        (tmp_path / "aemo_state.json").write_text("{}")
        (tmp_path / "guardian_state.json").write_text("{}")
        with patch("app.utils.state_tools.Config") as MockConfig:
            MockConfig.STATE_DIR = tmp_path
            files = scan_state_files(scraper="aemo")
        assert len(files) == 1
        assert files[0].name == "aemo_state.json"


# ===========================================================================
# TestBuildStateReport
# ===========================================================================
class TestBuildStateReport:
    def test_basic_report(self, tmp_path):
        path = tmp_path / "test_state.json"
        state = _make_valid_state("test")
        path.write_text(json.dumps(state))
        report = build_state_report(path)
        assert report["scraper"] == "test"
        assert report["errors"] == []
        assert report["hash"] is not None
        assert report["repaired"] is False

    def test_with_repair(self, tmp_path):
        path = tmp_path / "test_state.json"
        state = {"scraper_name": "test", "statistics": {"total_processed": -3}}
        path.write_text(json.dumps(state))
        report = build_state_report(path, repair=True)
        assert report["repaired"] is True

    def test_with_repair_and_write(self, tmp_path):
        path = tmp_path / "test_state.json"
        state = {"scraper_name": "test", "statistics": {"total_processed": -3}}
        path.write_text(json.dumps(state))
        report = build_state_report(path, repair=True, write=True)
        assert report["repaired"] is True
        # File should have been rewritten with repaired state
        written = json.loads(path.read_text())
        assert written["statistics"]["total_processed"] == 0
