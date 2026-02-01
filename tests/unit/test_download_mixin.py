import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import hashlib
from app.scrapers.mixins import HttpDownloadMixin
from app.scrapers.models import DocumentMetadata

class TestHttpDownloadMixin(unittest.TestCase):
    def setUp(self):
        class TestScraper(HttpDownloadMixin):
            name = "test_scraper"
            dry_run = False
            logger = MagicMock()

            # Mock _save_metadata to avoid file IO
            def _save_metadata(self, metadata):
                pass

        self.scraper = TestScraper()

    @patch("requests.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("app.scrapers.mixins.ensure_dir")
    @patch("app.scrapers.mixins.Config")
    def test_download_file_updates_metadata_hash(self, mock_config, mock_ensure_dir, mock_file, mock_get):
        # Setup
        url = "http://example.com/test.pdf"
        filename = "test.pdf"
        content = b"test content for hash"
        expected_hash = hashlib.sha256(content).hexdigest()

        metadata = DocumentMetadata(
            title="Test Doc",
            url=url,
            filename=filename,
            hash=None
        )

        # Mock requests.get response with iterator
        mock_response = MagicMock()
        # Return list of chunks (just one chunk here)
        mock_response.iter_content.return_value = [content]
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Mock download directory
        mock_path = MagicMock(spec=Path)
        # Make the path object return itself when joined with /
        mock_path.__truediv__.return_value = mock_path
        mock_config.DOWNLOAD_DIR = mock_path
        mock_ensure_dir.return_value = mock_path

        # Call _download_file
        self.scraper._download_file(url, filename, metadata)

        # Desired behavior check: hash IS updated
        self.assertEqual(metadata.hash, expected_hash, "Hash should be updated after download")
