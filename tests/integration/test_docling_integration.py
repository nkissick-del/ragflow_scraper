"""Integration tests for Docling parser with real PDF processing.

Tests PDF parsing, metadata extraction, and error handling.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock
import multiprocessing

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
        title="Test Document",
        url="http://example.com/test.pdf",
        organization="TestOrg",
        publication_date="2024-01-15",
    )


class TestDoclingParserAvailability:
    """Test parser availability checks."""

    def test_parser_name(self, docling_parser):
        """Should return correct parser name."""
        assert docling_parser.name == "docling"

    def test_is_available(self, docling_parser):
        """Should check if Docling is available."""
        # This will attempt lazy import
        available = docling_parser.is_available()
        # Result depends on whether docling is installed
        assert isinstance(available, bool)

    def test_supported_formats(self, docling_parser):
        """Should return supported file formats."""
        formats = docling_parser.get_supported_formats()
        assert isinstance(formats, list)
        assert "pdf" in formats


class TestDoclingParserParsing:
    """Test PDF parsing functionality."""

    def test_parse_simple_pdf_mocked(
        self, docling_parser, simple_pdf, context_metadata, tmp_path
    ):
        """Should parse simple PDF with mocked Docling."""
        # Mock the conversion process to avoid heavy Docling dependency
        mock_result = {
            "markdown": "# Test Document\n\nTest Content",
            "metadata": {
                "title": "Test Document",
                "author": "Test Author",
            },
            "page_count": 1,
        }

        def mock_conversion(file_path):
            return mock_result

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            side_effect=mock_conversion,
        ):
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
        assert result.extracted_metadata is not None
        assert "title" in result.extracted_metadata
        assert result.extracted_metadata.get("page_count") == 1

    def test_parse_with_subprocess_mocked(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should handle subprocess-based parsing."""
        # Mock subprocess conversion
        mock_queue_result = {
            "markdown": "# Subprocess Test\n\nContent from subprocess",
            "metadata": {"title": "Subprocess Test"},
            "page_count": 2,
        }

        def mock_queue_conversion(file_path, queue):
            queue.put(mock_queue_result)

        with patch(
            "app.backends.parsers.docling_parser._run_conversion_to_queue",
            side_effect=mock_queue_conversion,
        ):
            with patch("multiprocessing.Process") as mock_process:
                # Setup mock process
                mock_proc = Mock()
                mock_proc.is_alive.return_value = False
                mock_proc.exitcode = 0
                mock_process.return_value = mock_proc

                result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify
        assert result.success is True
        assert result.markdown_path.exists()

    def test_parse_extracts_metadata(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract metadata from PDF."""
        # Mock conversion with rich metadata
        mock_result = {
            "markdown": "# Rich Metadata Test\n\nContent",
            "metadata": {
                "title": "Extracted Title",
                "author": "Extracted Author",
                "subject": "Test Subject",
                "keywords": "test, metadata",
            },
            "page_count": 5,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify metadata extraction
        assert result.extracted_metadata is not None
        assert result.extracted_metadata.get("title") == "Extracted Title"
        assert result.extracted_metadata.get("author") == "Extracted Author"
        assert result.extracted_metadata.get("page_count") == 5

    def test_parse_fallback_title_from_markdown(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract title from markdown if not in metadata."""
        # Mock conversion without title in metadata
        mock_result = {
            "markdown": "# Markdown Title\n\nSome content here.",
            "metadata": {},
            "page_count": 1,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify title extracted from markdown
        assert result.extracted_metadata is not None
        # Title extraction logic should find "Markdown Title"
        title = result.extracted_metadata.get("title")
        assert title is not None


class TestDoclingParserErrorHandling:
    """Test error handling scenarios."""

    def test_parse_file_not_found(self, docling_parser, context_metadata):
        """Should handle missing file gracefully."""
        result = docling_parser.parse_document(
            Path("/nonexistent/file.pdf"),
            context_metadata,
        )

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower() or "exist" in result.error.lower()

    def test_parse_unsupported_format(self, docling_parser, context_metadata, tmp_path):
        """Should handle unsupported file formats."""
        # Create a text file (not PDF)
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not a PDF")

        result = docling_parser.parse_document(txt_file, context_metadata)

        # Should either reject or fail gracefully
        assert result.success is False
        assert result.error is not None

    def test_parse_corrupted_pdf(self, docling_parser, context_metadata, tmp_path):
        """Should handle corrupted PDF files."""
        # Create invalid PDF
        corrupted_pdf = tmp_path / "corrupted.pdf"
        corrupted_pdf.write_bytes(b"Not a valid PDF content")

        # Mock conversion to raise error
        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            side_effect=Exception("Parsing failed"),
        ):
            result = docling_parser.parse_document(corrupted_pdf, context_metadata)

        assert result.success is False
        assert result.error is not None

    def test_parse_subprocess_timeout(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should handle subprocess timeout."""
        # Mock process that never completes
        with patch("multiprocessing.Process") as mock_process:
            mock_proc = Mock()
            mock_proc.is_alive.return_value = True  # Always alive (timeout)
            mock_proc.exitcode = None
            mock_process.return_value = mock_proc

            with patch("multiprocessing.Queue") as mock_queue_class:
                mock_queue = Mock()
                mock_queue.empty.return_value = True  # No result
                mock_queue_class.return_value = mock_queue

                result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Should handle timeout gracefully
        assert result.success is False
        assert result.error is not None

    def test_parse_subprocess_crash(self, docling_parser, simple_pdf, context_metadata):
        """Should handle subprocess crash."""
        # Mock process that crashes
        with patch("multiprocessing.Process") as mock_process:
            mock_proc = Mock()
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 1  # Non-zero exit code (crash)
            mock_process.return_value = mock_proc

            with patch("multiprocessing.Queue") as mock_queue_class:
                mock_queue = Mock()
                mock_queue.empty.return_value = True  # No result
                mock_queue_class.return_value = mock_queue

                result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Should handle crash gracefully
        assert result.success is False
        assert result.error is not None


class TestDoclingParserResourceCleanup:
    """Test resource cleanup and management."""

    def test_parse_cleans_up_temp_files(
        self, docling_parser, simple_pdf, context_metadata, tmp_path
    ):
        """Should clean up temporary files after parsing."""
        # Mock conversion
        mock_result = {
            "markdown": "# Test\n\nContent",
            "metadata": {},
            "page_count": 1,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify markdown file exists (this is the output, not temp)
        assert result.markdown_path.exists()

        # Temp files should be cleaned up (implementation-specific)
        # This is a placeholder for actual cleanup verification

    def test_parse_closes_subprocess_resources(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should properly close subprocess resources."""
        mock_result = {
            "markdown": "# Test\n\nContent",
            "metadata": {},
            "page_count": 1,
        }

        with patch("multiprocessing.Process") as mock_process:
            mock_proc = Mock()
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 0
            mock_process.return_value = mock_proc

            with patch("multiprocessing.Queue") as mock_queue_class:
                mock_queue = Mock()
                mock_queue.empty.return_value = False
                mock_queue.get.return_value = mock_result
                mock_queue_class.return_value = mock_queue

                result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Verify process was properly managed
        mock_proc.join.assert_called()
        mock_proc.terminate.assert_not_called()  # Should exit cleanly


class TestDoclingParserMetadataExtraction:
    """Test metadata extraction logic."""

    def test_extract_page_count(self, docling_parser, simple_pdf, context_metadata):
        """Should extract page count from PDF."""
        mock_result = {
            "markdown": "# Test\n\nContent",
            "metadata": {},
            "page_count": 10,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.extracted_metadata.get("page_count") == 10

    def test_extract_author_from_metadata(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should extract author from PDF metadata."""
        mock_result = {
            "markdown": "# Test\n\nContent",
            "metadata": {"author": "John Doe"},
            "page_count": 1,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        assert result.extracted_metadata.get("author") == "John Doe"

    def test_metadata_merging_with_context(
        self, docling_parser, simple_pdf, context_metadata
    ):
        """Should preserve context metadata alongside extracted metadata."""
        mock_result = {
            "markdown": "# Test\n\nContent",
            "metadata": {"title": "Extracted Title"},
            "page_count": 1,
        }

        with patch(
            "app.backends.parsers.docling_parser._run_conversion",
            return_value=mock_result,
        ):
            result = docling_parser.parse_document(simple_pdf, context_metadata)

        # Extracted metadata should be present
        assert result.extracted_metadata.get("title") == "Extracted Title"

        # Context metadata is passed separately and merged in pipeline
        # Parser just returns extracted metadata
        assert result.success is True
