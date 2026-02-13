"""Tests for AnythingLLM client."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

from app.services.anythingllm_client import AnythingLLMClient


@pytest.fixture
def client():
    """Create test client."""
    return AnythingLLMClient(
        api_url="http://localhost:3001",
        api_key="test-key",
        workspace_id="test-workspace",
    )


class TestClientInitialization:
    """Test client initialization."""

    def test_init_with_explicit_params(self):
        """Should initialize with provided parameters."""
        client = AnythingLLMClient(
            api_url="http://example.com",
            api_key="my-key",
            workspace_id="my-workspace",
        )
        assert client.api_url == "http://example.com"
        assert client.api_key == "my-key"
        assert client.workspace_id == "my-workspace"

    def test_init_strips_trailing_slash(self):
        """Should strip trailing slash from API URL."""
        client = AnythingLLMClient(api_url="http://example.com/")
        assert client.api_url == "http://example.com"

    @patch("app.services.anythingllm_client.Config")
    def test_init_with_config_defaults(self, mock_config):
        """Should use Config defaults when params not provided."""
        mock_config.ANYTHINGLLM_API_URL = "http://config-url.com"
        mock_config.ANYTHINGLLM_API_KEY = "config-key"
        mock_config.ANYTHINGLLM_WORKSPACE_ID = "config-workspace"

        client = AnythingLLMClient()
        assert client.api_url == "http://config-url.com"
        assert client.api_key == "config-key"
        assert client.workspace_id == "config-workspace"


class TestTestConnection:
    """Test connection testing."""

    def test_connection_success(self, client):
        """Should return True when connection succeeds."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.test_connection()

        assert result is True
        mock_session.request.assert_called_once()
        args, kwargs = mock_session.request.call_args
        assert args[0] == "GET"
        assert "/api/v1/workspaces" in args[1]
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_connection_failure(self, client):
        """Should return False when connection fails."""
        mock_session = Mock()
        mock_session.request.side_effect = requests.RequestException("Network error")
        client.session = mock_session

        result = client.test_connection()

        assert result is False

    def test_connection_http_error(self, client):
        """Should return False when HTTP error occurs."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.test_connection()

        assert result is False


class TestListWorkspaces:
    """Test workspace listing."""

    def test_list_workspaces_dict_response(self, client):
        """Should handle dict response with workspaces key."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workspaces": [
                {"id": "ws1", "name": "Workspace 1"},
                {"id": "ws2", "name": "Workspace 2"},
            ]
        }
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.list_workspaces()

        assert len(result) == 2
        assert result[0]["id"] == "ws1"

    def test_list_workspaces_list_response(self, client):
        """Should handle list response directly."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "ws1", "name": "Workspace 1"},
        ]
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.list_workspaces()

        assert len(result) == 1
        assert result[0]["id"] == "ws1"

    def test_list_workspaces_error(self, client):
        """Should return empty list on error."""
        mock_session = Mock()
        mock_session.request.side_effect = Exception("API error")
        client.session = mock_session

        result = client.list_workspaces()

        assert result == []


class TestUploadDocument:
    """Test document upload."""

    def test_upload_success(self, client, tmp_path):
        """Should upload document successfully."""
        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Document")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "doc123",
            "workspace_id": "ws1",
        }
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is True
        assert result.document_id == "doc123"
        assert result.workspace_id == "ws1"
        assert result.filename == "test.md"

    def test_upload_with_workspace_ids(self, client, tmp_path):
        """Should include workspace IDs in request."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "doc123"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(
            test_file,
            workspace_ids=["ws1", "ws2"],
        )

        assert result.success is True
        # Verify workspace IDs were included in request
        args, kwargs = mock_session.request.call_args
        assert "data" in kwargs
        assert kwargs["data"]["addToWorkspaces"] == "ws1,ws2"

    def test_upload_with_metadata(self, client, tmp_path):
        """Should include metadata in request."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "doc123"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        metadata = {"title": "Test Doc", "author": "Test Author"}
        result = client.upload_document(test_file, metadata=metadata)

        assert result.success is True
        # Verify metadata was included and matches expected payload
        args, kwargs = mock_session.request.call_args
        assert "data" in kwargs
        assert "metadata" in kwargs["data"]
        # Parse JSON-serialized metadata and verify exact equality
        actual_metadata = json.loads(kwargs["data"]["metadata"])
        assert actual_metadata == metadata

    def test_upload_file_not_found(self, client):
        """Should return error when file doesn't exist."""
        result = client.upload_document(Path("/nonexistent/file.md"))

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_upload_http_error(self, client, tmp_path):
        """Should handle HTTP errors."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is False
        assert "500" in result.error

    def test_upload_network_error(self, client, tmp_path):
        """Should handle network errors."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_session.request.side_effect = requests.RequestException("Network error")
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is False
        assert "Network error" in result.error


