"""Integration tests for accessibility features on button elements."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock
from app.web import create_app

@pytest.fixture
def app():
    """Create test Flask app."""
    # Patch runtime dependencies before importing blueprints
    with patch("app.web.runtime.container"), \
         patch("app.web.runtime.job_queue"):
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        yield app

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

class TestScraperButtonsAccessibility:
    """Test accessibility features in scraper buttons."""

    @patch("app.scrapers.ScraperRegistry.list_scrapers")
    @patch("app.web.blueprints.scrapers.load_scraper_configs")  # Mock this to avoid complex setup
    def test_scraper_buttons_have_aria_labels(self, mock_load_configs, mock_list_scrapers, client):
        """Test that scraper action buttons have descriptive aria-labels."""
        # Create a mock scraper dict
        mock_scraper = {
            "name": "test-scraper",
            "description": "Test Description",
            "status": "idle",
            "base_url": "http://example.com",
            "excluded_tags": [],
            "state": {
                "processed_count": 0,
                "statistics": {},
                "last_updated": None
            },
            "ragflow_settings": {
                "ingestion_mode": "builtin",
                "chunk_method": "default",
                "pdf_parser": "default",
                "embedding_model": "",
                "pipeline_id": ""
            },
            "cloudflare_enabled": False
        }

        mock_list_scrapers.return_value = [mock_scraper]

        # mock_load_configs does nothing, so we must ensure mock_scraper has everything needed by the template.

        response = client.get("/scrapers")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # Verify Run button aria-label
        run_btn = soup.find("button", {"id": "run-btn-test-scraper"})
        assert run_btn is not None
        assert run_btn.get("aria-label") == "Run test-scraper scraper"

        # Verify Preview button aria-label
        preview_btn = soup.find("button", {"id": "preview-btn-test-scraper"})
        assert preview_btn is not None
        assert preview_btn.get("aria-label") == "Preview test-scraper scraper"

        # Verify RAGFlow Settings summary aria-label
        summary = soup.find("summary", {"class": "ragflow-settings-toggle"})
        assert summary is not None
        assert summary.get("aria-label") == "RAGFlow Settings for test-scraper"

        # Verify toggle icon aria-hidden
        icon = summary.find("span", {"class": "toggle-icon"})
        assert icon is not None
        assert icon.get("aria-hidden") == "true"

    @patch("app.scrapers.ScraperRegistry.get_scraper_class")
    def test_scraper_card_buttons_have_aria_labels(self, mock_get_scraper_class, client):
        """Test that scraper card buttons have descriptive aria-labels."""
        # Mock the scraper class and its metadata
        mock_scraper_class = MagicMock()
        mock_scraper_class.get_metadata.return_value = {
            "name": "test-scraper",
            "description": "Test Description",
            "status": "idle",
            "state": {"processed_count": 0, "last_updated": None},
        }
        mock_get_scraper_class.return_value = mock_scraper_class

        response = client.get("/scrapers/test-scraper/card")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # Verify Run button aria-label in card
        run_btn = soup.find("button", {"id": "run-btn-card-test-scraper"})
        assert run_btn is not None
        assert run_btn.get("aria-label") == "Run test-scraper scraper"

        # Verify Configure link aria-label
        configure_link = soup.find("a", string="Configure")
        assert configure_link is not None
        assert configure_link.get("aria-label") == "Configure test-scraper scraper"
