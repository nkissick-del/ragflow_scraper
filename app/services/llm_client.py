"""
LLM client for text generation via HTTP APIs.

Supports Ollama (native) and OpenAI-compatible (API) backends.
Used for document enrichment and contextual chunk descriptions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import requests

from app.utils import get_logger


@dataclass
class LLMResult:
    """Result from an LLM chat request."""

    content: str
    model: str
    finish_reason: str


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_format: Optional format hint ('json' for JSON output)
            max_tokens: Optional max tokens for response

        Returns:
            LLMResult with generated content
        """
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity to the LLM service.

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


class OllamaLLMClient(LLMClient):
    """LLM client for Ollama's native API.

    Uses POST {url}/api/chat with {"model": ..., "messages": ..., "stream": false}.
    """

    def __init__(
        self,
        url: str = "",
        model: str = "llama3.1:8b",
        timeout: int = 120,
    ):
        self._url = url.rstrip("/") if url else ""
        self._model = model
        self._timeout = timeout
        self.logger = get_logger("llm.ollama")

    @property
    def name(self) -> str:
        return "ollama"

    def is_configured(self) -> bool:
        return bool(self._url and self._model)

    def test_connection(self) -> bool:
        if not self.is_configured():
            return False
        try:
            resp = requests.get(f"{self._url}/api/tags", timeout=10)
            return resp.ok
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        if not self.is_configured():
            raise ValueError("Ollama LLM client not configured")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if response_format == "json":
            payload["format"] = "json"
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        resp = requests.post(
            f"{self._url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        content = message.get("content", "")
        done_reason = data.get("done_reason", "stop")

        return LLMResult(
            content=content,
            model=data.get("model", self._model),
            finish_reason=done_reason,
        )


class APILLMClient(LLMClient):
    """LLM client for OpenAI-compatible APIs.

    Uses POST {url}/v1/chat/completions with Bearer token auth.
    """

    def __init__(
        self,
        url: str = "",
        model: str = "",
        api_key: str = "",
        timeout: int = 120,
    ):
        self._url = url.rstrip("/") if url else ""
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self.logger = get_logger("llm.api")

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
            resp = requests.post(
                f"{self._url}/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 1,
                },
                headers=self._headers(),
                timeout=10,
            )
            return resp.ok
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        if not self.is_configured():
            raise ValueError("API LLM client not configured")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens

        resp = requests.post(
            f"{self._url}/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError(
                f"Unexpected API response: no choices. "
                f"Response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
            )

        choice = choices[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "stop")

        return LLMResult(
            content=content,
            model=data.get("model", self._model),
            finish_reason=finish_reason,
        )


def create_llm_client(
    backend: str = "ollama",
    model: str = "llama3.1:8b",
    url: str = "",
    api_key: str = "",
    timeout: int = 120,
) -> LLMClient:
    """Factory function to create an LLM client.

    Args:
        backend: Backend type ("ollama", "openai", or "api")
        model: Model name
        url: Service URL
        api_key: API key (for API/OpenAI backends)
        timeout: Request timeout in seconds

    Returns:
        LLMClient instance

    Raises:
        ValueError: If backend type is unknown
    """
    if backend in ("ollama",):
        return OllamaLLMClient(
            url=url,
            model=model,
            timeout=timeout,
        )
    elif backend in ("openai", "api"):
        return APILLMClient(
            url=url,
            model=model,
            api_key=api_key,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")
