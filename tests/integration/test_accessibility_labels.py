"""Integration tests for accessibility labels on buttons."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock
from app.web import create_app

@pytest.fixture
def app():
    """Create test Flask app."""
    # Patch runtime dependencies
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

@pytest.fixture
def mock_registry():
    """Mock the ScraperRegistry."""
    with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock:
        yield mock

class TestButtonAccessibilityLabels:
    """Test that action buttons have appropriate aria-labels."""

    def test_scrapers_page_buttons(self, client, mock_registry):
        """Test the buttons on the main scrapers page (scrapers.html)."""
        # Setup mock scraper
        mock_scraper = MagicMock()
        mock_scraper.name = "TestScraper"
        mock_scraper.description = "A test scraper"
        mock_scraper.status = "idle"
        # Mock dictionary access for the template
        mock_scraper.__getitem__ = lambda s, k: getattr(s, k)
        mock_scraper.get = lambda k, d=None: getattr(mock_scraper, k, d)

        # Additional attributes expected by the template
        mock_scraper.base_url = "http://example.com"
        mock_scraper.excluded_tags = []
        mock_scraper.state.processed_count = 0
        mock_scraper.state.statistics.total_downloaded = 0
        mock_scraper.state.statistics.total_skipped = 0
        mock_scraper.state.statistics.total_failed = 0
        mock_scraper.state.last_updated = None
        mock_scraper.ragflow_settings.ingestion_mode = "builtin"
        mock_scraper.ragflow_settings.chunk_method = "default"
        mock_scraper.ragflow_settings.pdf_parser = "default"
        mock_scraper.ragflow_settings.embedding_model = ""
        mock_scraper.ragflow_settings.pipeline_id = ""
        mock_scraper.cloudflare_enabled = False

        mock_registry.list_scrapers.return_value = [mock_scraper]

        response = client.get("/scrapers")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # Check Preview Button
        preview_btn = soup.find("button", id="preview-btn-TestScraper")
        assert preview_btn is not None
        assert preview_btn.get("aria-label") == "Preview TestScraper scraper"

        # Check Run Button
        run_btn = soup.find("button", id="run-btn-TestScraper")
        assert run_btn is not None
        assert run_btn.get("aria-label") == "Run TestScraper scraper"

    def test_scraper_card_buttons(self, client, mock_registry):
        """Test the buttons on the scraper card component (scraper-card.html)."""
        # Setup mock scraper class
        mock_scraper_class = MagicMock()
        mock_scraper_class.get_metadata.return_value = {
            "name": "TestScraper",
            "description": "A test scraper",
            "status": "idle",
            "processed_count": 0,
            "last_run": None,
            "state": {"processed_count": 0, "last_updated": None}
        }

        mock_registry.get_scraper_class.return_value = mock_scraper_class

        # Helper to patch build_scraper_metadata which is used in the route
        with patch("app.web.blueprints.scrapers.build_scraper_metadata") as mock_metadata:
            mock_metadata.return_value = {
                "name": "TestScraper",
                "description": "A test scraper",
                "status": "idle",
                "state": {"processed_count": 0, "last_updated": None}
            }

            response = client.get("/scrapers/TestScraper/card")
            assert response.status_code == 200

            soup = BeautifulSoup(response.data, "html.parser")

            # Check Run Button (should be present for 'idle' status)
            run_btn = soup.find("button", id="run-btn-card-TestScraper")
            assert run_btn is not None
            assert run_btn.get("aria-label") == "Run TestScraper scraper"

            # Check Configure Link
            config_link = soup.find("a", string="Configure")
            assert config_link is not None
            assert config_link.get("aria-label") == "Configure TestScraper scraper"

    def test_scraper_card_cancel_button(self, client, mock_registry):
        """Test the cancel button on the scraper card component."""
         # Helper to patch build_scraper_metadata which is used in the route
        with patch("app.web.blueprints.scrapers.build_scraper_metadata") as mock_metadata:
            mock_metadata.return_value = {
                "name": "TestScraper",
                "description": "A test scraper",
                "status": "running",
                "state": {"processed_count": 0, "last_updated": None}
            }

            # Need to patch ScraperRegistry.get_scraper_class to return something so 404 isn't raised
            mock_registry.get_scraper_class.return_value = MagicMock()

            response = client.get("/scrapers/TestScraper/card")
            assert response.status_code == 200

            soup = BeautifulSoup(response.data, "html.parser")

            # Check Cancel Button (should be present for 'running' status)
            # Cancel button doesn't have an ID in the template, so find by text/class
            cancel_btn = soup.find("button", class_="btn-danger")
            assert cancel_btn is not None
            assert cancel_btn.get("aria-label") == "Cancel TestScraper scraper"

    def test_scraper_card_cancelling_state(self, client, mock_registry):
        """Test the cancel button when status is cancelling."""
        with patch("app.web.blueprints.scrapers.build_scraper_metadata") as mock_metadata:
            mock_metadata.return_value = {
                "name": "TestScraper",
                "description": "A test scraper",
                "status": "cancelling",
                "state": {"processed_count": 0, "last_updated": None}
            }

            mock_registry.get_scraper_class.return_value = MagicMock()

            response = client.get("/scrapers/TestScraper/card")
            assert response.status_code == 200

            soup = BeautifulSoup(response.data, "html.parser")

            cancel_btn = soup.find("button", class_="btn-danger")
            assert cancel_btn is not None
            assert cancel_btn.get("aria-label") == "Cancelling TestScraper scraper"
