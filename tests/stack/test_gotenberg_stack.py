"""Stack tests for Gotenberg — require live service on Unraid."""

import pytest

from app.services.gotenberg_client import GotenbergClient


class TestGotenbergHealth:
    def test_health_check(self, gotenberg_url, gotenberg_alive):
        """Gotenberg should respond to health check."""
        client = GotenbergClient(url=gotenberg_url)
        assert client.health_check() is True

    def test_is_configured(self, gotenberg_url, gotenberg_alive):
        """Client should report as configured."""
        client = GotenbergClient(url=gotenberg_url)
        assert client.is_configured is True


class TestGotenbergConversion:
    def test_html_to_pdf(self, gotenberg_url, gotenberg_alive):
        """Should convert HTML to PDF."""
        client = GotenbergClient(url=gotenberg_url)
        html = (
            "<html><body>"
            "<h1>Stack Test</h1>"
            "<p>This is a Gotenberg stack test.</p>"
            "</body></html>"
        )
        pdf_bytes = client.convert_html_to_pdf(html, title="Stack Test")
        assert pdf_bytes[:4] == b"%PDF"
        assert len(pdf_bytes) > 100

    def test_markdown_to_pdf(self, gotenberg_url, gotenberg_alive):
        """Should convert Markdown to PDF."""
        client = GotenbergClient(url=gotenberg_url)
        md = "# Stack Test\n\nThis is a **Gotenberg** stack test.\n\n## Section\n\nMore content."
        pdf_bytes = client.convert_markdown_to_pdf(md, title="Stack Test")
        assert pdf_bytes[:4] == b"%PDF"
        assert len(pdf_bytes) > 100

    def test_html_file_to_pdf(self, gotenberg_url, gotenberg_alive, test_html):
        """Should convert an HTML file via convert_to_pdf routing."""
        client = GotenbergClient(url=gotenberg_url)
        pdf_bytes = client.convert_to_pdf(test_html)
        assert pdf_bytes[:4] == b"%PDF"

    def test_markdown_file_to_pdf(self, gotenberg_url, gotenberg_alive, test_markdown):
        """Should convert a Markdown file via convert_to_pdf routing."""
        client = GotenbergClient(url=gotenberg_url)
        pdf_bytes = client.convert_to_pdf(test_markdown)
        assert pdf_bytes[:4] == b"%PDF"
