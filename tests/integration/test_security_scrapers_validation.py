"""Integration tests for scraper blueprint input validation."""

import pytest
from unittest.mock import patch, MagicMock
from app.config import Config
from app.web import create_app


@pytest.fixture
def app():
    """Create test Flask app with CSRF disabled for validation testing."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.settings.flaresolverr_enabled = True
    mock_container.state_tracker.return_value.get_all_status.return_value = {}

    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
        patch.object(Config, "FLARESOLVERR_URL", "http://localhost:8191"),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        yield app
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestScraperValidation:

    def test_toggle_non_existent_scraper(self, client):
        """Test that toggle_scraper_cloudflare rejects non-existent scrapers."""
        response = client.post(
            "/scrapers/non_existent_scraper/cloudflare",
            data={"enabled": "on"},
        )
        assert response.status_code == 404
        assert b"Not found" in response.data

    def test_toggle_invalid_scraper_name(self, client):
        """Test that toggle_scraper_cloudflare rejects invalid name format."""
        response = client.post(
            "/scrapers/invalid@name/cloudflare",
            data={"enabled": "on"},
        )
        assert response.status_code == 400
        assert b"Invalid name" in response.data

    def test_run_scraper_invalid_max_pages(self, client):
        """Test that run_scraper rejects negative max_pages."""
        response = client.post(
            "/scrapers/some_scraper/run",
            data={"max_pages": "-5", "dry_run": "true"},
        )
        assert response.status_code == 400
        assert response.json["error"] == "max_pages must be positive"

    def test_run_scraper_invalid_name(self, client):
        """Test that run_scraper rejects invalid name format."""
        response = client.post(
            "/scrapers/invalid@name/run",
            data={"max_pages": "1"},
        )
        assert response.status_code == 400
        assert response.json["error"] == "Invalid scraper name format"

    def test_preview_scraper_invalid_name(self, client):
        """Test that preview_scraper rejects invalid name format."""
        response = client.post(
            "/scrapers/invalid@name/preview",
            data={"max_pages": "1"},
        )
        assert response.status_code == 400
        assert response.json["error"] == "Invalid scraper name format"

    def test_ragflow_settings_non_existent_scraper(self, client):
        """Test that save_scraper_ragflow_settings rejects non-existent scrapers."""
        response = client.post(
            "/scrapers/non_existent_scraper/ragflow",
            data={"chunk_method": "paper"},
        )
        assert response.status_code == 404
