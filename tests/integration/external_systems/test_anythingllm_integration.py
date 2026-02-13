"""Integration tests for AnythingLLM backend."""

import pytest
import requests
from unittest.mock import patch
import responses
from requests_toolbelt.multipart import decoder as multipart_decoder

from app.backends.rag.anythingllm_adapter import AnythingLLMBackend
from app.services.anythingllm_client import AnythingLLMClient


@pytest.fixture
def backend():
    """Create test backend."""
    return AnythingLLMBackend(
        api_url="http://localhost:3001",
        api_key="test-api-key",
        workspace_id="test-workspace-123",
    )


@pytest.fixture
def client():
    """Create test client."""
    return AnythingLLMClient(
        api_url="http://localhost:3001",
        api_key="test-api-key",
        workspace_id="test-workspace-123",
    )


class TestConnectionIntegration:
    """Test connection with mocked API."""

    @responses.activate
    def test_connection_success(self, client):
        """Should successfully connect to AnythingLLM API."""
        responses.add(
            responses.GET,
            "http://localhost:3001/api/v1/workspaces",
            json={"workspaces": []},
            status=200,
        )

        result = client.test_connection()
        assert result is True

    @responses.activate
    def test_connection_unauthorized(self, client):
        """Should handle unauthorized responses."""
        responses.add(
            responses.GET,
            "http://localhost:3001/api/v1/workspaces",
            json={"error": "Unauthorized"},
            status=401,
        )

        result = client.test_connection()
        assert result is False


class TestWorkspaceManagement:
    """Test workspace listing with mocked API."""

    @responses.activate
    def test_list_workspaces(self, client):
        """Should list workspaces successfully."""
        responses.add(
            responses.GET,
            "http://localhost:3001/api/v1/workspaces",
            json={
                "workspaces": [
                    {"id": "ws1", "name": "Workspace 1"},
                    {"id": "ws2", "name": "Workspace 2"},
                ]
            },
            status=200,
        )

        workspaces = client.list_workspaces()
        assert len(workspaces) == 2
        assert workspaces[0]["id"] == "ws1"
        assert workspaces[1]["name"] == "Workspace 2"


class TestDocumentUpload:
    """Test document upload workflow with mocked API."""

    @responses.activate
    def test_upload_document_success(self, client, tmp_path):
        """Should upload document successfully."""
        # Create test file
        test_file = tmp_path / "test_document.md"
        test_file.write_text("# Test Document\n\nThis is a test.")

        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={
                "id": "doc-123",
                "workspace_id": "test-workspace-123",
                "status": "uploaded",
            },
            status=200,
        )

        result = client.upload_document(
            filepath=test_file,
            folder_name="scraped_documents",
            workspace_ids=["test-workspace-123"],
        )

        assert result.success is True
        assert result.document_id == "doc-123"
        assert result.workspace_id == "test-workspace-123"

    @responses.activate
    def test_upload_with_metadata(self, client, tmp_path):
        """Should upload document with metadata."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={"id": "doc-456"},
            status=200,
        )

        metadata = {
            "title": "Test Document",
            "author": "Test Author",
            "tags": ["test", "integration"],
        }

        result = client.upload_document(
            filepath=test_file,
            metadata=metadata,
        )

        assert result.success is True
        # Verify request included metadata using callback validation
        assert len(responses.calls) == 1
        request = responses.calls[0].request
        # Parse multipart form data to verify metadata field exists
        content_type = request.headers.get("Content-Type", "")
        assert "multipart" in content_type, "Expected multipart form data request"
        parsed = multipart_decoder.MultipartDecoder(request.body, content_type)
        field_names = [
            part.headers.get(b"Content-Disposition", b"").decode()
            for part in parsed.parts
        ]
        assert any("metadata" in name for name in field_names)

    @responses.activate
    def test_upload_server_error(self, client, tmp_path):
        """Should handle server errors during upload."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={"error": "Internal server error"},
            status=500,
        )

        result = client.upload_document(test_file)

        assert result.success is False
        assert "500" in result.error


class TestBackendIntegration:
    """Test full backend integration with mocked API."""

    @responses.activate
    def test_ingest_document_end_to_end(self, backend, tmp_path):
        """Should ingest document through full workflow."""
        # Create test markdown file
        test_file = tmp_path / "article.md"
        test_file.write_text("# Test Article\n\nContent here.")

        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={
                "id": "doc-789",
                "workspace_id": "test-workspace-123",
            },
            status=200,
        )

        # Prepare metadata
        metadata = {
            "title": "Test Article",
            "url": "http://example.com/article",
            "organization": "TestOrg",
            "publication_date": "2024-01-15",
            "file_size": 1024,
            "hash": "abc123",
        }

        result = backend.ingest_document(
            markdown_path=test_file,
            metadata=metadata,
        )

        assert result.success is True
        assert result.document_id == "doc-789"
        assert result.collection_id == "test-workspace-123"
        assert result.rag_name == "anythingllm"

    @responses.activate
    def test_ingest_with_workspace_override(self, backend, tmp_path):
        """Should use collection_id to override default workspace."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={"id": "doc-999"},
            status=200,
        )

        result = backend.ingest_document(
            markdown_path=test_file,
            metadata={},
            collection_id="custom-workspace-456",
        )

        assert result.success is True
        # Verify custom workspace was used
        assert len(responses.calls) == 1
        request = responses.calls[0].request
        assert b"custom-workspace-456" in request.body

    @responses.activate
    def test_ingest_metadata_preparation(self, backend, tmp_path):
        """Should properly prepare metadata for AnythingLLM."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            json={"id": "doc-meta"},
            status=200,
        )

        metadata = {
            "title": "Test",
            "url": "http://example.com",
            "hash": "hash123",
            "page_count": 5,
            "extra": {"custom_field": "value"},
        }

        result = backend.ingest_document(test_file, metadata)

        assert result.success is True
        # Verify metadata was included in request
        request = responses.calls[0].request
        assert b"metadata" in request.body
        # Adapter transforms 'hash' to 'file_hash' for AnythingLLM
        assert b"file_hash" in request.body


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_network_timeout(self, client, tmp_path):
        """Should handle network timeouts gracefully."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        # Simulate timeout by patching session.request
        with patch.object(
            client.session, "request", side_effect=requests.Timeout("Timeout")
        ):
            result = client.upload_document(test_file)
            assert result.success is False
            assert "Timeout" in result.error

    @responses.activate
    def test_invalid_json_response(self, client, tmp_path):
        """Should handle invalid JSON responses."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        responses.add(
            responses.POST,
            "http://localhost:3001/api/v1/document/upload",
            body="Invalid JSON",
            status=200,
        )

        result = client.upload_document(test_file)

        # Invalid JSON should cause upload to fail with parse-related error
        # requests.JSONDecodeError produces messages like "Expecting value: line 1 column 1"
        assert result.success is False
        assert result.error is not None
        assert "Expecting value" in result.error or "JSON" in result.error
