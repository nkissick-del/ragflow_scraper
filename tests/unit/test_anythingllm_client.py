"""Tests for AnythingLLM client."""

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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_connection_success(self, mock_session_cls, client):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_connection_failure(self, mock_session_cls, client):
        """Should return False when connection fails."""
        mock_session = Mock()
        mock_session.request.side_effect = requests.RequestException("Network error")
        client.session = mock_session

        result = client.test_connection()

        assert result is False

    @patch("app.services.anythingllm_client.requests.Session")
    def test_connection_http_error(self, mock_session_cls, client):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_list_workspaces_dict_response(self, mock_session_cls, client):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_list_workspaces_list_response(self, mock_session_cls, client):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_list_workspaces_error(self, mock_session_cls, client):
        """Should return empty list on error."""
        mock_session = Mock()
        mock_session.request.side_effect = Exception("API error")
        client.session = mock_session

        result = client.list_workspaces()

        assert result == []


class TestUploadDocument:
    """Test document upload."""

    @patch("app.services.anythingllm_client.requests.Session")
    def test_upload_success(self, mock_session_cls, client, tmp_path):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_upload_with_workspace_ids(self, mock_session_cls, client, tmp_path):
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
        assert kwargs["data"]["add_to_workspaces"] == "ws1,ws2"

    @patch("app.services.anythingllm_client.requests.Session")
    def test_upload_with_metadata(self, mock_session_cls, client, tmp_path):
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
        # Verify metadata was included
        args, kwargs = mock_session.request.call_args
        assert "data" in kwargs
        assert "metadata" in kwargs["data"]

    def test_upload_file_not_found(self, client):
        """Should return error when file doesn't exist."""
        result = client.upload_document(Path("/nonexistent/file.md"))

        assert result.success is False
        assert "not found" in result.error.lower()

    @patch("app.services.anythingllm_client.requests.Session")
    def test_upload_http_error(self, mock_session_cls, client, tmp_path):
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

    @patch("app.services.anythingllm_client.requests.Session")
    def test_upload_network_error(self, mock_session_cls, client, tmp_path):
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

    @patch("app.services.anythingllm_client.requests.Session")
    @patch("app.services.anythingllm_client.time.sleep")
    def test_retries_on_500_error(self, mock_sleep, mock_session_cls, client):
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

    @patch("app.services.anythingllm_client.requests.Session")
    @patch("app.services.anythingllm_client.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep, mock_session_cls, client):
        """Should fail after max retries."""
        mock_session = Mock()
        mock_session.request.side_effect = requests.RequestException("Network error")
        client.session = mock_session
        client.max_retries = 3

        with pytest.raises(requests.RequestException):
            client._request("GET", "/api/test")

        assert mock_session.request.call_count == 3
