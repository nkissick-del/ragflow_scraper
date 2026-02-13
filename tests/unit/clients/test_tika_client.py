"""Unit tests for TikaClient."""

from unittest.mock import patch, Mock

import pytest
import requests

from app.config import Config
from app.services.tika_client import TikaClient


@pytest.fixture
def client():
    """Create a client with test URL."""
    return TikaClient(url="http://test-tika:9998", timeout=30)


class TestIsConfigured:
    def test_configured_with_url(self, client):
        assert client.is_configured is True

    def test_not_configured_without_url(self):
        c = TikaClient(url="")
        assert c.is_configured is False


class TestHealthCheck:
    @patch("app.services.tika_client.requests.get")
    def test_health_check_success(self, mock_get, client):
        mock_get.return_value = Mock(ok=True)
        assert client.health_check() is True
        mock_get.assert_called_once_with(
            "http://test-tika:9998/tika", timeout=10
        )

    @patch("app.services.tika_client.requests.get")
    def test_health_check_failure(self, mock_get, client):
        mock_get.return_value = Mock(ok=False)
        assert client.health_check() is False

    @patch("app.services.tika_client.requests.get")
    def test_health_check_connection_error(self, mock_get, client):
        mock_get.side_effect = requests.ConnectionError("refused")
        assert client.health_check() is False

    def test_health_check_no_url(self):
        c = TikaClient(url="")
        assert c.health_check() is False


class TestExtractText:
    @patch("app.services.tika_client.requests.put")
    def test_extract_text_success(self, mock_put, client, tmp_path):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.text = "This is the extracted text content."
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        result = client.extract_text(test_file)

        assert result == "This is the extracted text content."
        call_args = mock_put.call_args
        assert "/tika" in call_args[0][0]
        assert call_args[1]["headers"]["Accept"] == "text/plain"

    @patch("app.services.tika_client.requests.put")
    def test_extract_text_http_error(self, mock_put, client, tmp_path):
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        with pytest.raises(requests.HTTPError):
            client.extract_text(test_file)

    @patch("app.services.tika_client.requests.put")
    def test_extract_text_timeout(self, mock_put, client, tmp_path):
        mock_put.side_effect = requests.Timeout("timed out")

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        with pytest.raises(requests.Timeout):
            client.extract_text(test_file)


class TestExtractMetadata:
    @patch("app.services.tika_client.requests.put")
    def test_extract_metadata_success(self, mock_put, client, tmp_path):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "dc:title": "Test Document",
            "dc:creator": "John Doe",
            "meta:page-count": "5",
            "dcterms:created": "2025-01-15T10:00:00Z",
            "Content-Type": "application/pdf",
        }
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        result = client.extract_metadata(test_file)

        assert result["title"] == "Test Document"
        assert result["author"] == "John Doe"
        assert result["page_count"] == 5
        assert result["creation_date"] == "2025-01-15T10:00:00Z"
        assert result["content_type"] == "application/pdf"

    @patch("app.services.tika_client.requests.put")
    def test_extract_metadata_normalization(self, mock_put, client, tmp_path):
        """Should normalize Dublin Core keys to standard names."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "dc:title": "Title",
            "meta:author": "Author via meta:author",
            "xmpTPg:NPages": "10",
        }
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        result = client.extract_metadata(test_file)

        assert result["title"] == "Title"
        assert result["author"] == "Author via meta:author"
        assert result["page_count"] == 10

    @patch("app.services.tika_client.requests.put")
    def test_extract_metadata_invalid_page_count(self, mock_put, client, tmp_path):
        """Should skip non-integer page_count values."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "meta:page-count": "not-a-number",
        }
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        result = client.extract_metadata(test_file)
        assert "page_count" not in result

    @patch("app.services.tika_client.requests.put")
    def test_extract_metadata_first_match_wins(self, mock_put, client, tmp_path):
        """First matching key should take precedence."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "dc:creator": "First Author",
            "meta:author": "Second Author",
        }
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        result = client.extract_metadata(test_file)
        assert result["author"] == "First Author"


class TestDetectMimeType:
    @patch("app.services.tika_client.requests.put")
    def test_detect_mime_type(self, mock_put, client, tmp_path):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.text = "application/pdf\n"
        mock_put.return_value = mock_resp

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        result = client.detect_mime_type(test_file)

        assert result == "application/pdf"
        call_args = mock_put.call_args
        assert "/detect/stream" in call_args[0][0]


class TestFileSizeLimit:
    def test_rejects_oversized_file(self, client, tmp_path):
        """Should reject files exceeding MAX_UPLOAD_FILE_SIZE."""
        test_file = tmp_path / "big.pdf"
        # Write a file larger than 1KB limit
        test_file.write_bytes(b"x" * 2048)

        with patch.object(Config, "MAX_UPLOAD_FILE_SIZE", 1024):
            with pytest.raises(ValueError, match="exceeds MAX_UPLOAD_FILE_SIZE"):
                client.extract_text(test_file)

    def test_allows_file_within_limit(self, client, tmp_path):
        """Should allow files within the size limit."""
        test_file = tmp_path / "small.pdf"
        test_file.write_bytes(b"x" * 100)

        with patch.object(Config, "MAX_UPLOAD_FILE_SIZE", 1024):
            with patch("app.services.tika_client.requests.put") as mock_put:
                mock_resp = Mock()
                mock_resp.raise_for_status = Mock()
                mock_resp.text = "extracted text"
                mock_put.return_value = mock_resp

                result = client.extract_text(test_file)
                assert result == "extracted text"

    def test_size_check_disabled_when_zero(self, client, tmp_path):
        """Should skip size check when MAX_UPLOAD_FILE_SIZE is 0."""
        test_file = tmp_path / "any.pdf"
        test_file.write_bytes(b"x" * 999999)

        with patch.object(Config, "MAX_UPLOAD_FILE_SIZE", 0):
            with patch("app.services.tika_client.requests.put") as mock_put:
                mock_resp = Mock()
                mock_resp.raise_for_status = Mock()
                mock_resp.text = "ok"
                mock_put.return_value = mock_resp

                result = client.extract_text(test_file)
                assert result == "ok"
