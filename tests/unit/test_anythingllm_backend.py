"""Tests for AnythingLLM backend adapter."""

import pytest
from pathlib import Path
from unittest.mock import patch

from app.backends.rag.anythingllm_adapter import AnythingLLMBackend
from app.services.anythingllm_client import UploadResult


@pytest.fixture
def backend():
    """Create test backend."""
    return AnythingLLMBackend(
        api_url="http://localhost:3001",
        api_key="test-key",
        workspace_id="test-workspace",
    )


class TestBackendInitialization:
    """Test backend initialization."""

    def test_init_creates_client(self):
        """Should create client with provided parameters."""
        backend = AnythingLLMBackend(
            api_url="http://example.com",
            api_key="my-key",
            workspace_id="my-workspace",
        )
        assert backend.client.api_url == "http://example.com"
        assert backend.client.api_key == "my-key"
        assert backend.client.workspace_id == "my-workspace"

    def test_name_property(self, backend):
        """Should return correct backend name."""
        assert backend.name == "anythingllm"


class TestIsConfigured:
    """Test configuration checking."""

    def test_is_configured_with_url_and_key(self, backend):
        """Should return True when URL and key are set."""
        assert backend.is_configured() is True

    def test_is_configured_missing_url(self):
        """Should return False when URL is missing."""
        backend = AnythingLLMBackend(api_url="", api_key="test-key")
        assert backend.is_configured() is False

    def test_is_configured_missing_key(self):
        """Should return False when key is missing."""
        backend = AnythingLLMBackend(api_url="http://localhost:3001", api_key="")
        assert backend.is_configured() is False


class TestTestConnection:
    """Test connection testing."""

    def test_connection_success(self, backend):
        """Should return True when client connection succeeds."""
        with patch.object(backend.client, "test_connection", return_value=True):
            result = backend.test_connection()
            assert result is True

    def test_connection_failure(self, backend):
        """Should return False when client connection fails."""
        with patch.object(backend.client, "test_connection", return_value=False):
            result = backend.test_connection()
            assert result is False

    def test_connection_not_configured(self):
        """Should return False when not configured."""
        backend = AnythingLLMBackend(api_url="", api_key="")
        result = backend.test_connection()
        assert result is False

    def test_connection_exception(self, backend):
        """Should return False when exception occurs."""
        with patch.object(
            backend.client, "test_connection", side_effect=Exception("Network error")
        ):
            result = backend.test_connection()
            assert result is False


class TestIngestDocument:
    """Test document ingestion."""

    def test_ingest_success(self, backend, tmp_path):
        """Should ingest document successfully."""
        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Document")

        # Mock client upload
        upload_result = UploadResult(
            success=True,
            document_id="doc123",
            filename="test.md",
            workspace_id="ws1",
        )
        with patch.object(
            backend.client, "upload_document", return_value=upload_result
        ):
            result = backend.ingest_document(
                markdown_path=test_file,
                metadata={"title": "Test Doc", "url": "http://example.com"},
            )

        assert result.success is True
        assert result.document_id == "doc123"
        assert result.collection_id == "ws1"
        assert result.rag_name == "anythingllm"

    def test_ingest_with_collection_id_override(self, backend, tmp_path):
        """Should use collection_id to override default workspace."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        upload_result = UploadResult(success=True, document_id="doc123")
        with patch.object(
            backend.client, "upload_document", return_value=upload_result
        ) as mock_upload:
            result = backend.ingest_document(
                markdown_path=test_file,
                metadata={},
                collection_id="custom-workspace",
            )

        assert result.success is True
        # Verify collection_id was passed as workspace_ids
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        assert kwargs["workspace_ids"] == ["custom-workspace"]

    def test_ingest_not_configured(self, tmp_path):
        """Should return error when not configured."""
        backend = AnythingLLMBackend(api_url="", api_key="")
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        result = backend.ingest_document(test_file, {})

        assert result.success is False
        assert "not configured" in result.error.lower()

    def test_ingest_file_not_found(self, backend):
        """Should return error when file doesn't exist."""
        result = backend.ingest_document(
            markdown_path=Path("/nonexistent/file.md"),
            metadata={},
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_ingest_upload_failure(self, backend, tmp_path):
        """Should handle upload failures."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        upload_result = UploadResult(
            success=False,
            error="Upload failed",
            filename="test.md",
        )
        with patch.object(
            backend.client, "upload_document", return_value=upload_result
        ):
            result = backend.ingest_document(test_file, {})

        assert result.success is False
        assert "Upload failed" in result.error

    def test_ingest_exception(self, backend, tmp_path):
        """Should handle exceptions during ingestion."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch.object(
            backend.client, "upload_document", side_effect=Exception("Network error")
        ):
            result = backend.ingest_document(test_file, {})

        assert result.success is False
        assert "Network error" in result.error


class TestPrepareMetadata:
    """Test metadata preparation."""

    def test_prepare_core_fields(self, backend):
        """Should include core metadata fields."""
        metadata = {
            "title": "Test Document",
            "url": "http://example.com",
            "organization": "TestOrg",
            "source": "test-scraper",
            "document_type": "article",
        }
        result = backend._prepare_metadata(metadata)

        assert result["title"] == "Test Document"
        assert result["url"] == "http://example.com"
        assert result["organization"] == "TestOrg"
        assert result["source"] == "test-scraper"
        assert result["document_type"] == "article"

    def test_prepare_date_fields(self, backend):
        """Should convert date fields to strings."""
        from datetime import datetime

        metadata = {
            "publication_date": datetime(2024, 1, 15),
            "scraped_at": "2024-02-01",
        }
        result = backend._prepare_metadata(metadata)

        assert "publication_date" in result
        assert "scraped_at" in result
        assert isinstance(result["publication_date"], str)

    def test_prepare_numeric_fields(self, backend):
        """Should include numeric fields."""
        metadata = {
            "file_size": 1024,
            "page_count": 42,
        }
        result = backend._prepare_metadata(metadata)

        assert result["file_size"] == 1024
        assert result["page_count"] == 42

    def test_prepare_hash_field(self, backend):
        """Should rename hash to file_hash."""
        metadata = {"hash": "abc123"}
        result = backend._prepare_metadata(metadata)

        assert result["file_hash"] == "abc123"

    def test_prepare_extra_metadata(self, backend):
        """Should flatten extra metadata."""
        metadata = {
            "extra": {
                "author": "John Doe",
                "tags": ["energy", "report"],
                "custom_field": "value",
            }
        }
        result = backend._prepare_metadata(metadata)

        assert result["extra_author"] == "John Doe"
        assert "extra_tags" in result  # Should be JSON string
        assert result["extra_custom_field"] == "value"

    def test_prepare_skips_none_values(self, backend):
        """Should skip None values."""
        metadata = {
            "title": "Test",
            "url": None,
            "organization": "",
        }
        result = backend._prepare_metadata(metadata)

        assert "title" in result
        assert "url" not in result
        assert "organization" not in result

    def test_prepare_empty_metadata(self, backend):
        """Should handle empty metadata."""
        result = backend._prepare_metadata({})
        assert isinstance(result, dict)
        assert len(result) == 0
