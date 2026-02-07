"""Unit tests for TikaParser backend."""

from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest
import requests

from app.backends.parsers.tika_parser import TikaParser
from app.backends.parsers.base import ParserResult
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def parser():
    """Create a parser with test URL."""
    return TikaParser(url="http://test-tika:9998", timeout=60)


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
    def test_is_available_success(self, parser):
        with patch.object(parser.client, "health_check", return_value=True):
            assert parser.is_available() is True

    def test_is_available_failure(self, parser):
        with patch.object(parser.client, "health_check", return_value=False):
            assert parser.is_available() is False

    def test_is_available_connection_error(self, parser):
        with patch.object(
            parser.client, "health_check", side_effect=requests.ConnectionError
        ):
            assert parser.is_available() is False

    def test_is_available_no_url(self):
        p = TikaParser(url="")
        assert p.is_available() is False


class TestParseDocument:
    def test_parse_document_success(self, parser, test_pdf, dummy_metadata):
        """Should extract text, metadata, and write markdown file."""
        with (
            patch.object(
                parser.client,
                "extract_text",
                return_value="This is extracted text.\n\nSecond paragraph.",
            ),
            patch.object(
                parser.client,
                "extract_metadata",
                return_value={
                    "title": "Parsed Title",
                    "author": "Test Author",
                    "page_count": 3,
                },
            ),
        ):
            result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is True
        assert result.parser_name == "tika"
        assert result.markdown_path is not None
        assert result.markdown_path.exists()

        content = result.markdown_path.read_text(encoding="utf-8")
        assert "# Parsed Title" in content
        assert "This is extracted text." in content

        assert result.metadata["title"] == "Parsed Title"
        assert result.metadata["author"] == "Test Author"
        assert result.metadata["page_count"] == 3
        assert result.metadata["parsed_by"] == "tika"

    def test_parse_document_empty_text(self, parser, test_pdf, dummy_metadata):
        """Should return failure on empty text."""
        with (
            patch.object(parser.client, "extract_text", return_value=""),
            patch.object(
                parser.client, "extract_metadata", return_value={}
            ),
        ):
            result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "empty text" in result.error.lower()

    def test_parse_document_whitespace_only(self, parser, test_pdf, dummy_metadata):
        """Should return failure when text is whitespace only."""
        with (
            patch.object(
                parser.client, "extract_text", return_value="   \n\n  "
            ),
            patch.object(
                parser.client, "extract_metadata", return_value={}
            ),
        ):
            result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "empty text" in result.error.lower()

    def test_parse_nonexistent_file(self, parser, tmp_path, dummy_metadata):
        """Should return failure for non-existent file."""
        fake_path = tmp_path / "nonexistent.pdf"
        result = parser.parse_document(fake_path, dummy_metadata)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_parse_url_not_configured(self, dummy_metadata, tmp_path):
        """Should return failure when URL is empty."""
        p = TikaParser(url="")
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        result = p.parse_document(pdf_path, dummy_metadata)

        assert result.success is False
        assert "not configured" in result.error.lower()

    def test_parse_document_exception(self, parser, test_pdf, dummy_metadata):
        """Should handle unexpected exceptions gracefully."""
        with patch.object(
            parser.client,
            "extract_text",
            side_effect=Exception("unexpected error"),
        ):
            result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is False
        assert "unexpected error" in result.error.lower()

    def test_parse_uses_context_title_fallback(self, parser, test_pdf, dummy_metadata):
        """When Tika metadata and text both lack title, use context metadata title."""
        # Tika text is very short lines (< 4 chars) so no title extracted from text
        with (
            patch.object(
                parser.client,
                "extract_text",
                return_value="OK\n\nHi",
            ),
            patch.object(
                parser.client,
                "extract_metadata",
                return_value={},
            ),
        ):
            result = parser.parse_document(test_pdf, dummy_metadata)

        assert result.success is True
        content = result.markdown_path.read_text()
        # Should fall back to context metadata title
        assert "# Test Document" in content


class TestExtractMetadata:
    def test_extracts_standard_keys(self, parser):
        tika_meta = {
            "title": "My Title",
            "author": "Jane Doe",
            "page_count": 10,
            "content_type": "application/pdf",
        }
        result = parser._extract_metadata(tika_meta, "some text")
        assert result["title"] == "My Title"
        assert result["author"] == "Jane Doe"
        assert result["page_count"] == 10
        assert result["parsed_by"] == "tika"

    def test_fallback_title_from_text(self, parser):
        """Should extract title from first non-empty line if not in metadata."""
        result = parser._extract_metadata({}, "First line as title\n\nBody.")
        assert result["title"] == "First line as title"

    def test_no_title_if_short_lines(self, parser):
        """Should skip very short lines (<=3 chars) for title extraction."""
        result = parser._extract_metadata({}, "ab\n\nOK\n\nHi")
        assert "title" not in result


class TestTextToMarkdown:
    def test_with_title(self, parser):
        md = parser._text_to_markdown("Hello world.", title="My Title")
        assert md.startswith("# My Title\n")
        assert "Hello world." in md

    def test_without_title(self, parser):
        md = parser._text_to_markdown("Hello world.")
        assert not md.startswith("# ")
        assert "Hello world." in md

    def test_preserves_paragraphs(self, parser):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird."
        md = parser._text_to_markdown(text)
        assert "First paragraph." in md
        assert "Second paragraph." in md
        assert "Third." in md


class TestProperties:
    def test_name_property(self, parser):
        assert parser.name == "tika"

    def test_supported_formats(self, parser):
        formats = parser.get_supported_formats()
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".html" in formats
        assert ".csv" in formats
        assert ".epub" in formats
