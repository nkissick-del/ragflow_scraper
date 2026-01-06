from app.services.ragflow_metadata import validate_metadata
from app.services.settings_manager import SettingsManager
from app.utils.errors import ValidationError
import pytest


def test_settings_validation_rejects_invalid_timeout(monkeypatch, tmp_path):
    # SettingsManager is isolated via conftest to temp SETTINGS_FILE
    mgr = SettingsManager()

    # negative timeout should fail schema validation
    with pytest.raises(ValidationError):
        mgr.update_section("scraping", {"default_timeout": -5})


def test_metadata_validation_requires_required_fields():
    base = {
        "organization": "Org",
        "source_url": "http://example.com",
        "scraped_at": "2026-01-06T00:00:00Z",
        "document_type": "Report",
    }

    # Missing required field
    bad = base.copy()
    bad.pop("organization")
    with pytest.raises(ValueError):
        validate_metadata(bad)

    # Valid passes and preserves fields
    cleaned = validate_metadata(base)
    assert cleaned["organization"] == "Org"
    assert "publication_date" not in cleaned
