"""Stack tests for docling-serve — require real docling-serve service."""

import pytest

from app.backends.parsers.docling_serve_parser import DoclingServeParser
from app.scrapers.models import DocumentMetadata


pytestmark = pytest.mark.stack


@pytest.fixture
def parser(docling_serve_url, docling_serve_alive):
    """Create a DoclingServeParser connected to the real service."""
    return DoclingServeParser(url=docling_serve_url)


@pytest.fixture
def dummy_metadata():
    """Minimal DocumentMetadata for parse calls."""
    return DocumentMetadata(
        url="http://example.com/test.pdf",
        title="Test Document",
        filename="test_document.pdf",
    )


class TestDoclingServeAvailability:
    """Service availability tests."""

    def test_service_available(self, parser):
        """docling-serve should report as available."""
        assert parser.is_available() is True

    def test_supported_formats(self, parser):
        """Should include .pdf in supported formats."""
        formats = parser.get_supported_formats()
        assert ".pdf" in formats


class TestDoclingServeParsing:
    """Document parsing tests."""

    def test_parse_pdf(self, parser, test_pdf, dummy_metadata):
        """Parse a test PDF and verify markdown output."""
        result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is True, f"Parse failed: {result.error}"
        assert result.markdown_path is not None
        assert result.markdown_path.exists()

        content = result.markdown_path.read_text(encoding="utf-8")
        assert len(content) > 0, "Markdown file is empty"

    def test_parse_nonexistent_file(self, parser, tmp_path, dummy_metadata):
        """Should return failure for non-existent file."""
        fake_path = tmp_path / "does_not_exist.pdf"
        result = parser.parse_document(fake_path, dummy_metadata)

        assert result.success is False
        assert "not found" in result.error.lower() or "File not found" in result.error
