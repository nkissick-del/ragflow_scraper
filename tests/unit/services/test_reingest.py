"""Tests for ReconciliationService._reingest_document() helper."""

import pytest
from unittest.mock import Mock

from app.services.reconciliation import ReconciliationService


@pytest.fixture
def mock_container():
    """Create a mock ServiceContainer."""
    container = Mock()

    # Mock archive backend with a Paperless client
    mock_client = Mock()
    mock_client.is_configured = True
    mock_client.check_alive.return_value = True
    mock_client.get_scraper_document_urls.return_value = {}
    mock_client.download_document.return_value = b"%PDF test content"

    mock_archive = Mock()
    mock_archive.client = mock_client
    container.archive_backend = mock_archive

    # Mock state tracker
    mock_tracker = Mock()
    mock_tracker.get_processed_urls.return_value = []
    container.state_tracker.return_value = mock_tracker

    # Mock RAG backend
    mock_rag = Mock()
    mock_rag.list_documents.return_value = []
    mock_rag.ingest_document.return_value = Mock(success=True, document_id="rag-1", error=None)
    container.rag_backend = mock_rag

    # Mock parser backend
    mock_parse_result = Mock()
    mock_parse_result.success = True
    mock_parse_result.markdown_path = Mock()
    mock_parse_result.markdown_path.exists.return_value = True
    mock_parse_result.error = None
    mock_parser = Mock()
    mock_parser.parse_document.return_value = mock_parse_result
    container.parser_backend = mock_parser

    return container


@pytest.fixture
def service(mock_container):
    """Create ReconciliationService with mock container."""
    return ReconciliationService(container=mock_container)


@pytest.fixture
def mock_client(mock_container):
    """Return the mock Paperless client."""
    return mock_container.archive_backend.client


class TestReingestDocumentSuccess:
    """Test successful re-ingestion."""

    def test_success_returns_true(self, service, mock_client, mock_container):
        """Should return True on successful download, parse, and ingest."""
        result = service._reingest_document(
            doc_id=42,
            url="https://example.com/doc.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is True
        mock_client.download_document.assert_called_once_with(42)
        mock_container.parser_backend.parse_document.assert_called_once()
        mock_container.rag_backend.ingest_document.assert_called_once()

    def test_passes_dataset_id_to_rag(self, service, mock_client, mock_container):
        """Should pass dataset_id as collection_id to RAG backend."""
        service._reingest_document(
            doc_id=1,
            url="https://example.com/a.pdf",
            source="test",
            client=mock_client,
            dataset_id="my-dataset",
        )

        call_kwargs = mock_container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["collection_id"] == "my-dataset"

    def test_passes_none_dataset_id(self, service, mock_client, mock_container):
        """Should pass None as collection_id when no dataset configured."""
        service._reingest_document(
            doc_id=1,
            url="https://example.com/a.pdf",
            source="manual",
            client=mock_client,
            dataset_id=None,
        )

        call_kwargs = mock_container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["collection_id"] is None

    def test_passes_source_in_metadata(self, service, mock_client, mock_container):
        """Should include source label in RAG metadata."""
        service._reingest_document(
            doc_id=1,
            url="https://example.com/a.pdf",
            source="manual",
            client=mock_client,
        )

        call_kwargs = mock_container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["metadata"]["source"] == "manual"
        assert call_kwargs["metadata"]["url"] == "https://example.com/a.pdf"


class TestReingestDocumentDownloadFailure:
    """Test download failure handling."""

    def test_download_returns_none(self, service, mock_client, mock_container):
        """Should return False when download returns None."""
        mock_client.download_document.return_value = None

        result = service._reingest_document(
            doc_id=99,
            url="https://example.com/missing.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False
        mock_container.parser_backend.parse_document.assert_not_called()
        mock_container.rag_backend.ingest_document.assert_not_called()

    def test_download_returns_empty_bytes(self, service, mock_client, mock_container):
        """Should return False when download returns empty bytes."""
        mock_client.download_document.return_value = b""

        result = service._reingest_document(
            doc_id=99,
            url="https://example.com/empty.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False

    def test_download_raises_exception(self, service, mock_client, mock_container):
        """Should return False and not crash when download raises."""
        mock_client.download_document.side_effect = ConnectionError("timeout")

        result = service._reingest_document(
            doc_id=99,
            url="https://example.com/fail.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False


class TestReingestDocumentParseFailure:
    """Test parse failure handling."""

    def test_parse_returns_failure(self, service, mock_client, mock_container):
        """Should return False when parser returns success=False."""
        mock_parse_result = Mock()
        mock_parse_result.success = False
        mock_parse_result.markdown_path = None
        mock_parse_result.error = "OCR failed"
        mock_container.parser_backend.parse_document.return_value = mock_parse_result

        result = service._reingest_document(
            doc_id=1,
            url="https://example.com/bad.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False
        mock_container.rag_backend.ingest_document.assert_not_called()

    def test_parse_returns_no_markdown_path(self, service, mock_client, mock_container):
        """Should return False when parser returns no markdown_path."""
        mock_parse_result = Mock()
        mock_parse_result.success = True
        mock_parse_result.markdown_path = None
        mock_parse_result.error = None
        mock_container.parser_backend.parse_document.return_value = mock_parse_result

        result = service._reingest_document(
            doc_id=1,
            url="https://example.com/no-md.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False


class TestReingestDocumentIngestFailure:
    """Test RAG ingest failure handling."""

    def test_rag_ingest_returns_failure(self, service, mock_client, mock_container):
        """Should return False when RAG ingest returns success=False."""
        mock_container.rag_backend.ingest_document.return_value = Mock(
            success=False, error="Workspace full", document_id=None
        )

        result = service._reingest_document(
            doc_id=1,
            url="https://example.com/a.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False

    def test_rag_ingest_raises_exception(self, service, mock_client, mock_container):
        """Should return False when RAG ingest raises."""
        mock_container.rag_backend.ingest_document.side_effect = RuntimeError("connection lost")

        result = service._reingest_document(
            doc_id=1,
            url="https://example.com/a.pdf",
            source="reconciliation",
            client=mock_client,
        )

        assert result is False
