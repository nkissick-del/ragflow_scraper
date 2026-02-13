"""Unit tests for LLM client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm_client import (
    LLMResult,
    OllamaLLMClient,
    APILLMClient,
    create_llm_client,
)


# --------------- OllamaLLMClient ---------------


class TestOllamaLLMClient:
    def test_name(self):
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        assert client.name == "ollama"

    def test_is_configured_true(self):
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        assert client.is_configured() is True

    def test_is_configured_false_no_url(self):
        client = OllamaLLMClient(url="", model="llama3.1:8b")
        assert client.is_configured() is False

    def test_is_configured_false_no_model(self):
        client = OllamaLLMClient(url="http://localhost:11434", model="")
        assert client.is_configured() is False

    @patch("app.services.llm_client.requests.get")
    def test_test_connection_success(self, mock_get):
        mock_get.return_value = MagicMock(ok=True)
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        assert client.test_connection() is True
        mock_get.assert_called_once_with("http://localhost:11434/api/tags", timeout=10)

    @patch("app.services.llm_client.requests.get")
    def test_test_connection_failure(self, mock_get):
        mock_get.return_value = MagicMock(ok=False)
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        assert client.test_connection() is False

    @patch("app.services.llm_client.requests.get")
    def test_test_connection_exception(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        assert client.test_connection() is False

    def test_test_connection_not_configured(self):
        client = OllamaLLMClient(url="", model="")
        assert client.test_connection() is False

    @patch("app.services.llm_client.requests.post")
    def test_chat_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Hello there!"},
            "model": "llama3.1:8b",
            "done_reason": "stop",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        result = client.chat([{"role": "user", "content": "Hi"}])

        assert isinstance(result, LLMResult)
        assert result.content == "Hello there!"
        assert result.model == "llama3.1:8b"
        assert result.finish_reason == "stop"

    @patch("app.services.llm_client.requests.post")
    def test_chat_json_format(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": '{"key": "value"}'},
            "model": "llama3.1:8b",
            "done_reason": "stop",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        client.chat(
            [{"role": "user", "content": "Give JSON"}],
            response_format="json",
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["format"] == "json"

    @patch("app.services.llm_client.requests.post")
    def test_chat_with_max_tokens(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "ok"},
            "model": "llama3.1:8b",
            "done_reason": "stop",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        client.chat(
            [{"role": "user", "content": "test"}],
            max_tokens=500,
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["options"]["num_predict"] == 500

    def test_chat_not_configured(self):
        client = OllamaLLMClient(url="", model="")
        with pytest.raises(ValueError, match="not configured"):
            client.chat([{"role": "user", "content": "Hi"}])

    @patch("app.services.llm_client.requests.post")
    def test_chat_http_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.HTTPError("500 Server Error")
        client = OllamaLLMClient(url="http://localhost:11434", model="llama3.1:8b")
        with pytest.raises(requests.HTTPError):
            client.chat([{"role": "user", "content": "Hi"}])

    def test_url_trailing_slash_stripped(self):
        client = OllamaLLMClient(url="http://localhost:11434/", model="test")
        assert client._url == "http://localhost:11434"


# --------------- APILLMClient ---------------


class TestAPILLMClient:
    def test_name(self):
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        assert client.name == "api"

    def test_is_configured_true(self):
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        assert client.is_configured() is True

    def test_is_configured_false_no_url(self):
        client = APILLMClient(url="", model="gpt-4")
        assert client.is_configured() is False

    def test_is_configured_false_no_model(self):
        client = APILLMClient(url="http://localhost:8080", model="")
        assert client.is_configured() is False

    def test_headers_with_api_key(self):
        client = APILLMClient(
            url="http://localhost:8080", model="gpt-4", api_key="sk-test"
        )
        headers = client._headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_api_key(self):
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        headers = client._headers()
        assert "Authorization" not in headers

    @patch("app.services.llm_client.requests.post")
    def test_test_connection_success(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        assert client.test_connection() is True

    @patch("app.services.llm_client.requests.post")
    def test_test_connection_failure(self, mock_post):
        mock_post.return_value = MagicMock(ok=False)
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        assert client.test_connection() is False

    @patch("app.services.llm_client.requests.post")
    def test_test_connection_exception(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        assert client.test_connection() is False

    def test_test_connection_not_configured(self):
        client = APILLMClient(url="", model="")
        assert client.test_connection() is False

    @patch("app.services.llm_client.requests.post")
    def test_chat_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "model": "gpt-4",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = APILLMClient(
            url="http://localhost:8080", model="gpt-4", api_key="sk-test"
        )
        result = client.chat([{"role": "user", "content": "Hi"}])

        assert isinstance(result, LLMResult)
        assert result.content == "Hello!"
        assert result.model == "gpt-4"
        assert result.finish_reason == "stop"

    @patch("app.services.llm_client.requests.post")
    def test_chat_json_format(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "model": "gpt-4",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        client.chat(
            [{"role": "user", "content": "Give JSON"}],
            response_format="json",
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["response_format"] == {"type": "json_object"}

    @patch("app.services.llm_client.requests.post")
    def test_chat_with_max_tokens(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "gpt-4",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        client.chat([{"role": "user", "content": "test"}], max_tokens=500)

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["max_tokens"] == 500

    @patch("app.services.llm_client.requests.post")
    def test_chat_no_choices(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = APILLMClient(url="http://localhost:8080", model="gpt-4")
        with pytest.raises(ValueError, match="no choices"):
            client.chat([{"role": "user", "content": "Hi"}])

    def test_chat_not_configured(self):
        client = APILLMClient(url="", model="")
        with pytest.raises(ValueError, match="not configured"):
            client.chat([{"role": "user", "content": "Hi"}])


# --------------- Factory ---------------


class TestCreateLLMClient:
    def test_ollama_backend(self):
        client = create_llm_client(backend="ollama", url="http://localhost:11434")
        assert isinstance(client, OllamaLLMClient)

    def test_api_backend(self):
        client = create_llm_client(backend="api", url="http://localhost:8080", model="gpt-4")
        assert isinstance(client, APILLMClient)

    def test_openai_backend(self):
        client = create_llm_client(backend="openai", url="http://localhost:8080", model="gpt-4")
        assert isinstance(client, APILLMClient)

    def test_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            create_llm_client(backend="unknown")

    def test_default_model(self):
        client = create_llm_client(url="http://localhost:11434")
        assert isinstance(client, OllamaLLMClient)
        assert client._model == "llama3.1:8b"

    def test_custom_timeout(self):
        client = create_llm_client(url="http://localhost:11434", timeout=300)
        assert client._timeout == 300
