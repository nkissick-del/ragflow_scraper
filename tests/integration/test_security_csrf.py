
import pytest
from unittest.mock import patch, MagicMock
from app.web import create_app
from app.scrapers.scraper_registry import ScraperRegistry

@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies."""
    with patch("app.web.runtime.container") as mock_container, \
         patch("app.web.runtime.job_queue") as mock_queue:

        # Mock container services
        mock_container.settings_manager.return_value.get_settings.return_value = {
            "ragflow": {"api_url": "http://test", "api_key": "test"},
            "flaresolverr": {"api_url": "http://test"},
            "scraping": {"cloudflare_bypass": False}
        }
        mock_container.state_tracker.return_value.get_all_status.return_value = {}

        app = create_app()
        app.config["TESTING"] = True
        # Explicitly enable CSRF for this test to verify protection
        app.config["WTF_CSRF_ENABLED"] = True
        yield app

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

def test_run_scraper_without_csrf_token_fails(client):
    """
    Test that a POST request to run a scraper FAILS without a CSRF token.
    This verifies the fix is active.
    """
    with patch("app.web.blueprints.scrapers.job_queue") as mock_queue, \
            patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get_scraper, \
            patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class:

        mock_get_scraper.return_value = MagicMock()
        mock_get_class.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
        mock_queue.enqueue.return_value = None
        mock_queue.status.return_value = "queued"

        # Make a POST request without any CSRF token
        response = client.post("/scrapers/test_scraper/run", data={"dry_run": "true"})

        # Should fail with 400 Bad Request (CSRF error)
        assert response.status_code == 400
        # The exact error message depends on Flask-WTF configuration, but typically:
        assert b"The CSRF token is missing." in response.data or b"The CSRF token is invalid." in response.data

def test_run_scraper_with_csrf_token_succeeds(client, app):
    """
    Test that a POST request to run a scraper SUCCEEDS with a valid CSRF token.
    This verifies that legitimate requests are not blocked.
    """
    with patch("app.web.blueprints.scrapers.job_queue") as mock_queue, \
            patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get_scraper, \
            patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class, \
            patch("app.web.blueprints.scrapers.container") as mock_container, \
            patch.object(ScraperRegistry, "get_all_scrapers", return_value=["test_scraper"]):

        mock_get_scraper.return_value = MagicMock()
        mock_get_class.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
        mock_queue.enqueue.return_value = None
        mock_queue.status.return_value = "queued"

        mock_container.state_tracker.return_value.get_last_run_info.return_value = {}

        # Get CSRF token
        with client:
            # We need to make a request to generate the token cookie/session
            # and get the token from the DOM
            response = client.get("/scrapers")

            assert response.status_code == 200

            csrf_token = None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.data, 'html.parser')
            meta = soup.find('meta', {'name': 'csrf-token'})
            if meta:
                csrf_token = meta['content']

            assert csrf_token is not None, "CSRF token meta tag not found in base.html"

            # Now post with the token
            response = client.post(
                "/scrapers/test_scraper/run",
                data={"dry_run": "true"},
                headers={"X-CSRFToken": csrf_token}
            )

            assert response.status_code == 200
