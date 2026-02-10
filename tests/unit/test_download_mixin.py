
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from app.scrapers.mixins import HttpDownloadMixin
from app.scrapers.models import DocumentMetadata

class TestHttpDownloadMixin:
    def setup_method(self):
        class TestScraper(HttpDownloadMixin):
            name = "test_scraper"
            download_timeout = 30
            logger = Mock()

            def _save_metadata(self, metadata):
                pass

        self.scraper = TestScraper()

    @patch("app.scrapers.download_mixin.requests.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("app.scrapers.download_mixin.ensure_dir")
    def test_download_file_computes_hash(self, mock_ensure_dir, mock_file, mock_get):
        # Setup
        mock_ensure_dir.return_value = Path("/tmp")

        # Mock response with chunks
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_get.return_value = mock_response

        metadata = DocumentMetadata(
            url="http://example.com/file.pdf",
            title="Test",
            filename="file.pdf"
        )

        # Execute
        path = self.scraper._download_file("http://example.com/file.pdf", "file.pdf", metadata)

        # Verify
        assert path == Path("/tmp/file.pdf")

        # Check hash calculation
        import hashlib
        expected_hash = hashlib.sha256(b"chunk1chunk2").hexdigest()
        assert metadata.hash == expected_hash
        assert metadata.file_size == 12  # len("chunk1") + len("chunk2")

    @patch("app.scrapers.download_mixin.requests.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("app.scrapers.download_mixin.ensure_dir")
    def test_download_file_uses_chunk_size(self, mock_ensure_dir, mock_file, mock_get):
        # Setup
        mock_ensure_dir.return_value = Path("/tmp")
        mock_response = Mock()
        mock_response.iter_content.return_value = []
        mock_get.return_value = mock_response

        from app.utils.file_utils import CHUNK_SIZE

        # Execute
        self.scraper._download_file("http://example.com/file.pdf", "file.pdf")

        # Verify chunk size
        mock_response.iter_content.assert_called_with(chunk_size=CHUNK_SIZE)
