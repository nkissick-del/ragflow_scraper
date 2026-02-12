"""Tests for Docling parser backend."""

import pytest
from pathlib import Path
from queue import Empty
from unittest.mock import MagicMock, patch, PropertyMock

from app.backends.parsers.docling_parser import DoclingParser
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def parser():
    """Create test parser with docling marked as available."""
    p = DoclingParser()
    p._docling_available = True
    return p


@pytest.fixture
def unavailable_parser():
    """Create test parser with docling marked as unavailable."""
    p = DoclingParser()
    p._docling_available = False
    return p


@pytest.fixture
def context_metadata():
    """Create minimal context metadata for tests."""
    return DocumentMetadata(
        url="http://example.com/test.pdf",
        title="Test Document",
        filename="test.pdf",
    )


class TestInitialization:
    """Test parser initialization."""

    def test_init_sets_docling_available_none(self):
        """Should initialize with _docling_available as None."""
        p = DoclingParser()
        assert p._docling_available is None

    def test_name_property(self, parser):
        """Should return correct parser name."""
        assert parser.name == "docling"


class TestIsAvailable:
    """Test Docling availability checking."""

    def test_available_cached_true(self, parser):
        """Should return cached True without re-importing."""
        assert parser.is_available() is True

    def test_available_cached_false(self, unavailable_parser):
        """Should return cached False without re-importing."""
        assert unavailable_parser.is_available() is False

    def test_available_import_success(self):
        """Should set _docling_available=True when import succeeds."""
        p = DoclingParser()
        with patch.dict("sys.modules", {"docling": MagicMock()}):
            assert p.is_available() is True
            assert p._docling_available is True

    def test_available_import_failure(self):
        """Should set _docling_available=False when import fails."""
        p = DoclingParser()
        with patch("builtins.__import__", side_effect=ImportError("No module named 'docling'")):
            assert p.is_available() is False
            assert p._docling_available is False


class TestGetSupportedFormats:
    """Test supported formats."""

    def test_returns_expected_formats(self, parser):
        """Should include pdf, docx, pptx, html."""
        formats = parser.get_supported_formats()
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".pptx" in formats
        assert ".html" in formats


class TestParseDocument:
    """Test document parsing."""

    def test_parse_not_available(self, unavailable_parser, tmp_path, context_metadata):
        """Should return error when docling not available."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        result = unavailable_parser.parse_document(test_file, context_metadata)
        assert result.success is False
        assert "not available" in result.error.lower()
        assert result.parser_name == "docling"

    def test_parse_file_not_found(self, parser, context_metadata):
        """Should return error when file doesn't exist."""
        result = parser.parse_document(Path("/nonexistent/file.pdf"), context_metadata)
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_parse_success(self, parser, tmp_path, context_metadata):
        """Should successfully parse document and write markdown."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        queue_result = {
            "success": True,
            "result": {
                "markdown": "# Test Title\n\nContent here.",
                "metadata": {"title": "Test Title", "author": "Author"},
                "page_count": 3,
            },
        }

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_queue = MagicMock()
        mock_queue.get.return_value = queue_result

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is True
        assert result.markdown_path == test_file.with_suffix(".md")
        assert result.markdown_path.exists()
        assert result.markdown_path.read_text() == "# Test Title\n\nContent here."
        assert result.metadata["title"] == "Test Title"
        assert result.metadata["page_count"] == 3
        assert result.parser_name == "docling"

    def test_parse_timeout(self, parser, tmp_path, context_metadata):
        """Should handle queue timeout (Empty exception)."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        mock_queue = MagicMock()
        mock_queue.get.side_effect = Empty()

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        assert "timed out" in result.error.lower()
        mock_process.terminate.assert_called()

    def test_parse_timeout_process_dead(self, parser, tmp_path, context_metadata):
        """Should handle timeout when process already exited."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_queue = MagicMock()
        mock_queue.get.side_effect = Empty()

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_parse_timeout_kill_after_terminate(self, parser, tmp_path, context_metadata):
        """Should kill process if it's still alive after terminate."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        mock_process = MagicMock()
        # is_alive returns True for terminate check, True for kill check, then False for finally
        mock_process.is_alive.side_effect = [True, True, False]
        mock_queue = MagicMock()
        mock_queue.get.side_effect = Empty()

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        mock_process.terminate.assert_called()
        mock_process.kill.assert_called()

    def test_parse_conversion_failure(self, parser, tmp_path, context_metadata):
        """Should return error when conversion fails."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        queue_result = {
            "success": False,
            "error": "Conversion error details",
            "traceback": "Traceback...",
        }

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_queue = MagicMock()
        mock_queue.get.return_value = queue_result

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        assert "Conversion error details" in result.error

    def test_parse_conversion_failure_none_result(self, parser, tmp_path, context_metadata):
        """Should return error when queue returns None."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_queue = MagicMock()
        mock_queue.get.return_value = None

        with patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp:
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        assert "failed" in result.error.lower()

    def test_parse_write_error(self, parser, tmp_path, context_metadata):
        """Should handle OSError when writing markdown file."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        queue_result = {
            "success": True,
            "result": {
                "markdown": "# Test",
                "metadata": {},
                "page_count": 1,
            },
        }

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_queue = MagicMock()
        mock_queue.get.return_value = queue_result

        with (
            patch("app.backends.parsers.docling_parser.multiprocessing") as mock_mp,
            patch.object(Path, "write_text", side_effect=OSError("Permission denied")),
        ):
            mock_mp.Queue.return_value = mock_queue
            mock_mp.Process.return_value = mock_process
            result = parser.parse_document(test_file, context_metadata)

        # OSError is re-raised and caught by outer handler
        assert result.success is False
        assert "Permission denied" in result.error

    def test_parse_general_exception(self, parser, tmp_path, context_metadata):
        """Should handle unexpected exceptions."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        with patch(
            "app.backends.parsers.docling_parser.multiprocessing"
        ) as mock_mp:
            mock_mp.Queue.side_effect = RuntimeError("Unexpected failure")
            result = parser.parse_document(test_file, context_metadata)

        assert result.success is False
        assert "Unexpected failure" in result.error