class TestRetryLogic:
    """Test retry logic."""

    @patch("app.services.anythingllm_client.time.sleep")
    def test_retries_on_500_error(self, mock_sleep, client):
        """Should retry on 500 errors."""
        mock_session = Mock()
        mock_response_fail = Mock()
        mock_response_fail.ok = False
        mock_response_fail.status_code = 500

        mock_response_success = Mock()
        mock_response_success.ok = True
        mock_response_success.status_code = 200

        mock_session.request.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]
        client.session = mock_session

        result = client.test_connection()

        assert result is True
        assert mock_session.request.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("app.services.anythingllm_client.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep, client):
        """Should fail after max retries using public API."""
        mock_session = Mock()
        mock_session.request.side_effect = requests.RequestException("Network error")
        client.session = mock_session
        client.max_retries = 3

        # Use public API which exercises retry logic internally
        result = client.test_connection()

        assert result is False
        assert mock_session.request.call_count == 3
        # Should sleep between retries (max_retries - 1 attempts)
        assert mock_sleep.call_count == client.max_retries - 1


# ── Additional coverage tests ─────────────────────────────────────────


class TestCloseCleanup:
    """Test close() and context manager cleanup."""

    def test_close_sets_closed_flag(self, client):
        """Should set _closed flag and nullify session."""
        assert client._closed is False
        client.close()
        assert client._closed is True
        assert client.session is None

    def test_double_close_is_noop(self, client):
        """Should handle double close gracefully."""
        client.close()
        client.close()  # Should not raise
        assert client._closed is True

    def test_closed_client_raises_on_request(self, client):
        """Should raise RuntimeError when making requests after close."""
        client.close()
        with pytest.raises(RuntimeError, match="closed"):
            client._request("GET", "/api/v1/workspaces")

    def test_closed_client_raises_on_test_connection(self, client):
        """Should raise RuntimeError when test_connection after close."""
        client.close()
        with pytest.raises(RuntimeError, match="closed"):
            client.test_connection()

    def test_closed_client_raises_on_list_workspaces(self, client):
        """Should raise RuntimeError when list_workspaces after close."""
        client.close()
        with pytest.raises(RuntimeError, match="closed"):
            client.list_workspaces()

    def test_context_manager_closes_on_exit(self):
        """Context manager should close client on exit."""
        with AnythingLLMClient(
            api_url="http://localhost:3001",
            api_key="test-key",
        ) as c:
            assert c._closed is False

        assert c._closed is True


class TestUploadDocumentEdgeCases:
    """Test upload_document edge cases."""

    def test_upload_response_not_dict(self, client, tmp_path):
        """Should handle non-dict response gracefully."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = "just a string"
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is True
        assert result.filename == "test.md"

    def test_upload_with_documents_array(self, client, tmp_path):
        """Should extract doc from documents array."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documents": [{"id": "doc-abc", "workspace_id": "ws1"}]
        }
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is True
        assert result.document_id == "doc-abc"

    def test_upload_with_non_dict_document_in_array(self, client, tmp_path):
        """Should handle non-dict items in documents array."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documents": ["not-a-dict"]
        }
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.upload_document(test_file)

        assert result.success is True
        assert result.filename == "test.md"

    def test_upload_uses_default_workspace_when_no_ids(self, client, tmp_path):
        """Should use default workspace_id when no workspace_ids provided."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "doc123"}
        mock_session.request.return_value = mock_response
        client.session = mock_session

        client.upload_document(test_file)

        args, kwargs = mock_session.request.call_args
        assert kwargs["data"]["addToWorkspaces"] == "test-workspace"


class TestListDocumentsAnythingLLM:
    """Test list_documents endpoint."""

    def test_list_documents_dict_with_localfiles(self, client):
        """Should flatten localFiles structure."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "localFiles": {
                "items": [
                    {
                        "name": "folder1",
                        "items": [
                            {"name": "doc1.md", "id": "d1"},
                            {"name": "doc2.md", "id": "d2"},
                        ],
                    }
                ]
            }
        }
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.list_documents()

        assert len(result) == 2
        assert result[0]["name"] == "doc1.md"

    def test_list_documents_list_response(self, client):
        """Should handle list response directly."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "doc1.md"}]
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.list_documents()

        assert len(result) == 1

    def test_list_documents_failure(self, client):
        """Should return empty list on failure."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_session.request.return_value = mock_response
        client.session = mock_session

        result = client.list_documents()

        assert result == []

    def test_list_documents_exception(self, client):
        """Should return empty list on exception."""
        mock_session = Mock()
        mock_session.request.side_effect = Exception("Network")
        client.session = mock_session

        result = client.list_documents()

        assert result == []


class TestSanitizeResponseText:
    """Test _sanitize_response_text."""

    def test_empty_text(self, client):
        """Should return empty string for empty input."""
        assert client._sanitize_response_text("") == ""

    def test_truncation(self, client):
        """Should truncate long text."""
        long_text = "a" * 600
        result = client._sanitize_response_text(long_text, max_len=100)
        assert len(result) == 103  # 100 + "..."
        assert result.endswith("...")

    def test_strips_control_characters(self, client):
        """Should remove control characters."""
        text = "hello\x00world\x01test"
        result = client._sanitize_response_text(text)
        assert "\x00" not in result
        assert "\x01" not in result


class TestApiUrlStripping:
    """Test /api suffix stripping."""

    def test_strips_api_suffix(self):
        """Should strip /api from URL to avoid /api/api paths."""
        client = AnythingLLMClient(api_url="http://localhost:3001/api")
        assert client.api_url == "http://localhost:3001"

    def test_max_attempts_minimum_one(self):
        """Should enforce minimum of 1 attempt."""
        client = AnythingLLMClient(
            api_url="http://localhost:3001",
            api_key="key",
            max_attempts=0,
        )
        assert client.max_attempts == 1
