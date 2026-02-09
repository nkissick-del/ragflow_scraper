"""Tests for EmbeddingClient implementations."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.embedding_client import (
    EmbeddingResult,
    OllamaEmbeddingClient,
    APIEmbeddingClient,
    create_embedding_client,
)


class TestEmbeddingResult:
    """Test EmbeddingResult dataclass."""

    def test_basic_creation(self):
        result = EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="test-model",
            dimensions=3,
        )
        assert result.model == "test-model"
        assert result.dimensions == 3
        assert len(result.embeddings) == 1

    def test_empty_embeddings(self):
        result = EmbeddingResult(embeddings=[], model="test", dimensions=768)
        assert result.embeddings == []


class TestOllamaEmbeddingClient:
    """Test OllamaEmbeddingClient."""

    def test_is_configured_true(self):
        client = OllamaEmbeddingClient(url="http://localhost:11434", model="nomic-embed-text")
        assert client.is_configured() is True

    def test_is_configured_false_no_url(self):
        client = OllamaEmbeddingClient(url="", model="nomic-embed-text")
        assert client.is_configured() is False

    def test_is_configured_false_no_model(self):
        client = OllamaEmbeddingClient(url="http://localhost:11434", model="")
        assert client.is_configured() is False

    def test_name(self):
        client = OllamaEmbeddingClient()
        assert client.name == "ollama"

    @patch("app.services.embedding_client.requests.get")
    def test_test_connection_success(self, mock_get):
        mock_get.return_value = MagicMock(ok=True)
        client = OllamaEmbeddingClient(url="http://localhost:11434", model="test")
        assert client.test_connection() is True
        mock_get.assert_called_once()

    @patch("app.services.embedding_client.requests.get")
    def test_test_connection_failure(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")
        client = OllamaEmbeddingClient(url="http://localhost:11434", model="test")
        assert client.test_connection() is False

    def test_test_connection_not_configured(self):
        client = OllamaEmbeddingClient(url="", model="test")
        assert client.test_connection() is False

    @patch("app.services.embedding_client.requests.post")
    def test_embed_single_batch(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        }
        mock_post.return_value = mock_resp

        client = OllamaEmbeddingClient(
            url="http://localhost:11434", model="test-model", dimensions=3,
        )
        result = client.embed(["hello", "world"])

        assert len(result.embeddings) == 2
        assert result.model == "test-model"
        assert result.dimensions == 3
        mock_post.assert_called_once()

    @patch("app.services.embedding_client.requests.post")
    def test_embed_multiple_batches(self, mock_post):
        """Texts exceeding batch_size should be split into multiple requests."""
        mock_resp_batch1 = MagicMock()
        mock_resp_batch1.raise_for_status = MagicMock()
        mock_resp_batch1.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

        mock_resp_batch2 = MagicMock()
        mock_resp_batch2.raise_for_status = MagicMock()
        mock_resp_batch2.json.return_value = {"embeddings": [[0.5, 0.6]]}

        mock_post.side_effect = [mock_resp_batch1, mock_resp_batch2]

        client = OllamaEmbeddingClient(
            url="http://localhost:11434", model="test", batch_size=2,
        )
        result = client.embed(["a", "b", "c"])

        assert mock_post.call_count == 2  # batch of 2 + batch of 1
        assert len(result.embeddings) == 3  # 2 from first batch + 1 from second

    @patch("app.services.embedding_client.requests.post")
    def test_embed_empty_list(self, mock_post):
        client = OllamaEmbeddingClient(url="http://localhost:11434", model="test")
        result = client.embed([])
        assert result.embeddings == []
        mock_post.assert_not_called()

    def test_embed_not_configured(self):
        client = OllamaEmbeddingClient(url="", model="test")
        with pytest.raises(ValueError, match="not configured"):
            client.embed(["hello"])

    @patch("app.services.embedding_client.requests.post")
    def test_embed_single(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        mock_post.return_value = mock_resp

        client = OllamaEmbeddingClient(url="http://localhost:11434", model="test")
        vector = client.embed_single("hello")
        assert vector == [0.1, 0.2, 0.3]

    @patch("app.services.embedding_client.requests.post")
    def test_embed_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        mock_post.return_value = mock_resp

        client = OllamaEmbeddingClient(url="http://localhost:11434", model="test")
        with pytest.raises(Exception, match="500"):
            client.embed(["hello"])

    def test_url_trailing_slash_stripped(self):
        client = OllamaEmbeddingClient(url="http://localhost:11434/")
        assert client._url == "http://localhost:11434"


class TestAPIEmbeddingClient:
    """Test APIEmbeddingClient (OpenAI-compatible)."""

    def test_is_configured_true(self):
        client = APIEmbeddingClient(url="http://api.example.com", model="text-embedding-ada-002")
        assert client.is_configured() is True

    def test_is_configured_false(self):
        client = APIEmbeddingClient(url="", model="")
        assert client.is_configured() is False

    def test_name(self):
        client = APIEmbeddingClient()
        assert client.name == "api"

    def test_headers_with_api_key(self):
        client = APIEmbeddingClient(url="http://api", model="m", api_key="sk-test")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_api_key(self):
        client = APIEmbeddingClient(url="http://api", model="m", api_key="")
        headers = client._headers()
        assert "Authorization" not in headers

    @patch("app.services.embedding_client.requests.post")
    def test_embed(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
            ]
        }
        mock_post.return_value = mock_resp

        client = APIEmbeddingClient(url="http://api", model="test-model")
        result = client.embed(["hello", "world"])

        # Should be sorted by index
        assert result.embeddings[0] == [0.1, 0.2, 0.3]
        assert result.embeddings[1] == [0.4, 0.5, 0.6]

    @patch("app.services.embedding_client.requests.post")
    def test_test_connection_success(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        client = APIEmbeddingClient(url="http://api", model="test")
        assert client.test_connection() is True

    @patch("app.services.embedding_client.requests.post")
    def test_test_connection_failure(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        client = APIEmbeddingClient(url="http://api", model="test")
        assert client.test_connection() is False

    def test_embed_not_configured(self):
        client = APIEmbeddingClient(url="", model="")
        with pytest.raises(ValueError, match="not configured"):
            client.embed(["hello"])


class TestCreateEmbeddingClient:
    """Test factory function."""

    def test_create_ollama(self):
        client = create_embedding_client(
            backend="ollama", url="http://localhost:11434", model="test",
        )
        assert isinstance(client, OllamaEmbeddingClient)

    def test_create_openai(self):
        client = create_embedding_client(
            backend="openai", url="http://api", model="test", api_key="sk-test",
        )
        assert isinstance(client, APIEmbeddingClient)

    def test_create_api(self):
        client = create_embedding_client(
            backend="api", url="http://api", model="test",
        )
        assert isinstance(client, APIEmbeddingClient)

    def test_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown embedding backend"):
            create_embedding_client(backend="unknown")
