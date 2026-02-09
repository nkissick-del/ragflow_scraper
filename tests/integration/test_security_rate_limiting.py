"""Integration tests for rate limiting."""

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


@pytest.fixture
def app():
    """Create app with rate limiting ENABLED."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    mock_container.embedding_client.is_configured.return_value = True
    mock_container.embedding_client.embed_single.return_value = [0.1] * 384
    mock_container.pgvector_client.is_configured.return_value = True
    mock_container.pgvector_client.search.return_value = []
    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.blueprints.search.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        application = create_app()
        application.config["TESTING"] = True
        application.config["WTF_CSRF_ENABLED"] = False
        # Rate limiting is ON (default)
        yield application
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestRateLimiting:

    def test_scraper_run_rate_limited(self, client):
        """11th POST to /scrapers/<name>/run in a minute should return 429."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_cls, \
             patch("app.web.blueprints.scrapers.container") as mock_ctr, \
             patch("app.web.blueprints.scrapers.job_queue") as mock_queue:
            mock_get.return_value = MagicMock()
            mock_cls.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
            mock_queue.enqueue.return_value = None
            mock_queue.status.return_value = "queued"
            mock_ctr.state_tracker.return_value.get_last_run_info.return_value = {}

            for i in range(10):
                resp = client.post("/scrapers/test_scraper/run")
                assert resp.status_code == 200, f"Request {i+1} failed unexpectedly"

            # 11th should be rate limited
            resp = client.post("/scrapers/test_scraper/run")
            assert resp.status_code == 429

    def test_search_rate_limited(self, client):
        """31st POST to /api/search in a minute should return 429."""
        for i in range(30):
            resp = client.post(
                "/api/search",
                json={"query": "test"},
                content_type="application/json",
            )
            assert resp.status_code == 200, f"Request {i+1} failed unexpectedly"

        resp = client.post(
            "/api/search",
            json={"query": "test"},
            content_type="application/json",
        )
        assert resp.status_code == 429

    def test_api_scraper_run_rate_limited(self, client):
        """11th POST to /api/scrapers/<name>/run should also return 429."""
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry.get_scraper") as mock_get, \
             patch("app.web.blueprints.api_scrapers.job_queue") as mock_queue:
            mock_get.return_value = MagicMock()
            mock_queue.enqueue.return_value = None

            for i in range(10):
                resp = client.post("/api/scrapers/test_scraper/run", json={})
                assert resp.status_code == 202, f"API request {i+1} failed"

            resp = client.post("/api/scrapers/test_scraper/run", json={})
            assert resp.status_code == 429
