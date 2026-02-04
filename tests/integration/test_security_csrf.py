"""Integration tests for CSRF security."""

import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from app.web import create_app

@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies and CSRF ENABLED."""
    with patch("app.web.runtime.container") as mock_container, \
         patch("app.web.runtime.job_queue") as mock_queue:

        # Mock container services
        mock_container.settings_manager.return_value.get_settings.return_value = {}
        mock_container.state_tracker.return_value.get_all_status.return_value = {}

        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = True  # Explicitly enable for these tests
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

class TestCSRFProtection:

    def test_post_without_token_fails(self, client):
        """Test that POST request to protected endpoint without CSRF token fails."""
        # Using /scrapers/<name>/run which is a protected endpoint
        response = client.post("/scrapers/test_scraper/run")

        # 400 Bad Request is the standard CSRF failure code
        assert response.status_code == 400
        assert b"The CSRF token is missing" in response.data or b"Bad Request" in response.data

    def test_post_with_token_succeeds(self, client):
        """Test that POST request with valid CSRF token succeeds."""

        # 1. Get the CSRF token from the page
        with patch("app.web.blueprints.scrapers.ScraperRegistry.list_scrapers") as mock_list, \
             patch("app.web.blueprints.scrapers.load_scraper_configs"):
            mock_list.return_value = []
            response_get = client.get("/scrapers")
            assert response_get.status_code == 200

            soup = BeautifulSoup(response_get.data, 'html.parser')
            meta = soup.find('meta', attrs={'name': 'csrf-token'})
            assert meta is not None, "CSRF token meta tag not found"
            csrf_token = meta['content']

        # 2. POST with the token
        with patch("app.web.blueprints.scrapers.job_queue") as mock_queue, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get_scraper, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class, \
             patch("app.web.blueprints.scrapers.container"):

            mock_get_scraper.return_value = MagicMock()
            mock_get_class.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
            mock_queue.enqueue.return_value = None
            mock_queue.status.return_value = "queued"

            # Simulate HTMX request with header
            response_post = client.post(
                "/scrapers/test_scraper/run",
                headers={"X-CSRFToken": csrf_token}
            )

            # Should succeed (200 OK)
            assert response_post.status_code == 200

    def test_api_exempted(self, client):
        """Test that API endpoints are exempted from CSRF protection."""
        with patch("app.web.blueprints.api_scrapers.job_queue") as mock_queue, \
             patch("app.web.blueprints.api_scrapers.ScraperRegistry.get_scraper") as mock_get_scraper:

            mock_get_scraper.return_value = MagicMock()
            mock_queue.enqueue.return_value = MagicMock(job_id="test")

            # POST to API without token
            # Note: The API endpoint validates scraper name regex first
            response = client.post("/api/scrapers/test_scraper/run", json={})

            # Should NOT be 400 (CSRF error).
            # We expect 202 Accepted (success) or 404/500 depending on mocks, but definitely not 400.
            assert response.status_code != 400
            if response.status_code == 202:
                # Success
                pass
            else:
                # If it failed, check it wasn't CSRF
                assert b"CSRF" not in response.data
