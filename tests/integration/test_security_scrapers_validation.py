
import unittest
from unittest.mock import patch, MagicMock
from app.web import create_app
from app.config import Config
from app.services.settings_manager import get_settings

class TestScraperValidation(unittest.TestCase):
    def setUp(self):
        # Disable Basic Auth for testing
        self.original_basic_auth = Config.BASIC_AUTH_ENABLED
        Config.BASIC_AUTH_ENABLED = False

        # Enable FlareSolverr
        self.original_flaresolverr_url = Config.FLARESOLVERR_URL
        Config.FLARESOLVERR_URL = "http://localhost:8191"

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
        self.client = self.app.test_client()
        self.settings = get_settings()

        # Ensure FlareSolverr is enabled in settings
        self.settings.update_section("flaresolverr", {"enabled": True})

    def tearDown(self):
        Config.BASIC_AUTH_ENABLED = self.original_basic_auth
        Config.FLARESOLVERR_URL = self.original_flaresolverr_url

    def test_toggle_non_existent_scraper(self):
        """Test that toggle_scraper_cloudflare rejects non-existent scrapers."""
        # Simulate POST request to toggle Cloudflare for non-existent scraper
        response = self.client.post(
            "/scrapers/non_existent_scraper/cloudflare",
            data={"enabled": "on"}
        )

        # Should return 404
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Not found", response.data)

        # Verify settings were NOT polluted
        if "non_existent_scraper" in self.settings._settings.get("scrapers", {}):
             self.fail("Settings should not be polluted")

    def test_toggle_invalid_scraper_name(self):
        """Test that toggle_scraper_cloudflare rejects invalid name format."""
        response = self.client.post(
            "/scrapers/invalid@name/cloudflare",
            data={"enabled": "on"}
        )
        # Should return 400
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid name", response.data)

    def test_run_scraper_invalid_max_pages(self):
        """Test that run_scraper rejects negative max_pages."""
        with patch('app.web.blueprints.scrapers.ScraperRegistry') as mock_registry:
            mock_scraper = MagicMock()
            mock_registry.get_scraper.return_value = mock_scraper
            mock_registry.get_scraper_class.return_value = MagicMock()

            # Simulate POST request with negative max_pages
            response = self.client.post(
                "/scrapers/some_scraper/run",
                data={"max_pages": "-5", "dry_run": "true"}
            )

            # Should return 400
            self.assertEqual(response.status_code, 400)
            self.assertIn("max_pages must be positive", response.json['error'])

    def test_run_scraper_invalid_name(self):
        """Test that run_scraper rejects invalid name format."""
        response = self.client.post(
            "/scrapers/invalid@name/run",
            data={"max_pages": "1"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid scraper name format", response.json['error'])

if __name__ == "__main__":
    unittest.main()
