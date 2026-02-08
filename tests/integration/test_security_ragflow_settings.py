import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.web.blueprints.scrapers import bp
from app.services.ragflow_client import CHUNK_METHODS, PDF_PARSERS

class TestRAGFlowSettingsSecurity(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

        # Mock container
        self.container_patch = patch('app.web.blueprints.scrapers.container')
        self.mock_container = self.container_patch.start()

        # Mock settings manager
        self.mock_settings = MagicMock()
        self.mock_container.settings = self.mock_settings

        # Mock ScraperRegistry
        self.registry_patch = patch('app.web.blueprints.scrapers.ScraperRegistry')
        self.mock_registry = self.registry_patch.start()

        # Setup mock scraper
        self.mock_scraper_class = MagicMock()
        self.mock_registry.get_scraper_class.return_value = self.mock_scraper_class

    def tearDown(self):
        self.container_patch.stop()
        self.registry_patch.stop()

    def test_save_invalid_chunk_method(self):
        """Test that invalid chunk_method is rejected."""
        scraper_name = "test_scraper"
        invalid_method = "<script>alert(1)</script>"

        data = {
            "chunk_method": invalid_method,
            f"ingestion_mode_{scraper_name}": "builtin"
        }

        response = self.client.post(f"/scrapers/{scraper_name}/ragflow", data=data)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid chunk method", response.data)
        self.mock_settings.set_scraper_ragflow_settings.assert_not_called()

    def test_save_valid_chunk_method(self):
        """Test that valid chunk_method is accepted."""
        scraper_name = "test_scraper"
        valid_method = CHUNK_METHODS[0]

        data = {
            "chunk_method": valid_method,
            f"ingestion_mode_{scraper_name}": "builtin"
        }

        response = self.client.post(f"/scrapers/{scraper_name}/ragflow", data=data)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Saved", response.data)
        self.mock_settings.set_scraper_ragflow_settings.assert_called()

    def test_save_invalid_pdf_parser(self):
        """Test that invalid pdf_parser is rejected."""
        scraper_name = "test_scraper"
        invalid_parser = "InvalidParser"

        data = {
            "pdf_parser": invalid_parser,
            f"ingestion_mode_{scraper_name}": "builtin"
        }

        response = self.client.post(f"/scrapers/{scraper_name}/ragflow", data=data)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid PDF parser", response.data)
        self.mock_settings.set_scraper_ragflow_settings.assert_not_called()

    def test_save_valid_complex_embedding_model(self):
        """Test that complex embedding_model with / and : is accepted."""
        scraper_name = "test_scraper"
        valid_model = "org/model:v1@provider"

        data = {
            "embedding_model": valid_model,
            f"ingestion_mode_{scraper_name}": "builtin"
        }

        response = self.client.post(f"/scrapers/{scraper_name}/ragflow", data=data)

        self.assertEqual(response.status_code, 200)
        self.mock_settings.set_scraper_ragflow_settings.assert_called()

    def test_save_invalid_embedding_model(self):
        """Test that invalid embedding_model format is rejected."""
        scraper_name = "test_scraper"
        invalid_model = "model; DROP TABLE users;"

        data = {
            "embedding_model": invalid_model,
            f"ingestion_mode_{scraper_name}": "builtin"
        }

        response = self.client.post(f"/scrapers/{scraper_name}/ragflow", data=data)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid embedding model format", response.data)
        self.mock_settings.set_scraper_ragflow_settings.assert_not_called()

if __name__ == "__main__":
    unittest.main()
