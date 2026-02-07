"""Unit tests for DoclingServeParser backend."""

from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest
import requests

from app.backends.parsers.docling_serve_parser import DoclingServeParser
from app.backends.parsers.base import ParserResult
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def parser():
    """Create a parser with test URL."""
    return DoclingServeParser(url="http://test-docling:4949", timeout=60)


@pytest.fixture
def dummy_metadata():
    """Minimal DocumentMetadata for tests."""
    return DocumentMetadata(
        url="http://example.com/test.pdf",
        title="Test Document",
        filename="test.pdf",
    )


@pytest.fixture
def test_pdf(tmp_path):
    """Create a minimal test PDF file."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 minimal test content")
    return pdf_path


class TestIsAvailable:
    """Test is_available() method."""

    @patch("app.backends.parsers.docling_serve_parser.requests.get")
    def test_is_available_success(self, mock_get, parser):
        """Should return True when health endpoint responds OK."""
        mock_get.return_value = Mock(ok=True)
        assert parser.is_available() is True
        mock_get.assert_called_once_with(
            "http://test-docling:4949/health", timeout=10
        )

    @patch("app.backends.parsers.docling_serve_parser.requests.get")
    def test_is_available_failure(self, mock_get, parser):
        """Should return False when health endpoint fails."""
        mock_get.return_value = Mock(ok=False)
        assert parser.is_available() is False

    @patch("app.backends.parsers.docling_serve_parser.requests.get")
    def test_is_available_connection_error(self, mock_get, parser):
        """Should return False when connection fails."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")
        assert parser.is_available() is False

    def test_is_available_no_url(self):
        """Should return False when URL is not configured."""
        parser = DoclingServeParser(url="")
        assert parser.is_available() is False


class TestParseDocument:
    """Test parse_document() method."""

    @patch("app.backends.parsers.docling_serve_parser.requests.post")
    def test_parse_document_success(self, mock_post, parser, test_pdf, dummy_metadata):
        """Should parse PDF and write markdown file."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "document": {
                "md_content": "# Test Heading\n\nSome content here.\n",
                "metadata": {"title": "Parsed Title", "author": "Test Author"},
                "page_count": 3,
            },
            "status": "success",
        }
        mock_post.return_value = mock_response

        result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is True
        assert result.parser_name == "docling_serve"
        assert result.markdown_path is not None
        assert result.markdown_path.exists()

        content = result.markdown_path.read_text(encoding="utf-8")
        assert "# Test Heading" in content
        assert "Some content here." in content

        # Metadata should include extracted values
        assert result.metadata["title"] == "Parsed Title"
        assert result.metadata["author"] == "Test Author"
        assert result.metadata["page_count"] == 3
        assert result.metadata["parsed_by"] == "docling_serve"

    @patch("app.backends.parsers.docling_serve_parser.requests.post")
    def test_parse_document_timeout(self, mock_post, parser, test_pdf, dummy_metadata):
        """Should return failure on timeout."""
        mock_post.side_effect = requests.Timeout("Request timed out")

        result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "timed out" in result.error

    @patch("app.backends.parsers.docling_serve_parser.requests.post")
    def test_parse_document_http_error(self, mock_post, parser, test_pdf, dummy_metadata):
        """Should return failure on HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_post.return_value = mock_response

        result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "HTTP error" in result.error

    @patch("app.backends.parsers.docling_serve_parser.requests.post")
    def test_parse_document_empty_markdown(self, mock_post, parser, test_pdf, dummy_metadata):
        """Should return failure when API returns empty markdown."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "document": {"md_content": ""},
            "status": "success",
        }
        mock_post.return_value = mock_response

        result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "empty markdown" in result.error.lower()

    def test_parse_nonexistent_file(self, parser, tmp_path, dummy_metadata):
        """Should return failure for non-existent file."""
        fake_path = tmp_path / "nonexistent.pdf"

        result = parser.parse_document(fake_path, dummy_metadata)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_parse_url_not_configured(self, dummy_metadata, tmp_path):
        """Should return failure when URL is empty."""
        parser = DoclingServeParser(url="")
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        result = parser.parse_document(pdf_path, dummy_metadata)

        assert result.success is False
        assert "not configured" in result.error.lower()


class TestExtractMetadata:
    """Test _extract_metadata() method."""

    def test_extract_metadata_from_response(self, parser):
        """Should extract title, author, page_count from document response."""
        document = {
            "metadata": {
                "title": "My Document",
                "author": "John Doe",
                "creation_date": "2025-01-15",
            },
            "page_count": 10,
        }
        markdown = "# Heading\n\nContent.\n"

        metadata = parser._extract_metadata(document, markdown)

        assert metadata["title"] == "My Document"
        assert metadata["author"] == "John Doe"
        assert metadata["creation_date"] == "2025-01-15"
        assert metadata["page_count"] == 10
        assert metadata["parsed_by"] == "docling_serve"

    def test_extract_metadata_from_markdown_heading(self, parser):
        """Should extract title from first heading if not in metadata."""
        document = {"metadata": {}}
        markdown = "# My Title From Heading\n\nSome body text.\n"

        metadata = parser._extract_metadata(document, markdown)

        assert metadata["title"] == "My Title From Heading"
        assert metadata["parsed_by"] == "docling_serve"

    def test_extract_metadata_no_title(self, parser):
        """Should not include title when not found anywhere."""
        document = {"metadata": {}}
        markdown = "No heading here, just plain text.\n"

        metadata = parser._extract_metadata(document, markdown)

        assert "title" not in metadata
        assert metadata["parsed_by"] == "docling_serve"


class TestProperties:
    """Test parser properties."""

    def test_name_property(self, parser):
        """Should return 'docling_serve'."""
        assert parser.name == "docling_serve"

    def test_supported_formats(self, parser):
        """Should include common document formats."""
        formats = parser.get_supported_formats()
        assert ".pdf" in formats
        assert ".docx" in formats