class TestExtractMetadata:
    """Test metadata extraction."""

    def test_extract_full_metadata(self, parser):
        """Should extract title, author, creation_date from docling metadata."""
        docling_meta = {
            "title": "Document Title",
            "author": "John Doe",
            "creation_date": "2024-01-15",
        }
        result = parser._extract_metadata(docling_meta, 5, "# Heading\nContent")
        assert result["title"] == "Document Title"
        assert result["author"] == "John Doe"
        assert result["creation_date"] == "2024-01-15"
        assert result["parsed_by"] == "docling"
        assert result["page_count"] == 5

    def test_extract_empty_docling_metadata(self, parser):
        """Should handle empty docling metadata."""
        result = parser._extract_metadata({}, None, "No headings here")
        assert result["parsed_by"] == "docling"
        assert result["page_count"] is None
        assert "title" not in result

    def test_extract_none_docling_metadata(self, parser):
        """Should handle None docling metadata."""
        result = parser._extract_metadata(None, 1, "No headings")
        assert result["parsed_by"] == "docling"

    def test_extract_title_from_h1_heading(self, parser):
        """Should extract title from first H1 heading when not in metadata."""
        result = parser._extract_metadata({}, 1, "# First Heading\nContent")
        assert result["title"] == "First Heading"

    def test_extract_title_from_h2_heading(self, parser):
        """Should extract title from first H2 heading when no H1."""
        result = parser._extract_metadata({}, 1, "## Second Heading\nContent")
        assert result["title"] == "Second Heading"

    def test_extract_title_prefers_metadata_over_heading(self, parser):
        """Should prefer metadata title over heading title."""
        docling_meta = {"title": "Metadata Title"}
        result = parser._extract_metadata(docling_meta, 1, "# Heading Title\nContent")
        assert result["title"] == "Metadata Title"

    def test_extract_title_no_heading_found(self, parser):
        """Should not set title when no heading and no metadata title."""
        result = parser._extract_metadata({}, 1, "Just plain text\nNo headings")
        assert "title" not in result

    def test_extract_partial_metadata(self, parser):
        """Should handle metadata with only some fields."""
        docling_meta = {"title": "Only Title"}
        result = parser._extract_metadata(docling_meta, 2, "Content")
        assert result["title"] == "Only Title"
        assert "author" not in result
        assert "creation_date" not in result
