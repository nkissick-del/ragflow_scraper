"""Tests for Paperless-ngx archive backend adapter."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.backends.archives.paperless_adapter import PaperlessArchiveBackend


@pytest.fixture
def mock_client():
    """Create a mock PaperlessClient."""
    client = MagicMock()
    client.is_configured = True
    client.url = "http://localhost:8000"
    return client


@pytest.fixture
def backend(mock_client):
    """Create test backend with mock client."""
    return PaperlessArchiveBackend(client=mock_client)


@pytest.fixture
def unconfigured_client():
    """Create an unconfigured mock PaperlessClient."""
    client = MagicMock()
    client.is_configured = False
    return client


@pytest.fixture
def unconfigured_backend(unconfigured_client):
    """Create backend that is not configured."""
    return PaperlessArchiveBackend(client=unconfigured_client)


class TestInitialization:
    """Test backend initialization."""

    def test_init_with_injected_client(self, mock_client):
        """Should use injected client."""
        backend = PaperlessArchiveBackend(client=mock_client)
        assert backend.client is mock_client

    def test_init_default_client(self):
        """Should create default PaperlessClient when none provided."""
        with patch("app.backends.archives.paperless_adapter.PaperlessClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            PaperlessArchiveBackend()
            mock_cls.assert_called_once()

    def test_name_property(self, backend):
        """Should return correct archive name."""
        assert backend.name == "paperless"

    def test_pending_metadata_initialized_empty(self, backend):
        """Should initialize with empty pending metadata dict."""
        assert backend._pending_metadata == {}


class TestIsConfigured:
    """Test configuration checking."""

    def test_configured(self, backend):
        """Should return True when client is configured."""
        assert backend.is_configured() is True

    def test_not_configured(self, unconfigured_backend):
        """Should return False when client is not configured."""
        assert unconfigured_backend.is_configured() is False


class TestArchiveDocument:
    """Test document archiving."""

    def test_archive_not_configured(self, unconfigured_backend, tmp_path):
        """Should return error when not configured."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        result = unconfigured_backend.archive_document(test_file, "Test Title")
        assert result.success is False
        assert "not configured" in result.error.lower()
        assert result.archive_name == "paperless"

    def test_archive_file_not_found(self, backend):
        """Should return error when file doesn't exist."""
        result = backend.archive_document(Path("/nonexistent/file.pdf"), "Test Title")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_archive_success(self, backend, mock_client, tmp_path):
        """Should archive document successfully."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-123"

        result = backend.archive_document(test_file, "Test Title")

        assert result.success is True
        assert result.document_id == "task-123"
        assert "task-123" in result.url
        assert result.archive_name == "paperless"

    def test_archive_with_created_date(self, backend, mock_client, tmp_path):
        """Should parse ISO date and pass to client."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-456"

        result = backend.archive_document(
            test_file, "Test", created="2024-01-15T10:30:00+00:00"
        )

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["created"] is not None

    def test_archive_with_z_date_format(self, backend, mock_client, tmp_path):
        """Should normalize Z suffix to +00:00."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-789"

        result = backend.archive_document(
            test_file, "Test", created="2024-01-15T10:30:00Z"
        )

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["created"] is not None

    def test_archive_with_invalid_date(self, backend, mock_client, tmp_path):
        """Should handle invalid date gracefully (pass None for created)."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-000"

        result = backend.archive_document(
            test_file, "Test", created="not-a-date"
        )

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["created"] is None

    def test_archive_with_correspondent_and_tags(self, backend, mock_client, tmp_path):
        """Should pass correspondent and tags to client."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-111"

        result = backend.archive_document(
            test_file,
            "Test",
            correspondent="AEMO",
            tags=["energy", "report"],
        )

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["correspondent"] == "AEMO"
        assert call_kwargs["tags"] == ["energy", "report"]

    def test_archive_with_document_type(self, backend, mock_client, tmp_path):
        """Should pass document_type to client."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-dt"

        result = backend.archive_document(
            test_file,
            "Test",
            document_type="Article",
        )

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["document_type"] == "Article"

    def test_archive_without_document_type(self, backend, mock_client, tmp_path):
        """Should pass None for document_type when not provided."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-nodt"

        result = backend.archive_document(test_file, "Test")

        assert result.success is True
        call_kwargs = mock_client.post_document.call_args[1]
        assert call_kwargs["document_type"] is None

    def test_archive_upload_returns_none(self, backend, mock_client, tmp_path):
        """Should return error when client returns None task_id."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = None

        result = backend.archive_document(test_file, "Test")

        assert result.success is False
        assert "no task_id" in result.error.lower()

    def test_archive_upload_returns_empty(self, backend, mock_client, tmp_path):
        """Should return error when client returns empty string task_id."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = ""

        result = backend.archive_document(test_file, "Test")

        assert result.success is False

    def test_archive_stores_pending_metadata(self, backend, mock_client, tmp_path):
        """Should store metadata keyed by task_id for later custom field application."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-meta"

        metadata = {"author": "Test Author", "category": "Energy"}
        result = backend.archive_document(
            test_file, "Test", metadata=metadata
        )

        assert result.success is True
        assert "task-meta" in backend._pending_metadata
        assert backend._pending_metadata["task-meta"] == metadata

    def test_archive_no_metadata_not_stored(self, backend, mock_client, tmp_path):
        """Should not store pending metadata when None."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")
        mock_client.post_document.return_value = "task-nometa"

        result = backend.archive_document(test_file, "Test")

        assert result.success is True
        assert "task-nometa" not in backend._pending_metadata

    def test_archive_metadata_eviction_at_capacity(self, backend, mock_client, tmp_path):
        """Should evict oldest entry when at 100 capacity."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        # Pre-fill 100 entries
        for i in range(100):
            backend._pending_metadata[f"old-task-{i}"] = {"old": True}

        assert len(backend._pending_metadata) == 100

        mock_client.post_document.return_value = "new-task"
        backend.archive_document(
            test_file, "Test", metadata={"new": True}
        )

        # Should still be at 100 (evicted oldest, added new)
        assert len(backend._pending_metadata) == 100
        assert "old-task-0" not in backend._pending_metadata
        assert "new-task" in backend._pending_metadata


