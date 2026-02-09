"""
Embedding client for generating vector embeddings via HTTP APIs.

Supports Ollama (native) and OpenAI-compatible (API) backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests

from app.utils import get_logger


@dataclass
class EmbeddingResult:
    """Result from an embedding request."""

    embeddings: list[list[float]]
    model: str
    dimensions: int


class EmbeddingClient(ABC):
    """Abstract base class for embedding clients."""

    @abstractmethod
    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            EmbeddingResult with embeddings list
        """
        raise NotImplementedError

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text and return the vector.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            ValueError: If embedding service returns no results
        """
        result = self.embed([text])
        if not result.embeddings:
            raise ValueError(f"Embedding service returned no results for input text")
        return result.embeddings[0]

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity to the embedding service.

        Returns:
            True if service is reachable
        """
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the client has valid configuration.

        Returns:
            True if URL and model are set
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name for logging."""
        raise NotImplementedError


class OllamaEmbeddingClient(EmbeddingClient):
    """Embedding client for Ollama's native API.

    Uses POST {url}/api/embed with {"model": ..., "input": [texts]}.
    """

    def __init__(
        self,
        url: str = "",
        model: str = "nomic-embed-text",
        dimensions: int = 768,
        timeout: int = 60,
        batch_size: int = 32,
    ):
        self._url = url.rstrip("/") if url else ""
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout
        self._batch_size = batch_size
        self.logger = get_logger("embedding.ollama")

    @property
    def name(self) -> str:
        return "ollama"

    def is_configured(self) -> bool:
        return bool(self._url and self._model)

    def test_connection(self) -> bool:
        if not self.is_configured():
            return False
        try:
            # Ollama responds to GET /api/tags
            resp = requests.get(f"{self._url}/api/tags", timeout=10)
            return resp.ok
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not self.is_configured():
            raise ValueError("Ollama embedding client not configured")
        if not texts:
            return EmbeddingResult(embeddings=[], model=self._model, dimensions=self._dimensions)

        all_embeddings: list[list[float]] = []

        # Batch the requests
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            resp = requests.post(
                f"{self._url}/api/embed",
                json={"model": self._model, "input": batch},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if "embeddings" not in data:
                raise ValueError(
                    f"Unexpected Ollama response format: missing 'embeddings' key. "
                    f"Response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
                )
            all_embeddings.extend(data["embeddings"])

        # Detect dimensions from first embedding
        dims = len(all_embeddings[0]) if all_embeddings else self._dimensions

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._model,
            dimensions=dims,
        )


class APIEmbeddingClient(EmbeddingClient):
    """Embedding client for OpenAI-compatible APIs.

    Uses POST {url}/v1/embeddings with Bearer token auth.
    """

    def __init__(
        self,
        url: str = "",
        model: str = "",
        api_key: str = "",
        dimensions: int = 768,
        timeout: int = 60,
        batch_size: int = 32,
    ):
        self._url = url.rstrip("/") if url else ""
        self._model = model
        self._api_key = api_key
        self._dimensions = dimensions
        self._timeout = timeout
        self._batch_size = batch_size
        self.logger = get_logger("embedding.api")

    @property
    def name(self) -> str:
        return "api"

    def is_configured(self) -> bool:
        return bool(self._url and self._model)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def test_connection(self) -> bool:
        if not self.is_configured():
            return False
        try:
            # Try a minimal embedding to verify connectivity
            resp = requests.post(
                f"{self._url}/v1/embeddings",
                json={"model": self._model, "input": ["test"]},
                headers=self._headers(),
                timeout=10,
            )
            return resp.ok
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not self.is_configured():
            raise ValueError("API embedding client not configured")
        if not texts:
            return EmbeddingResult(embeddings=[], model=self._model, dimensions=self._dimensions)

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            resp = requests.post(
                f"{self._url}/v1/embeddings",
                json={"model": self._model, "input": batch},
                headers=self._headers(),
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # OpenAI format: {"data": [{"embedding": [...], "index": 0}, ...]}
            if "data" not in data:
                raise ValueError(
                    f"Unexpected API response format: missing 'data' key. "
                    f"Response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
                )
            for item in data["data"]:
                if "embedding" not in item or "index" not in item:
                    raise ValueError(
                        f"Malformed embedding response item: missing 'embedding' or 'index' key. "
                        f"Item keys: {list(item.keys()) if isinstance(item, dict) else type(item).__name__}"
                    )
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            all_embeddings.extend([item["embedding"] for item in sorted_data])

        dims = len(all_embeddings[0]) if all_embeddings else self._dimensions

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._model,
            dimensions=dims,
        )


def create_embedding_client(
    backend: str = "ollama",
    model: str = "nomic-embed-text",
    url: str = "",
    api_key: str = "",
    dimensions: int = 768,
    timeout: int = 60,
) -> EmbeddingClient:
    """Factory function to create an embedding client.

    Args:
        backend: Backend type ("ollama", "openai", or "api")
        model: Model name
        url: Service URL
        api_key: API key (for API/OpenAI backends)
        dimensions: Expected embedding dimensions
        timeout: Request timeout in seconds

    Returns:
        EmbeddingClient instance

    Raises:
        ValueError: If backend type is unknown
    """
    if backend in ("ollama",):
        return OllamaEmbeddingClient(
            url=url,
            model=model,
            dimensions=dimensions,
            timeout=timeout,
        )
    elif backend in ("openai", "api"):
        return APIEmbeddingClient(
            url=url,
            model=model,
            api_key=api_key,
            dimensions=dimensions,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unknown embedding backend: {backend}")
