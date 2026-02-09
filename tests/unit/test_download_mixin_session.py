
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from app.scrapers.mixins import HttpDownloadMixin

class TestHttpDownloadMixinSession:
    def setup_method(self):
        # Create a scraper with _session attribute
        class TestScraper(HttpDownloadMixin):
            name = "test_scraper"
            download_timeout = 30
            logger = Mock()
            _session = Mock()

            def _save_metadata(self, metadata):
                pass

        self.scraper = TestScraper()

    @patch("app.scrapers.mixins.ensure_dir")
    def test_download_file_uses_session(self, mock_ensure_dir):
        # Setup
        mock_ensure_dir.return_value = Path("/tmp")

        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"data"]
        self.scraper._session.get.return_value = mock_response

        # Execute
        with patch("builtins.open", new_callable=mock_open):
            self.scraper._download_file("http://example.com/file.pdf", "file.pdf")

        # Verify session.get called instead of requests.get
        self.scraper._session.get.assert_called_once()

        # Verify arguments
        args, kwargs = self.scraper._session.get.call_args
        assert args[0] == "http://example.com/file.pdf"
        assert kwargs["stream"] is True
        assert "headers" in kwargs
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0 PDF Scraper"

    @patch("app.scrapers.mixins.requests.get")
    @patch("app.scrapers.mixins.ensure_dir")
    def test_download_file_fallback_to_requests(self, mock_ensure_dir, mock_requests_get):
        # Create a scraper WITHOUT _session attribute
        class TestScraperNoSession(HttpDownloadMixin):
            name = "test_scraper"
            download_timeout = 30
            logger = Mock()
            # No _session

            def _save_metadata(self, metadata):
                pass

        scraper = TestScraperNoSession()

        # Setup
        mock_ensure_dir.return_value = Path("/tmp")
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"data"]
        mock_requests_get.return_value = mock_response

        # Execute
        with patch("builtins.open", new_callable=mock_open):
            scraper._download_file("http://example.com/file.pdf", "file.pdf")

        # Verify requests.get called
        mock_requests_get.assert_called_once()
