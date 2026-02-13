"""Tests for RAGFlow RAG backend adapter."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.backends.rag.ragflow_adapter import RAGFlowBackend


@pytest.fixture
def mock_client():
    """Create a mock RAGFlowClient."""
    client = MagicMock()
    client.api_url = "http://localhost:9380"
    client.api_key = "test-api-key"
    return client


@pytest.fixture
def backend(mock_client):
    """Create test backend with mock client."""
    return RAGFlowBackend(client=mock_client)


@pytest.fixture
def unconfigured_client():
    """Create a mock RAGFlowClient that is not configured."""
    client = MagicMock()
    client.api_url = ""
    client.api_key = ""
    return client


@pytest.fixture
def unconfigured_backend(unconfigured_client):
    """Create backend that is not configured."""
    return RAGFlowBackend(client=unconfigured_client)


class TestInitialization:
    """Test backend initialization."""

    def test_init_with_injected_client(self, mock_client):
        """Should use injected client."""
        backend = RAGFlowBackend(client=mock_client)
        assert backend.client is mock_client

    def test_init_default_client(self):
        """Should create default RAGFlowClient when none provided."""
        with patch("app.backends.rag.ragflow_adapter.RAGFlowClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            RAGFlowBackend()
            mock_cls.assert_called_once()

    def test_name_property(self, backend):
        """Should return correct backend name."""
        assert backend.name == "ragflow"


class TestIsConfigured:
    """Test configuration checking."""

    def test_configured_with_url_and_key(self, backend):
        """Should return True when URL and key are set."""
        assert backend.is_configured() is True

    def test_not_configured_missing_url(self, unconfigured_client):
        """Should return False when URL is missing."""
        unconfigured_client.api_url = ""
        unconfigured_client.api_key = "some-key"
        backend = RAGFlowBackend(client=unconfigured_client)
        assert backend.is_configured() is False

    def test_not_configured_missing_key(self, unconfigured_client):
        """Should return False when key is missing."""
        unconfigured_client.api_url = "http://localhost:9380"
        unconfigured_client.api_key = ""
        backend = RAGFlowBackend(client=unconfigured_client)
        assert backend.is_configured() is False

    def test_not_configured_both_missing(self, unconfigured_backend):
        """Should return False when both URL and key are missing."""
        assert unconfigured_backend.is_configured() is False


class TestTestConnection:
    """Test connection testing."""

    def test_connection_success(self, backend, mock_client):
        """Should return True when list_datasets returns a list."""
        mock_client.list_datasets.return_value = [{"id": "ds1", "name": "Test"}]
        assert backend.test_connection() is True

    def test_connection_empty_list(self, backend, mock_client):
        """Should return True even with empty list (it's still a list)."""
        mock_client.list_datasets.return_value = []
        assert backend.test_connection() is True

    def test_connection_not_configured(self, unconfigured_backend):
        """Should return False when not configured."""
        assert unconfigured_backend.test_connection() is False

    def test_connection_exception(self, backend, mock_client):
        """Should return False when exception occurs."""
        mock_client.list_datasets.side_effect = Exception("Connection refused")
        assert backend.test_connection() is False

    def test_connection_non_list_response(self, backend, mock_client):
        """Should return False when response is not a list."""
        mock_client.list_datasets.return_value = "unexpected"
        assert backend.test_connection() is False


class TestListDocuments:
    """Test document listing."""

    def test_list_documents_success(self, backend, mock_client):
        """Should return documents from client."""
        mock_client.list_documents.return_value = [
            {"id": "doc1", "name": "test.md"},
        ]
        result = backend.list_documents(collection_id="ds1")
        assert len(result) == 1
        assert result[0]["id"] == "doc1"

    def test_list_documents_not_configured(self, unconfigured_backend):
        """Should return empty list when not configured."""
        assert unconfigured_backend.list_documents(collection_id="ds1") == []

    def test_list_documents_no_collection_id(self, backend):
        """Should return empty list when no collection_id provided."""
        assert backend.list_documents() == []

    def test_list_documents_exception(self, backend, mock_client):
        """Should return empty list on exception."""
        mock_client.list_documents.side_effect = Exception("API error")
        assert backend.list_documents(collection_id="ds1") == []


class TestIngestDocument:
    """Test document ingestion."""

    def test_ingest_not_configured(self, unconfigured_backend, tmp_path):
        """Should return error when not configured."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        result = unconfigured_backend.ingest_document(test_file, {})
        assert result.success is False
        assert "not configured" in result.error.lower()
        assert result.rag_name == "ragflow"

    def test_ingest_file_not_found(self, backend):
        """Should return error when file doesn't exist."""
        result = backend.ingest_document(Path("/nonexistent/file.md"), {})
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_ingest_with_collection_id(self, backend, mock_client, tmp_path):
        """Should use provided collection_id directly."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Document")

        mock_upload_result = MagicMock()
        mock_upload_result.success = True
        mock_upload_result.document_id = "doc123"
        mock_client.upload_documents_with_metadata.return_value = [mock_upload_result]

        with patch.object(backend, "_prepare_metadata", return_value={"title": "Test"}):
            result = backend.ingest_document(
                test_file, {"title": "Test"}, collection_id="my-dataset"
            )

        assert result.success is True
        assert result.document_id == "doc123"
        assert result.collection_id == "my-dataset"

    def test_ingest_default_dataset_lookup(self, backend, mock_client, tmp_path):
        """Should look up default dataset when no collection_id provided."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_client.list_datasets.return_value = [{"id": "default-ds", "name": "Default"}]
        mock_upload_result = MagicMock()
        mock_upload_result.success = True
        mock_upload_result.document_id = "doc456"
        mock_client.upload_documents_with_metadata.return_value = [mock_upload_result]

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {})

        assert result.success is True
        assert result.collection_id == "default-ds"

    def test_ingest_no_datasets_found(self, backend, mock_client, tmp_path):
        """Should return error when no datasets exist and no collection_id."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        mock_client.list_datasets.return_value = []

        result = backend.ingest_document(test_file, {})
        assert result.success is False
        assert "no ragflow datasets" in result.error.lower()

    def test_ingest_invalid_dataset_response_not_list(self, backend, mock_client, tmp_path):
        """Should return error when datasets response is not a list."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        mock_client.list_datasets.return_value = "invalid"

        result = backend.ingest_document(test_file, {})
        assert result.success is False

    def test_ingest_invalid_dataset_response_no_id(self, backend, mock_client, tmp_path):
        """Should return error when first dataset has no 'id' key."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        mock_client.list_datasets.return_value = [{"name": "no-id"}]

        result = backend.ingest_document(test_file, {})
        assert result.success is False

    def test_ingest_invalid_dataset_response_not_dict(self, backend, mock_client, tmp_path):
        """Should return error when first dataset element is not a dict."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        mock_client.list_datasets.return_value = ["not-a-dict"]

        result = backend.ingest_document(test_file, {})
        assert result.success is False

    def test_ingest_dataset_lookup_exception(self, backend, mock_client, tmp_path):
        """Should return error when dataset lookup throws."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")
        mock_client.list_datasets.side_effect = Exception("API error")

        result = backend.ingest_document(test_file, {})
        assert result.success is False
        assert "Failed to get default dataset" in result.error

    def test_ingest_upload_failure(self, backend, mock_client, tmp_path):
        """Should return error when upload fails."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_upload_result = MagicMock()
        mock_upload_result.success = False
        mock_upload_result.error = "Upload rejected"
        mock_upload_result.status = "failed"
        mock_client.upload_documents_with_metadata.return_value = [mock_upload_result]

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {}, collection_id="ds1")

        assert result.success is False
        assert "Upload rejected" in result.error

    def test_ingest_upload_failure_no_error_attr(self, backend, mock_client, tmp_path):
        """Should show status when upload result has no error attribute."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_upload_result = MagicMock()
        mock_upload_result.success = False
        mock_upload_result.error = None
        mock_upload_result.status = "rejected"
        mock_client.upload_documents_with_metadata.return_value = [mock_upload_result]

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {}, collection_id="ds1")

        assert result.success is False
        assert "rejected" in result.error.lower()

    def test_ingest_upload_empty_result(self, backend, mock_client, tmp_path):
        """Should return error when upload returns empty list."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_client.upload_documents_with_metadata.return_value = []

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {}, collection_id="ds1")

        assert result.success is False

    def test_ingest_upload_none_result(self, backend, mock_client, tmp_path):
        """Should return error when upload returns None."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_client.upload_documents_with_metadata.return_value = None

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {}, collection_id="ds1")

        assert result.success is False

    def test_ingest_exception(self, backend, mock_client, tmp_path):
        """Should handle exceptions during ingestion."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_client.upload_documents_with_metadata.side_effect = Exception(
            "Network error"
        )

        with patch.object(backend, "_prepare_metadata", return_value={}):
            result = backend.ingest_document(test_file, {}, collection_id="ds1")

        assert result.success is False
        assert "Network error" in result.error


class TestPrepareMetadata:
    """Test metadata preparation."""

    def test_prepare_delegates_to_helper(self, backend):
        """Should call prepare_metadata_for_ragflow helper."""
        metadata = {"title": "Test", "url": "http://example.com"}
        with patch(
            "app.services.ragflow_metadata.prepare_metadata_for_ragflow",
            return_value={"prepared": True},
        ) as mock_prepare:
            result = backend._prepare_metadata(metadata)
            mock_prepare.assert_called_once_with(metadata)
            assert result == {"prepared": True}

    def test_prepare_with_empty_metadata(self, backend):
        """Should handle empty metadata dict."""
        with patch(
            "app.services.ragflow_metadata.prepare_metadata_for_ragflow",
            return_value={},
        ):
            result = backend._prepare_metadata({})
            assert result == {}
