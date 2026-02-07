"""Stack tests for Apache Tika — require live service on Unraid."""

import pytest

from app.services.tika_client import TikaClient


class TestTikaHealth:
    def test_health_check(self, tika_url, tika_alive):
        """Tika should respond to health check."""
        client = TikaClient(url=tika_url)
        assert client.health_check() is True

    def test_is_configured(self, tika_url, tika_alive):
        """Client should report as configured."""
        client = TikaClient(url=tika_url)
        assert client.is_configured is True


class TestTikaTextExtraction:
    def test_extract_text_from_pdf(self, tika_url, tika_alive, test_pdf):
        """Should extract text from PDF."""
        client = TikaClient(url=tika_url)
        text = client.extract_text(test_pdf)
        # Our test PDF has "Stack test <timestamp>" as content
        assert "Stack test" in text or "test" in text.lower()

    def test_extract_text_from_html(self, tika_url, tika_alive, test_html):
        """Should extract text from HTML."""
        client = TikaClient(url=tika_url)
        text = client.extract_text(test_html)
        assert "Test Document" in text or "Stack test" in text

    def test_extract_text_from_markdown(self, tika_url, tika_alive, test_markdown):
        """Should extract text from Markdown."""
        client = TikaClient(url=tika_url)
        text = client.extract_text(test_markdown)
        assert "Test Document" in text


class TestTikaMetadataExtraction:
    def test_extract_metadata_from_pdf(self, tika_url, tika_alive, test_pdf):
        """Should extract metadata from PDF."""
        client = TikaClient(url=tika_url)
        metadata = client.extract_metadata(test_pdf)
        assert isinstance(metadata, dict)
        # PDF should be detected via content_type
        assert "content_type" in metadata, "Expected content_type in metadata"
        assert "pdf" in metadata["content_type"].lower()

    def test_extract_metadata_from_html(self, tika_url, tika_alive, test_html):
        """Should extract metadata from HTML."""
        client = TikaClient(url=tika_url)
        metadata = client.extract_metadata(test_html)
        assert isinstance(metadata, dict)
        # Our test HTML has <title>Test</title>
        assert "title" in metadata, "Expected title in metadata"
        assert "Test" in metadata["title"]


class TestTikaMimeDetection:
    def test_detect_pdf_mime(self, tika_url, tika_alive, test_pdf):
        """Should detect PDF MIME type."""
        client = TikaClient(url=tika_url)
        mime = client.detect_mime_type(test_pdf)
        assert "pdf" in mime.lower()

    def test_detect_html_mime(self, tika_url, tika_alive, test_html):
        """Should detect HTML MIME type."""
        client = TikaClient(url=tika_url)
        mime = client.detect_mime_type(test_html)
        assert "html" in mime.lower() or "xml" in mime.lower()
