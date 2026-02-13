"""Tests for the API purge endpoint."""

from __future__ import annotations

import base64
from unittest.mock import patch, MagicMock

import pytest

from app.config import Config


_AUTH_HEADER = {
    "Authorization": "Basic " + base64.b64encode(b"testuser:testpass").decode()
}


@pytest.fixture
def app():
    """Create Flask app with mocked dependencies."""
    with patch("app.web.runtime.get_container") as mock_gc, \
         patch("app.web.runtime.JobQueue") as mock_jq_cls, \
         patch.object(Config, "SECRET_KEY", "test-secret-key"), \
         patch.object(Config, "BASIC_AUTH_USERNAME", "testuser"), \
         patch.object(Config, "BASIC_AUTH_PASSWORD", "testpass"), \
         patch.object(Config, "MAX_CONCURRENT_DOWNLOADS", 1):

        mock_container = MagicMock()
        mock_gc.return_value = mock_container
        mock_jq = MagicMock()
        mock_jq_cls.return_value = mock_jq

        from app.web import create_app
        application = create_app()
        application.config["TESTING"] = True
        application.config["WTF_CSRF_ENABLED"] = False

        # Patch the runtime references that blueprints imported
        with patch("app.web.blueprints.api_scrapers.container", mock_container), \
             patch("app.web.blueprints.api_scrapers.job_queue", mock_jq):
            yield application, mock_container, mock_jq


class TestApiPurgeScraper:
    def test_invalid_name(self, app):
        """Invalid scraper name returns 400."""
        application, _, _ = app
        with application.test_client() as client:
            resp = client.post(
                "/api/scrapers/evil.name/purge", headers=_AUTH_HEADER
            )
            assert resp.status_code == 400

    def test_scraper_not_found(self, app):
        """Unknown scraper returns 404."""
        application, _, _ = app
        with application.test_client() as client:
            with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
                mock_reg.get_scraper_class.return_value = None
                resp = client.post(
                    "/api/scrapers/nonexistent/purge", headers=_AUTH_HEADER
                )
                assert resp.status_code == 404

    def test_running_scraper_returns_409(self, app):
        """Purging a running scraper returns 409."""
        application, mock_container, mock_jq = app
        with application.test_client() as client:
            with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
                mock_reg.get_scraper_class.return_value = MagicMock()
                mock_job = MagicMock()
                mock_job.is_active = True
                mock_job.status = "running"
                mock_jq.get.return_value = mock_job

                resp = client.post(
                    "/api/scrapers/aemo/purge", headers=_AUTH_HEADER
                )
                assert resp.status_code == 409

    def test_successful_purge(self, app):
        """Successful purge returns 200 with counts."""
        application, mock_container, mock_jq = app
        with application.test_client() as client:
            with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
                mock_reg.get_scraper_class.return_value = MagicMock()
                mock_jq.get.return_value = None  # Not running

                mock_tracker = MagicMock()
                mock_tracker.purge.return_value = {
                    "urls_cleared": 5,
                    "files_deleted": 3,
                    "metadata_deleted": 3,
                }
                mock_container.state_tracker.return_value = mock_tracker

                resp = client.post(
                    "/api/scrapers/aemo/purge", headers=_AUTH_HEADER
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["success"] is True
                assert data["urls_cleared"] == 5
                assert data["files_deleted"] == 3

    def test_idle_job_allows_purge(self, app):
        """Completed/idle job does not block purge."""
        application, mock_container, mock_jq = app
        with application.test_client() as client:
            with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
                mock_reg.get_scraper_class.return_value = MagicMock()
                mock_job = MagicMock()
                mock_job.is_active = False  # Completed
                mock_jq.get.return_value = mock_job

                mock_tracker = MagicMock()
                mock_tracker.purge.return_value = {
                    "urls_cleared": 0,
                    "files_deleted": 0,
                    "metadata_deleted": 0,
                }
                mock_container.state_tracker.return_value = mock_tracker

                resp = client.post(
                    "/api/scrapers/aemo/purge", headers=_AUTH_HEADER
                )
                assert resp.status_code == 200
