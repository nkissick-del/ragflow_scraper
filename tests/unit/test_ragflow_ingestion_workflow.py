"""Tests for RAGFlow ingestion workflow."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from app.services.ragflow_ingestion import RAGFlowIngestionWorkflow
from app.services.ragflow_client import UploadResult
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def mock_client():
    """Create mock RAGFlow client."""
    client = Mock()
    client.check_document_exists = Mock(return_value=None)
    client.upload_document = Mock()
    client.wait_for_document_ready = Mock(return_value=True)
    client.set_document_metadata = Mock(return_value=True)
    return client


@pytest.fixture
def workflow(mock_client):
    """Create workflow with mocked client."""
    return RAGFlowIngestionWorkflow(mock_client)


@pytest.fixture
def sample_metadata():
    """Create sample document metadata."""
    return DocumentMetadata(
        url="http://example.com/doc.pdf",
        title="Test Document",
        filename="doc.pdf",
        file_size=1024,
        hash="abc123",
        organization="TestOrg",
    )


class TestCheckExists:
    """Test duplicate checking."""

    def test_check_exists_returns_document_id_if_found(self, workflow, mock_client):
        """Should return document ID when duplicate exists."""
        mock_client.check_document_exists.return_value = "doc_123"

        result = workflow.check_exists("dataset_1", "hash_abc")

        assert result == "doc_123"
        mock_client.check_document_exists.assert_called_once_with("dataset_1", "hash_abc")

    def test_check_exists_returns_none_if_not_found(self, workflow, mock_client):
        """Should return None when no duplicate found."""
        mock_client.check_document_exists.return_value = None

        result = workflow.check_exists("dataset_1", "hash_xyz")

        assert result is None

    def test_check_exists_handles_client_exception(self, workflow, mock_client):
        """Should handle client exceptions gracefully."""
        mock_client.check_document_exists.side_effect = Exception("Network error")

        with pytest.raises(Exception):
            workflow.check_exists("dataset_1", "hash_abc")


class TestUploadAndWait:
    """Test upload with polling."""

    def test_upload_and_wait_success(self, workflow, mock_client):
        """Should upload and wait for document to be ready."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_456", filename="test.pdf"
        )
        mock_client.wait_for_document_ready.return_value = True

        result = workflow.upload_and_wait("dataset_1", filepath, timeout=5.0)

        assert result.success is True
        assert result.document_id == "doc_456"
        mock_client.upload_document.assert_called_once_with("dataset_1", filepath)
        mock_client.wait_for_document_ready.assert_called_once_with(
            "dataset_1", "doc_456", timeout=5.0, poll_interval=0.5
        )

    def test_upload_and_wait_handles_upload_failure(self, workflow, mock_client):
        """Should return failed result if upload fails."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=False, error="Upload failed", filename="test.pdf"
        )

        result = workflow.upload_and_wait("dataset_1", filepath)

        assert result.success is False
        assert result.error == "Upload failed"
        mock_client.wait_for_document_ready.assert_not_called()

    def test_upload_and_wait_handles_timeout(self, workflow, mock_client):
        """Should handle timeout when waiting for parsing."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_789", filename="test.pdf"
        )
        mock_client.wait_for_document_ready.return_value = False

        result = workflow.upload_and_wait("dataset_1", filepath, timeout=1.0)

        assert result.success is True  # Upload succeeded
        assert result.document_id == "doc_789"
        # Timeout logged but result still returned

    def test_upload_and_wait_uses_custom_poll_interval(self, workflow, mock_client):
        """Should use custom poll interval."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_999", filename="test.pdf"
        )

        workflow.upload_and_wait("dataset_1", filepath, timeout=10.0, poll_interval=1.0)

        mock_client.wait_for_document_ready.assert_called_once_with(
            "dataset_1", "doc_999", timeout=10.0, poll_interval=1.0
        )


class TestPushMetadata:
    """Test metadata pushing."""

    def test_push_metadata_success(self, workflow, mock_client):
        """Should push metadata and return True."""
        metadata = {"key": "value"}
        mock_client.set_document_metadata.return_value = True

        result = workflow.push_metadata("dataset_1", "doc_123", metadata)

        assert result is True
        mock_client.set_document_metadata.assert_called_once_with(
            "dataset_1", "doc_123", metadata
        )

    def test_push_metadata_failure(self, workflow, mock_client):
        """Should return False when metadata push fails."""
        metadata = {"key": "value"}
        mock_client.set_document_metadata.return_value = False

        result = workflow.push_metadata("dataset_1", "doc_123", metadata)

        assert result is False

    def test_push_metadata_handles_exception(self, workflow, mock_client):
        """Should propagate exceptions from client."""
        metadata = {"key": "value"}
        mock_client.set_document_metadata.side_effect = Exception("API error")

        with pytest.raises(Exception):
            workflow.push_metadata("dataset_1", "doc_123", metadata)


class TestIngestWithMetadata:
    """Test full ingestion workflow."""

    def test_ingest_single_document_success(self, workflow, mock_client, sample_metadata):
        """Should ingest single document with metadata."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_111", filename="test.pdf"
        )

        docs = [{"filepath": filepath, "metadata": sample_metadata}]
        results = workflow.ingest_with_metadata("dataset_1", docs)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc_111"
        assert results[0].metadata_pushed is True

    def test_ingest_skips_duplicates(self, workflow, mock_client, sample_metadata):
        """Should skip documents that already exist."""
        filepath = Path("/tmp/test.pdf")
        mock_client.check_document_exists.return_value = "doc_existing"

        docs = [{"filepath": filepath, "metadata": sample_metadata}]
        results = workflow.ingest_with_metadata("dataset_1", docs, check_duplicates=True)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc_existing"
        assert results[0].skipped_duplicate is True
        mock_client.upload_document.assert_not_called()

    def test_ingest_without_duplicate_check(self, workflow, mock_client, sample_metadata):
        """Should upload even if duplicate exists when check disabled."""
        filepath = Path("/tmp/test.pdf")
        mock_client.check_document_exists.return_value = "doc_existing"
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_new", filename="test.pdf"
        )

        docs = [{"filepath": filepath, "metadata": sample_metadata}]
        results = workflow.ingest_with_metadata("dataset_1", docs, check_duplicates=False)

        assert len(results) == 1
        assert results[0].document_id == "doc_new"
        mock_client.upload_document.assert_called_once()

    def test_ingest_without_metadata(self, workflow, mock_client):
        """Should handle documents without metadata."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_222", filename="test.pdf"
        )

        docs = [{"filepath": filepath}]
        results = workflow.ingest_with_metadata("dataset_1", docs)

        assert len(results) == 1
        assert results[0].success is True
        mock_client.set_document_metadata.assert_not_called()

    def test_ingest_handles_upload_failure(self, workflow, mock_client, sample_metadata):
        """Should continue with other documents when one fails."""
        filepath1 = Path("/tmp/test1.pdf")
        filepath2 = Path("/tmp/test2.pdf")

        def upload_side_effect(dataset_id, filepath):
            if filepath == filepath1:
                return UploadResult(success=False, error="Network error", filename="test1.pdf")
            return UploadResult(success=True, document_id="doc_333", filename="test2.pdf")

        mock_client.upload_document.side_effect = upload_side_effect

        docs = [
            {"filepath": filepath1, "metadata": sample_metadata},
            {"filepath": filepath2, "metadata": sample_metadata},
        ]
        results = workflow.ingest_with_metadata("dataset_1", docs, check_duplicates=False)

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True
        assert results[1].document_id == "doc_333"

    def test_ingest_handles_metadata_push_failure(self, workflow, mock_client, sample_metadata):
        """Should mark metadata_pushed=False when push fails."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_444", filename="test.pdf"
        )
        mock_client.set_document_metadata.return_value = False

        docs = [{"filepath": filepath, "metadata": sample_metadata}]
        results = workflow.ingest_with_metadata("dataset_1", docs)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].metadata_pushed is False

    def test_ingest_batch_with_mixed_results(self, workflow, mock_client, sample_metadata):
        """Should handle batch with duplicates, successes, and failures."""
        filepath1 = Path("/tmp/dup.pdf")
        filepath2 = Path("/tmp/new.pdf")
        filepath3 = Path("/tmp/fail.pdf")

        def check_exists_side_effect(dataset_id, file_hash):
            if file_hash == "hash_dup":
                return "doc_existing"
            return None

        def upload_side_effect(dataset_id, filepath):
            if filepath == filepath3:
                return UploadResult(success=False, error="Upload failed", filename="fail.pdf")
            return UploadResult(success=True, document_id="doc_new", filename=filepath.name)

        mock_client.check_document_exists.side_effect = check_exists_side_effect
        mock_client.upload_document.side_effect = upload_side_effect

        metadata1 = DocumentMetadata(
            url="http://example.com/dup.pdf",
            title="Dup",
            filename="dup.pdf",
            hash="hash_dup",
        )
        metadata2 = DocumentMetadata(
            url="http://example.com/new.pdf",
            title="New",
            filename="new.pdf",
            hash="hash_new",
        )
        metadata3 = DocumentMetadata(
            url="http://example.com/fail.pdf",
            title="Fail",
            filename="fail.pdf",
            hash="hash_fail",
        )

        docs = [
            {"filepath": filepath1, "metadata": metadata1},
            {"filepath": filepath2, "metadata": metadata2},
            {"filepath": filepath3, "metadata": metadata3},
        ]
        results = workflow.ingest_with_metadata("dataset_1", docs, check_duplicates=True)

        assert len(results) == 3
        assert results[0].skipped_duplicate is True
        assert results[1].success is True
        assert results[1].metadata_pushed is True
        assert results[2].success is False

    def test_ingest_uses_custom_timeout(self, workflow, mock_client, sample_metadata):
        """Should pass custom timeout to wait_for_document_ready."""
        filepath = Path("/tmp/test.pdf")
        mock_client.upload_document.return_value = UploadResult(
            success=True, document_id="doc_555", filename="test.pdf"
        )

        docs = [{"filepath": filepath, "metadata": sample_metadata}]
        workflow.ingest_with_metadata("dataset_1", docs, wait_timeout=20.0, poll_interval=2.0)

        mock_client.wait_for_document_ready.assert_called_once_with(
            "dataset_1", "doc_555", timeout=20.0, poll_interval=2.0
        )
