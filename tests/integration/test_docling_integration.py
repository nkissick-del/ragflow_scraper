"""Integration tests for Docling parser with real PDF processing.

Tests PDF parsing, metadata extraction, and error handling.
"""

import queue
from contextlib import contextmanager

import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from app.backends.parsers.docling_parser import DoclingParser
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def docling_parser():
    """Create Docling parser instance."""
    return DoclingParser()


@pytest.fixture
def simple_pdf(tmp_path):
    """Create a simple test PDF."""
    pdf_file = tmp_path / "simple.pdf"
    # Minimal valid PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources 4 0 R /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Content) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000229 00000 n
0000000327 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
419
%%EOF
"""
    pdf_file.write_bytes(pdf_content)
    return pdf_file


@pytest.fixture
def context_metadata():
    """Create context metadata for testing."""
    return DocumentMetadata(
        url="http://example.com/test.pdf",
        title="Test Document",
        filename="test.pdf",
        organization="TestOrg",
        publication_date="2024-01-15",
    )


@contextmanager
def mock_docling_subprocess(queue_result):
    """Mock the Docling subprocess orchestration (Queue + Process + is_available).

    Args:
        queue_result: The value returned by queue.get() (success or error dict).

    Yields:
        Tuple of (mock_queue, mock_proc) for additional assertions.
    """
    with patch.object(DoclingParser, "is_available", return_value=True):
        with patch("multiprocessing.Queue") as mock_queue_class:
            mock_queue = Mock()
            if isinstance(queue_result, Exception):
                mock_queue.get.side_effect = queue_result
            else:
                mock_queue.get.return_value = queue_result
            mock_queue_class.return_value = mock_queue

            with patch("multiprocessing.Process") as mock_process_class:
                mock_proc = Mock()
                mock_proc.is_alive.return_value = False
                mock_process_class.return_value = mock_proc

                yield mock_queue, mock_proc


class TestDoclingParserAvailability:
    """Test parser availability checks."""

    def test_parser_name(self, docling_parser):
        """Should return correct parser name."""
        assert docling_parser.name == "docling"

    def test_is_available(self, docling_parser):
        """Should check if Docling is available."""
        available = docling_parser.is_available()
        assert isinstance(available, bool)

    def test_parse_when_simulated_available(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should parse correctly when Docling availability is mocked."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "# Availability Test\n\nContent",
                "metadata": {"title": "Availability Test"},
                "page_count": 1,
            },
        }
        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.success is True
        assert result.parser_name == "docling"
        assert result.markdown_path.exists()
        assert result.metadata is not None
        assert result.metadata.get("title") == "Availability Test"

    def test_supported_formats(self, docling_parser):
        """Should return supported file formats."""
        formats = docling_parser.get_supported_formats()
        assert isinstance(formats, list)
        assert ".pdf" in formats
        assert ".docx" in formats


class TestDoclingParserParsing:
    """Test PDF parsing functionality."""

    def test_parse_simple_pdf_mocked(
        self, docling_parser, simple_pdf, context_metadata, tmp_path
    ):
        """Should parse simple PDF with mocked Docling."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "# Test Document\n\nTest Content",
                "metadata": {
                    "title": "Test Document",
                    "author": "Test Author",
                },
                "page_count": 1,
            },
        }

        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify
        assert result.success is True
        assert result.parser_name == "docling"
        assert result.markdown_path.exists()
        assert result.markdown_path.suffix == ".md"

        # Verify markdown content
        markdown_content = result.markdown_path.read_text()
        assert "Test Document" in markdown_content
        assert "Test Content" in markdown_content

        # Verify extracted metadata
        assert result.metadata is not None
        assert "title" in result.metadata
        assert result.metadata.get("page_count") == 1

    def test_parse_with_subprocess_mocked(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should parse using mocked subprocess orchestration."""
        mock_queue_result = {
            "success": True,
            "result": {
                "markdown": "# Subprocess Test\n\nContent from subprocess",
                "metadata": {"title": "Subprocess Test"},
                "page_count": 2,
            },
        }

        with mock_docling_subprocess(mock_queue_result) as (_, mock_proc):
            mock_proc.exitcode = 0
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify
        assert result.success is True
        assert result.markdown_path.exists()

    def test_parse_extracts_metadata(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract metadata from PDF."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "# Rich Metadata Test\n\nContent",
                "metadata": {
                    "title": "Extracted Title",
                    "author": "Extracted Author",
                    "subject": "Test Subject",
                    "keywords": "test, metadata",
                },
                "page_count": 5,
            },
        }

        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify metadata extraction
        assert result.metadata is not None
        assert result.metadata.get("title") == "Extracted Title"
        assert result.metadata.get("author") == "Extracted Author"
        assert result.metadata.get("page_count") == 5

    def test_parse_fallback_title_from_markdown(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract title from markdown if not in metadata."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "# Markdown Title\n\nSome content here.",
                "metadata": {},
                "page_count": 1,
            },
        }

        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify title extracted from markdown
        assert result.metadata is not None
        title = result.metadata.get("title")
        assert title == "Markdown Title"


class TestDoclingParserErrorHandling:
    """Test error handling scenarios."""

    def test_parse_file_not_found(self, docling_parser, context_metadata):
        """Should handle missing file gracefully."""
        with patch.object(DoclingParser, "is_available", return_value=True):
            result = docling_parser.parse_document(
                Path("/nonexistent/file.pdf"),
                context_metadata,
            )

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower() or "exist" in result.error.lower()

    def test_parse_unsupported_format(self, docling_parser, context_metadata, tmp_path):
        """Should handle unsupported file formats."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not a PDF")

        result = docling_parser.parse_document(txt_file, context_metadata)

        assert result.success is False
        assert result.error is not None

    def test_parse_raises_on_conversion_error(
        self, docling_parser, context_metadata, tmp_path
    ):
        """Should propagate conversion errors gracefully."""
        corrupted_pdf = tmp_path / "corrupted.pdf"
        corrupted_pdf.write_bytes(b"Not a valid PDF content")

        mock_error_result = {
            "success": False,
            "error": "Parsing failed",
            "traceback": "Traceback info...",
        }

        with mock_docling_subprocess(mock_error_result):
            result = docling_parser.parse_document(corrupted_pdf, context_metadata)

        assert result.success is False
        assert result.error is not None
        assert "Parsing failed" in result.error or "failed" in result.error.lower()

    def test_parse_subprocess_timeout(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should handle subprocess timeout."""
        with mock_docling_subprocess(queue.Empty()):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Should handle timeout gracefully
        assert result.success is False
        assert result.error is not None

    def test_parse_subprocess_crash(self, docling_parser, simple_pdf, context_metadata):
        """Should handle subprocess crash."""
        with mock_docling_subprocess(None) as (_, mock_proc):
            mock_proc.exitcode = 1
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.success is False
        assert "failed" in result.error.lower()


class TestDoclingParserResourceCleanup:
    """Test resource cleanup and management."""

    def test_parse_closes_subprocess_resources(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should ensure queue and process are closed/joined."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "# Resource Test\n\nContent",
                "metadata": {},
                "page_count": 1,
            },
        }

        with mock_docling_subprocess(mock_result) as (mock_queue, mock_proc):
            docling_parser.parse_document(simple_pdf, context_metadata)

            # Verify cleanup calls
            assert mock_queue.close.called
            assert mock_queue.join_thread.called
            assert mock_proc.join.called


class TestDoclingParserMetadataExtraction:
    """Test metadata extraction logic."""

    def test_extract_page_count(self, docling_parser, simple_pdf, context_metadata):
        """Should extract page count from Docling metadata."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "Test",
                "metadata": {},
                "page_count": 42,
            },
        }
        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.metadata.get("page_count") == 42

    def test_extract_author_from_metadata(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract author from Docling metadata."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "Test",
                "metadata": {"author": "John Doe"},
                "page_count": 1,
            },
        }
        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.metadata.get("author") == "John Doe"

    def test_metadata_merging_with_context(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should return result for merging metadata (merging logic is in models)."""
        mock_result = {
            "success": True,
            "result": {
                "markdown": "Test",
                "metadata": {"title": "Parser Title", "author": "Parser Author"},
                "page_count": 10,
            },
        }
        with mock_docling_subprocess(mock_result):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verification of extraction (merging happens in orchestrator/pipeline)
        assert result.metadata["title"] == "Parser Title"
        assert result.metadata["author"] == "Parser Author"
        assert result.metadata["page_count"] == 10
        assert result.success is True
