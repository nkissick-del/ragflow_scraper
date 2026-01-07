"""Integration tests for RAGFlow ingestion workflow.

Tests the complete document ingestion flow with mocked RAGFlowClient to verify:
- Deduplication detection
- Upload and polling workflow
- Metadata push after parsing
- Error handling and retries
- Batch processing with partial failures
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import pytest

from app.services.ragflow_ingestion import RAGFlowIngestionWorkflow
from app.services.ragflow_client import UploadResult


@pytest.fixture
def mock_client():
    """Create a mocked RAGFlowClient for testing workflow."""
    client = MagicMock()
    client.upload_document.return_value = ("doc-123", 2048)
    client.check_document_exists.return_value = None
    client.wait_for_document_ready.return_value = True
    client.set_document_metadata.return_value = True
    return client


@pytest.fixture
def workflow(mock_client):
    """Create RAGFlowIngestionWorkflow with mocked client."""
    return RAGFlowIngestionWorkflow(mock_client)


@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary test file."""
    test_file = tmp_path / "test_document.pdf"
    test_file.write_bytes(b"fake pdf content")
    return test_file


@pytest.fixture
def metadata():
    """Create sample document metadata."""
    return {
        "organization": "test_scraper",
        "source_url": "https://example.com/doc.pdf",
        "scraped_at": "2026-01-07T00:00:00",
        "document_type": "report",
        "title": "Test Document",
        "publication_date": "2026-01-07",
        "file_hash": "abc123"
    }


class TestDeduplication:
    """Test document deduplication logic."""
    
    def test_check_exists_returns_none_when_not_found(self, workflow, mock_client):
        """Test check_exists returns None when document doesn't exist."""
        mock_client.check_document_exists.return_value = None
        
        result = workflow.check_exists("dataset-1", "hash123")
        
        assert result is None
        mock_client.check_document_exists.assert_called_once_with("dataset-1", "hash123")
    
    def test_check_exists_returns_document_id_when_found(self, workflow, mock_client):
        """Test check_exists returns document ID when document exists."""
        mock_client.check_document_exists.return_value = "doc-existing"
        
        result = workflow.check_exists("dataset-1", "hash123")
        
        assert result == "doc-existing"
        mock_client.check_document_exists.assert_called_once()
    
    def test_check_exists_handles_api_error(self, workflow, mock_client):
        """Test check_exists handles API errors gracefully."""
        mock_client.check_document_exists.side_effect = Exception("API error")
        
        with pytest.raises(Exception):
            workflow.check_exists("dataset-1", "hash123")


class TestUploadAndWait:
    """Test document upload and polling workflow."""
    
    def test_upload_and_wait_success(self, workflow, mock_client, temp_file):
        """Test successful upload and polling workflow."""
        mock_client.upload_document.return_value = ("doc-123", 2048)
        mock_client.wait_for_document_ready.return_value = True
        
        result = workflow.upload_and_wait("dataset-1", temp_file)
        
        assert result.success is True
        assert result.document_id == "doc-123"
        assert result.file_path == temp_file
        mock_client.upload_document.assert_called_once_with("dataset-1", temp_file)
        mock_client.wait_for_document_ready.assert_called_once_with("dataset-1", "doc-123", timeout=10.0, poll_interval=0.5)
    
    def test_upload_and_wait_with_custom_timeout(self, workflow, mock_client, temp_file):
        """Test upload with custom timeout value."""
        mock_client.upload_document.return_value = ("doc-456", 4096)
        mock_client.wait_for_document_ready.return_value = True
        
        result = workflow.upload_and_wait("dataset-1", temp_file, timeout=30.0)
        
        assert result.success is True
        mock_client.wait_for_document_ready.assert_called_once_with("dataset-1", "doc-456", timeout=30.0, poll_interval=0.5)
    
    def test_upload_fails_returns_error_result(self, workflow, mock_client, temp_file):
        """Test upload failure returns UploadResult with error."""
        mock_client.upload_document.side_effect = Exception("Upload failed")
        
        result = workflow.upload_and_wait("dataset-1", temp_file)
        
        assert result.success is False
        assert result.error is not None
        assert "Upload failed" in result.error
        mock_client.wait_for_document_ready.assert_not_called()
    
    def test_polling_timeout_returns_error_result(self, workflow, mock_client, temp_file):
        """Test polling timeout returns UploadResult with timeout error."""
        mock_client.upload_document.return_value = ("doc-789", 1024)
        mock_client.wait_for_document_ready.side_effect = Exception("Parsing timeout")
        
        result = workflow.upload_and_wait("dataset-1", temp_file)
        
        assert result.success is False
        assert result.document_id == "doc-789"
        assert "Parsing timeout" in result.error
    
    def test_nonexistent_file_returns_error(self, workflow, mock_client):
        """Test attempting to upload nonexistent file returns error."""
        fake_path = Path("/nonexistent/file.pdf")
        mock_client.upload_document.side_effect = FileNotFoundError(f"File not found: {fake_path}")
        
        result = workflow.upload_and_wait("dataset-1", fake_path)
        
        assert result.success is False
        assert result.error is not None
        assert "File not found" in result.error
        mock_client.upload_document.assert_called_once_with("dataset-1", fake_path)


