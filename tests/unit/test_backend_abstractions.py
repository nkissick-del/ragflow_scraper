"""Unit tests for backend abstract base classes."""

import pytest
from pathlib import Path

from app.backends import (
    ParserBackend,
    ParserResult,
    ArchiveBackend,
    ArchiveResult,
    RAGBackend,
    RAGResult,
)
from app.scrapers.models import DocumentMetadata


class TestParserResult:
    """Test ParserResult dataclass validation."""

    def test_success_requires_markdown_path(self):
        """Successful parse must include markdown_path."""
        with pytest.raises(ValueError, match="must include markdown_path"):
            ParserResult(success=True, metadata={})

    def test_failure_requires_error(self):
        """Failed parse must include error message."""
        with pytest.raises(ValueError, match="must include error message"):
            ParserResult(success=False)

    def test_valid_success_result(self):
        """Valid success result."""
        result = ParserResult(
            success=True,
            markdown_path=Path("/tmp/test.md"),
            metadata={"title": "Test"},
            parser_name="test_parser",
        )
        assert result.success
        assert result.markdown_path == Path("/tmp/test.md")
        assert result.metadata == {"title": "Test"}

    def test_valid_failure_result(self):
        """Valid failure result."""
        result = ParserResult(
            success=False, error="Parse failed", parser_name="test_parser"
        )
        assert not result.success
        assert result.error == "Parse failed"


class TestArchiveResult:
    """Test ArchiveResult dataclass validation."""

    def test_success_requires_document_id(self):
        """Successful archive must include document_id."""
        with pytest.raises(ValueError, match="must include document_id"):
            ArchiveResult(success=True, url="http://example.com")

    def test_failure_requires_error(self):
        """Failed archive must include error message."""
        with pytest.raises(ValueError, match="must include error message"):
            ArchiveResult(success=False)

    def test_valid_success_result(self):
        """Valid success result."""
        result = ArchiveResult(
            success=True,
            document_id="123",
            url="http://example.com/doc/123",
            archive_name="test_archive",
        )
        assert result.success
        assert result.document_id == "123"

    def test_valid_failure_result(self):
        """Valid failure result."""
        result = ArchiveResult(
            success=False, error="Archive failed", archive_name="test_archive"
        )
        assert not result.success
        assert result.error == "Archive failed"


class TestRAGResult:
    """Test RAGResult dataclass validation."""

    def test_failure_requires_error(self):
        """Failed RAG ingestion must include error message."""
        with pytest.raises(ValueError, match="must include error message"):
            RAGResult(success=False)

    def test_valid_success_result(self):
        """Valid success result."""
        result = RAGResult(
            success=True,
            document_id="abc",
            collection_id="col1",
            rag_name="test_rag",
        )
        assert result.success
        assert result.document_id == "abc"

    def test_valid_failure_result(self):
        """Valid failure result."""
        result = RAGResult(success=False, error="Ingestion failed", rag_name="test_rag")
        assert not result.success
        assert result.error == "Ingestion failed"


class TestParserBackend:
    """Test ParserBackend ABC."""

    def test_cannot_instantiate(self):
        """Cannot instantiate abstract class."""
        with pytest.raises(TypeError):
            ParserBackend()

    def test_must_implement_parse_document(self):
        """Subclass must implement parse_document."""

        class IncompleteParser(ParserBackend):
            def is_available(self):
                return True

            def get_supported_formats(self):
                return [".pdf"]

            @property
            def name(self):
                return "incomplete"

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_valid_implementation(self):
        """Valid implementation with all methods."""

        class ValidParser(ParserBackend):
            def parse_document(self, pdf_path, context_metadata):
                return ParserResult(
                    success=True,
                    markdown_path=Path("/tmp/test.md"),
                    metadata={},
                    parser_name="valid",
                )

            def is_available(self):
                return True

            def get_supported_formats(self):
                return [".pdf"]

            @property
            def name(self):
                return "valid"

        parser = ValidParser()
        assert parser.is_available()
        assert parser.get_supported_formats() == [".pdf"]
        assert parser.name == "valid"


class TestArchiveBackend:
    """Test ArchiveBackend ABC."""

    def test_cannot_instantiate(self):
        """Cannot instantiate abstract class."""
        with pytest.raises(TypeError):
            ArchiveBackend()

    def test_must_implement_archive_document(self):
        """Subclass must implement archive_document."""

        class IncompleteArchive(ArchiveBackend):
            def verify_document(self, document_id, timeout=60):
                return True

            def is_configured(self):
                return True

            @property
            def name(self):
                return "incomplete"

        with pytest.raises(TypeError):
            IncompleteArchive()

    def test_valid_implementation(self):
        """Valid implementation with all methods."""

        class ValidArchive(ArchiveBackend):
            def archive_document(
                self, file_path, title, created=None, correspondent=None, tags=None, metadata=None
            ):
                return ArchiveResult(
                    success=True, document_id="123", archive_name="valid"
                )

            def verify_document(self, document_id, timeout=60):
                return True

            def is_configured(self):
                return True

            @property
            def name(self):
                return "valid"

        archive = ValidArchive()
        assert archive.is_configured()
        assert archive.name == "valid"


class TestRAGBackend:
    """Test RAGBackend ABC."""

    def test_cannot_instantiate(self):
        """Cannot instantiate abstract class."""
        with pytest.raises(TypeError):
            RAGBackend()

    def test_must_implement_ingest_document(self):
        """Subclass must implement ingest_document."""

        class IncompleteRAG(RAGBackend):
            def is_configured(self):
                return True

            def test_connection(self):
                return True

            @property
            def name(self):
                return "incomplete"

        with pytest.raises(TypeError):
            IncompleteRAG()

    def test_valid_implementation(self):
        """Valid implementation with all methods."""

        class ValidRAG(RAGBackend):
            def ingest_document(self, markdown_path, metadata, collection_id=None):
                return RAGResult(success=True, document_id="abc", rag_name="valid")

            def is_configured(self):
                return True

            def test_connection(self):
                return True

            @property
            def name(self):
                return "valid"

        rag = ValidRAG()
        assert rag.is_configured()
        assert rag.test_connection()
        assert rag.name == "valid"