class TestVerifyDocument:
    """Test document verification."""

    def test_verify_not_configured(self, unconfigured_backend):
        """Should return False when not configured."""
        assert unconfigured_backend.verify_document("task-123") is False

    def test_verify_success(self, backend, mock_client):
        """Should return True when document is verified."""
        mock_client.verify_document_exists.return_value = "42"
        assert backend.verify_document("task-123") is True

    def test_verify_failure(self, backend, mock_client):
        """Should return False when verification fails."""
        mock_client.verify_document_exists.return_value = None
        assert backend.verify_document("task-123") is False

    def test_verify_custom_timeout(self, backend, mock_client):
        """Should pass timeout to client."""
        mock_client.verify_document_exists.return_value = "42"
        backend.verify_document("task-123", timeout=120)
        mock_client.verify_document_exists.assert_called_once_with(
            task_id="task-123", timeout=120, poll_interval=2
        )

    def test_verify_applies_custom_fields(self, backend, mock_client):
        """Should apply custom fields after successful verification."""
        backend._pending_metadata["task-fields"] = {"author": "Test", "category": "Energy"}
        mock_client.verify_document_exists.return_value = "55"

        result = backend.verify_document("task-fields")

        assert result is True
        mock_client.set_custom_fields.assert_called_once_with(
            55, {"author": "Test", "category": "Energy"}
        )
        # Metadata should be cleaned up
        assert "task-fields" not in backend._pending_metadata

    def test_verify_custom_fields_failure_nonfatal(self, backend, mock_client):
        """Should return True even if custom fields PATCH fails."""
        backend._pending_metadata["task-nonfatal"] = {"author": "Test"}
        mock_client.verify_document_exists.return_value = "66"
        mock_client.set_custom_fields.side_effect = Exception("PATCH failed")

        result = backend.verify_document("task-nonfatal")

        assert result is True  # Non-fatal
        # Metadata still cleaned up
        assert "task-nonfatal" not in backend._pending_metadata

    def test_verify_no_pending_metadata(self, backend, mock_client):
        """Should not call set_custom_fields when no pending metadata."""
        mock_client.verify_document_exists.return_value = "77"
        backend.verify_document("task-nopending")
        mock_client.set_custom_fields.assert_not_called()

    def test_verify_failure_cleans_up_metadata(self, backend, mock_client):
        """Should clean up pending metadata even on verification failure."""
        backend._pending_metadata["task-cleanup"] = {"author": "Test"}
        mock_client.verify_document_exists.return_value = None

        result = backend.verify_document("task-cleanup")

        assert result is False
        assert "task-cleanup" not in backend._pending_metadata
        mock_client.set_custom_fields.assert_not_called()