class TestMetadataPush:
    """Test metadata pushing after document ready."""
    
    def test_push_metadata_success(self, workflow, mock_client, metadata):
        """Test successful metadata push."""
        mock_client.set_document_metadata.return_value = True
        
        result = workflow.push_metadata("dataset-1", "doc-123", metadata)
        
        assert result is True
        mock_client.set_document_metadata.assert_called_once_with("dataset-1", "doc-123", metadata)
    
    def test_push_metadata_failure(self, workflow, mock_client, metadata):
        """Test metadata push failure."""
        mock_client.set_document_metadata.return_value = False
        
        result = workflow.push_metadata("dataset-1", "doc-123", metadata)
        
        assert result is False
    
    def test_push_metadata_handles_api_error(self, workflow, mock_client, metadata):
        """Test metadata push handles API errors."""
        mock_client.set_document_metadata.side_effect = Exception("Metadata API error")
        
        with pytest.raises(Exception):
            workflow.push_metadata("dataset-1", "doc-123", metadata)


class TestFullIngestion:
    """Test complete ingestion workflow with multiple files."""
    
    def test_ingest_single_file_success(self, workflow, mock_client, temp_file, metadata):
        """Test successful ingestion of single file."""
        mock_client.check_document_exists.return_value = None
        mock_client.upload_document.return_value = ("doc-123", 2048)
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = True
        
        files = [(temp_file, metadata)]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc-123"
        assert results[0].skipped is False
        mock_client.upload_document.assert_called_once()
        mock_client.set_document_metadata.assert_called_once()
    
    def test_ingest_skips_duplicate_when_enabled(self, workflow, mock_client, temp_file, metadata):
        """Test ingestion skips duplicate documents when skip_duplicates=True."""
        mock_client.check_document_exists.return_value = "doc-existing"
        
        files = [(temp_file, metadata)]
        results = workflow.ingest_with_metadata("dataset-1", files, skip_duplicates=True)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc-existing"
        assert results[0].skipped is True
        mock_client.upload_document.assert_not_called()
        mock_client.set_document_metadata.assert_not_called()
    
    def test_ingest_uploads_duplicate_when_disabled(self, workflow, mock_client, temp_file, metadata):
        """Test ingestion uploads duplicate when skip_duplicates=False."""
        mock_client.check_document_exists.return_value = "doc-existing"
        mock_client.upload_document.return_value = ("doc-new", 2048)
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = True
        
        files = [(temp_file, metadata)]
        results = workflow.ingest_with_metadata("dataset-1", files, skip_duplicates=False)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc-new"
        assert results[0].skipped is False
        mock_client.upload_document.assert_called_once()
    
    def test_ingest_multiple_files_success(self, workflow, mock_client, tmp_path, metadata):
        """Test successful batch ingestion of multiple files."""
        # Create multiple test files
        file1 = tmp_path / "doc1.pdf"
        file2 = tmp_path / "doc2.pdf"
        file3 = tmp_path / "doc3.pdf"
        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")
        file3.write_bytes(b"content3")
        
        mock_client.check_document_exists.return_value = None
        mock_client.upload_document.side_effect = [
            ("doc-1", 1024),
            ("doc-2", 2048),
            ("doc-3", 3072)
        ]
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = True
        
        files = [
            (file1, metadata),
            (file2, metadata),
            (file3, metadata)
        ]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.document_id for r in results] == ["doc-1", "doc-2", "doc-3"]
        assert mock_client.upload_document.call_count == 3
        assert mock_client.set_document_metadata.call_count == 3
    
    def test_ingest_handles_partial_failures(self, workflow, mock_client, tmp_path, metadata):
        """Test batch ingestion continues after individual file failures."""
        file1 = tmp_path / "doc1.pdf"
        file2 = tmp_path / "doc2.pdf"
        file3 = tmp_path / "doc3.pdf"
        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")
        file3.write_bytes(b"content3")
        
        mock_client.check_document_exists.return_value = None
        # Second upload fails, others succeed
        mock_client.upload_document.side_effect = [
            ("doc-1", 1024),
            Exception("Upload failed"),
            ("doc-3", 3072)
        ]
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = True
        
        files = [
            (file1, metadata),
            (file2, metadata),
            (file3, metadata)
        ]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert "Upload failed" in results[1].error
        assert results[2].success is True
    
    def test_ingest_metadata_push_failures_dont_fail_upload(self, workflow, mock_client, temp_file, metadata):
        """Test that metadata push failures don't mark upload as failed."""
        mock_client.check_document_exists.return_value = None
        mock_client.upload_document.return_value = ("doc-123", 2048)
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = False  # Metadata push fails
        
        files = [(temp_file, metadata)]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        # Upload should still be marked as success even if metadata fails
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].document_id == "doc-123"
    
    def test_ingest_empty_list_returns_empty_results(self, workflow, mock_client):
        """Test ingesting empty file list returns empty results."""
        files = []
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 0
        mock_client.upload_document.assert_not_called()
    
    def test_ingest_mixed_duplicates_and_new_files(self, workflow, mock_client, tmp_path, metadata):
        """Test batch with mix of duplicates and new files."""
        file1 = tmp_path / "doc1.pdf"
        file2 = tmp_path / "doc2.pdf"  # Will be duplicate
        file3 = tmp_path / "doc3.pdf"
        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")
        file3.write_bytes(b"content3")
        
        # File 2 is duplicate, others are new
        mock_client.check_document_exists.side_effect = [None, "doc-existing", None]
        mock_client.upload_document.side_effect = [
            ("doc-1", 1024),
            ("doc-3", 3072)
        ]
        mock_client.wait_for_document_ready.return_value = True
        mock_client.set_document_metadata.return_value = True
        
        files = [
            (file1, metadata),
            (file2, metadata),
            (file3, metadata)
        ]
        results = workflow.ingest_with_metadata("dataset-1", files, skip_duplicates=True)
        
        assert len(results) == 3
        assert results[0].success is True
        assert results[0].skipped is False
        assert results[1].success is True
        assert results[1].skipped is True
        assert results[1].document_id == "doc-existing"
        assert results[2].success is True
        assert results[2].skipped is False
        # Should only upload 2 files (skipping the duplicate)
        assert mock_client.upload_document.call_count == 2


