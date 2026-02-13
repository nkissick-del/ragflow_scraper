"""Unit tests for GotenbergClient."""

from unittest.mock import patch, Mock

import pytest
import requests

from app.config import Config
from app.services.gotenberg_client import GotenbergClient


@pytest.fixture
def client():
    """Create a client with test URL."""
    return GotenbergClient(url="http://test-gotenberg:3156", timeout=30)


class TestIsConfigured:
    def test_configured_with_url(self, client):
        assert client.is_configured is True

    def test_not_configured_without_url(self):
        c = GotenbergClient(url="")
        assert c.is_configured is False


class TestHealthCheck:
    @patch("app.services.gotenberg_client.requests.get")
    def test_health_check_success(self, mock_get, client):
        mock_get.return_value = Mock(ok=True)
        assert client.health_check() is True
        mock_get.assert_called_once_with(
            "http://test-gotenberg:3156/health", timeout=10
        )

    @patch("app.services.gotenberg_client.requests.get")
    def test_health_check_failure(self, mock_get, client):
        mock_get.return_value = Mock(ok=False)
        assert client.health_check() is False

    @patch("app.services.gotenberg_client.requests.get")
    def test_health_check_connection_error(self, mock_get, client):
        mock_get.side_effect = requests.ConnectionError("refused")
        assert client.health_check() is False

    def test_health_check_no_url(self):
        c = GotenbergClient(url="")
        assert c.health_check() is False


class TestConvertHtmlToPdf:
    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_success(self, mock_post, client):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4 fake pdf"
        mock_post.return_value = mock_resp

        result = client.convert_html_to_pdf(
            "<html><body><p>Hello</p></body></html>", title="Test"
        )

        assert result == b"%PDF-1.4 fake pdf"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "/forms/chromium/convert/html" in call_kwargs[0][0]

    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_wraps_partial_html(self, mock_post, client):
        """Partial HTML (no <html> tag) should be wrapped in template."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4"
        mock_post.return_value = mock_resp

        client.convert_html_to_pdf("<p>Just a paragraph</p>", title="Test")

        # The posted content should be wrapped in full HTML
        call_args = mock_post.call_args
        files = call_args[1]["files"]
        content = files["files"][1]  # (filename, content, mimetype)
        assert b"<!DOCTYPE html>" in content
        assert b"Just a paragraph" in content

    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_http_error(self, mock_post, client):
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            client.convert_html_to_pdf("<p>Test</p>")

    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_connection_error(self, mock_post, client):
        mock_post.side_effect = requests.ConnectionError("refused")

        with pytest.raises(requests.ConnectionError):
            client.convert_html_to_pdf("<p>Test</p>")


class TestConvertMarkdownToPdf:
    @patch("app.services.gotenberg_client.requests.post")
    def test_markdown_to_pdf_success(self, mock_post, client):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4 md pdf"
        mock_post.return_value = mock_resp

        result = client.convert_markdown_to_pdf(
            "# Hello\n\nWorld", title="Test Doc"
        )

        assert result == b"%PDF-1.4 md pdf"
        mock_post.assert_called_once()


class TestConvertOfficeToPdf:
    @patch("app.services.gotenberg_client.requests.post")
    def test_office_to_pdf_success(self, mock_post, client, tmp_path):
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4 office pdf"
        mock_post.return_value = mock_resp

        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(b"fake docx content")

        result = client.convert_office_to_pdf(docx_path)

        assert result == b"%PDF-1.4 office pdf"
        call_args = mock_post.call_args
        assert "/forms/libreoffice/convert" in call_args[0][0]


class TestConvertToPdf:
    @patch.object(GotenbergClient, "convert_html_to_pdf", return_value=b"pdf")
    def test_routes_html(self, mock_html, client, tmp_path):
        html_file = tmp_path / "test.html"
        html_file.write_text("<p>Hello</p>")

        result = client.convert_to_pdf(html_file)
        assert result == b"pdf"
        mock_html.assert_called_once()

    @patch.object(GotenbergClient, "convert_markdown_to_pdf", return_value=b"pdf")
    def test_routes_markdown(self, mock_md, client, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello")

        result = client.convert_to_pdf(md_file)
        assert result == b"pdf"
        mock_md.assert_called_once()

    @patch.object(GotenbergClient, "convert_office_to_pdf", return_value=b"pdf")
    def test_routes_office(self, mock_office, client, tmp_path):
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"fake docx")

        result = client.convert_to_pdf(docx_file)
        assert result == b"pdf"
        mock_office.assert_called_once()


class TestFileSizeLimit:
    def test_rejects_oversized_file(self, client, tmp_path):
        """Should reject files exceeding MAX_UPLOAD_FILE_SIZE."""
        test_file = tmp_path / "big.docx"
        test_file.write_bytes(b"x" * 2048)

        with patch.object(Config, "MAX_UPLOAD_FILE_SIZE", 1024):
            with pytest.raises(ValueError, match="exceeds MAX_UPLOAD_FILE_SIZE"):
                client.convert_office_to_pdf(test_file)

    def test_allows_office_within_limit(self, client, tmp_path):
        """Should allow office files within the size limit."""
        test_file = tmp_path / "small.docx"
        test_file.write_bytes(b"x" * 100)

        with patch.object(Config, "MAX_UPLOAD_FILE_SIZE", 1024):
            with patch("app.services.gotenberg_client.requests.post") as mock_post:
                mock_resp = Mock()
                mock_resp.raise_for_status = Mock()
                mock_resp.content = b"%PDF-1.4"
                mock_post.return_value = mock_resp

                result = client.convert_office_to_pdf(test_file)
                assert result == b"%PDF-1.4"
