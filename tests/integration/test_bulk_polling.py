"""Integration tests for aggregate (bulk) scraper status polling endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from app.config import Config
from app.web import create_app


FAKE_SCRAPERS = [
    {
        "name": "alpha",
        "description": "Alpha scraper",
        "base_url": "https://alpha.example.com",
        "default_chunk_method": "naive",
        "default_parser": "DeepDOC",
    },
    {
        "name": "beta",
        "description": "Beta scraper",
        "base_url": "https://beta.example.com",
        "default_chunk_method": "naive",
        "default_parser": "DeepDOC",
    },
]


def _make_mock_state():
    state = MagicMock()
    state.get_last_run_info.return_value = {
        "processed_count": 5,
        "last_updated": "2026-01-01T00:00:00",
        "statistics": {
            "total_downloaded": 5,
            "total_skipped": 0,
            "total_failed": 0,
        },
    }
    return state


@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value = _make_mock_state()
    mock_container.settings.get_scraper_cloudflare_enabled.return_value = False
    mock_container.settings.get_scraper_ragflow_settings.return_value = {
        "ingestion_mode": "builtin",
        "chunk_method": "naive",
        "pdf_parser": "DeepDOC",
        "embedding_model": "",
        "pipeline_id": "",
    }

    mock_job_queue = MagicMock()
    mock_job_queue.status.return_value = "idle"

    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue", mock_job_queue),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue", mock_job_queue),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        application = create_app()
        application.config["TESTING"] = True
        application.config["WTF_CSRF_ENABLED"] = False
        application.config["RATELIMIT_ENABLED"] = False
        yield application
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestBulkCardPolling:
    """Tests for GET /scrapers/cards/bulk (dashboard bulk card poller)."""

    def test_returns_200(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/cards/bulk")
            assert resp.status_code == 200

    def test_oob_attributes_present(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/cards/bulk")
            html = resp.data.decode()
            assert 'hx-swap-oob="true"' in html

    def test_all_scraper_ids_present(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/cards/bulk")
            html = resp.data.decode()
            assert 'id="scraper-alpha"' in html
            assert 'id="scraper-beta"' in html

    def test_no_self_polling(self, client):
        """Bulk cards should NOT contain per-card self-polling triggers."""
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/cards/bulk")
            html = resp.data.decode()
            assert "every 5s" not in html

    def test_empty_scrapers(self, client):
        """Bulk endpoint with no scrapers returns 200 with empty body."""
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=[],
        ):
            resp = client.get("/scrapers/cards/bulk")
            assert resp.status_code == 200
            assert resp.data.decode().strip() == ""


class TestBulkStatusPolling:
    """Tests for GET /scrapers/status/bulk (scrapers page bulk status poller)."""

    def test_returns_200(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/status/bulk")
            assert resp.status_code == 200

    def test_oob_attributes_present(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/status/bulk")
            html = resp.data.decode()
            assert 'hx-swap-oob="true"' in html

    def test_all_badge_ids_present(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/status/bulk")
            html = resp.data.decode()
            assert 'id="status-badge-alpha"' in html
            assert 'id="status-badge-beta"' in html

    def test_no_self_polling(self, client):
        """Bulk badges should NOT contain per-badge self-polling triggers."""
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=FAKE_SCRAPERS,
        ):
            resp = client.get("/scrapers/status/bulk")
            html = resp.data.decode()
            assert "every 5s" not in html

    def test_empty_scrapers(self, client):
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.list_scrapers",
            return_value=[],
        ):
            resp = client.get("/scrapers/status/bulk")
            assert resp.status_code == 200
            assert resp.data.decode().strip() == ""


class TestIndividualEndpointsUnchanged:
    """Verify individual card/status endpoints still work without OOB."""

    def test_individual_status_no_oob(self, client):
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "alpha"}
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class",
            return_value=mock_class,
        ):
            resp = client.get("/scrapers/alpha/status")
            assert resp.status_code == 200
            html = resp.data.decode()
            assert "hx-swap-oob" not in html

    def test_individual_card_no_oob(self, client):
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {
            "name": "alpha",
            "description": "Alpha",
            "status": "idle",
            "state": None,
        }
        with patch(
            "app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class",
            return_value=mock_class,
        ):
            resp = client.get("/scrapers/alpha/card")
            assert resp.status_code == 200
            html = resp.data.decode()
            assert "hx-swap-oob" not in html