class TestErrorRecovery:
    """Test error handling and recovery scenarios."""
    
    def test_workflow_handles_network_errors(self, workflow, mock_client, temp_file, metadata):
        """Test workflow handles transient network errors."""
        mock_client.check_document_exists.side_effect = Exception("Network error")
        
        files = [(temp_file, metadata)]
        
        with pytest.raises(Exception):
            workflow.ingest_with_metadata("dataset-1", files)
    
    def test_workflow_captures_errors_in_results(self, workflow, mock_client, temp_file, metadata):
        """Test workflow captures errors in result objects."""
        mock_client.upload_document.side_effect = Exception("Upload failed")
        
        files = [(temp_file, metadata)]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error is not None
    
    def test_workflow_continues_after_single_timeout(self, workflow, mock_client, tmp_path, metadata):
        """Test workflow continues processing after single file timeout."""
        file1 = tmp_path / "doc1.pdf"
        file2 = tmp_path / "doc2.pdf"
        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")
        
        mock_client.check_document_exists.return_value = None
        mock_client.upload_document.side_effect = [
            ("doc-1", 1024),
            ("doc-2", 2048)
        ]
        # First file times out, second succeeds
        mock_client.wait_for_document_ready.side_effect = [
            Exception("Timeout"),
            True
        ]
        mock_client.set_document_metadata.return_value = True
        
        files = [
            (file1, metadata),
            (file2, metadata)
        ]
        results = workflow.ingest_with_metadata("dataset-1", files)
        
        assert len(results) == 2
        assert results[0].success is False
        assert "Timeout" in results[0].error
        assert results[1].success is True
