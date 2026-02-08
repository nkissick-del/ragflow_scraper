"""
AnythingLLM client for document ingestion.

Provides HTTP client for interacting with AnythingLLM API:
- Document upload via multipart/form-data
- Workspace management
- Bearer token authentication
- Metadata support
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from requests import Response, Session

from app.config import Config
from app.utils import get_logger
from app.utils.logging_config import log_exception


@dataclass
class UploadResult:
    """Result of document upload operation."""

    success: bool
    document_id: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    workspace_id: Optional[str] = None


class AnythingLLMClient:
    """Client for AnythingLLM API."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
        timeout: int = 60,
        max_attempts: int = 3,
    ) -> None:
        """
        Initialize AnythingLLM client.

        Args:
            api_url: AnythingLLM base URL (e.g., 'http://localhost:3001').
                     The client appends '/api/v1/...' paths automatically.
                     If URL ends with '/api', it will be stripped.
            api_key: API key for authentication (defaults to Config.ANYTHINGLLM_API_KEY)
            workspace_id: Default workspace slug (defaults to Config.ANYTHINGLLM_WORKSPACE_ID)
            timeout: Request timeout in seconds
            max_attempts: Maximum number of attempts (including the first attempt)
        """
        # Strip /api suffix if present to avoid double /api/api prefix
        api_url_clean = (api_url or Config.ANYTHINGLLM_API_URL or "").rstrip("/")
        if api_url_clean.endswith("/api"):
            api_url_clean = api_url_clean[:-4]

        self.api_url = api_url_clean
        self.api_key = api_key or Config.ANYTHINGLLM_API_KEY or ""
        self.workspace_id = workspace_id or Config.ANYTHINGLLM_WORKSPACE_ID or ""
        self.timeout = timeout
        # Ensure at least one attempt is made
        self.max_attempts = max(1, max_attempts)
        self.session: Session = requests.Session()
        self.logger = get_logger("anythingllm.client")
        self._closed = False

    def _ensure_not_closed(self) -> None:
        """Raise RuntimeError if client is closed."""
        if self._closed:
            raise RuntimeError("AnythingLLMClient is closed")

    def close(self) -> None:
        """Close the session and release connection pool resources."""
        if self._closed:
            return
        if hasattr(self, "session") and self.session:
            self.session.close()
            self.session = None  # type: ignore[assignment]
        self._closed = True

    def __enter__(self) -> "AnythingLLMClient":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close session."""
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> Response:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/api/v1/workspaces')
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            requests.RequestException: If request fails after retries
            RuntimeError: If client is closed
        """
        self._ensure_not_closed()
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        kwargs.setdefault("timeout", self.timeout)
        url = f"{self.api_url}{path}"

        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self.session.request(method, url, headers=headers, **kwargs)
                if resp.status_code >= 500 and attempt < self.max_attempts:
                    self.logger.warning(
                        f"{method} {path} returned {resp.status_code}, retrying..."
                    )
                    time.sleep(0.5 * attempt)
                    continue
                return resp
            except requests.RequestException as exc:
                if attempt == self.max_attempts:
                    raise
                self.logger.warning(f"{method} {url} failed (attempt {attempt}): {exc}")
                time.sleep(0.5 * attempt)

        raise RuntimeError(
            f"Request failed after {self.max_attempts} attempts: {method} {path}"
        )

    def test_connection(self) -> bool:
        """
        Test connection to AnythingLLM API.

        Returns:
            True if connection successful, False otherwise
        """
        self._ensure_not_closed()
        try:
            # Try to list workspaces as a connectivity test
            resp = self._request("GET", "/api/v1/workspaces")
            return resp.ok
        except Exception as exc:
            log_exception(self.logger, exc, "anythingllm.test_connection")
            return False

    def list_workspaces(self) -> list[dict]:
        """
        List available workspaces.

        Returns:
            List of workspace dictionaries
        """
        self._ensure_not_closed()
        try:
            resp = self._request("GET", "/api/v1/workspaces")
            if resp.ok:
                data = resp.json()
                # Handle different response formats
                if isinstance(data, dict):
                    return data.get("workspaces", [])
                elif isinstance(data, list):
                    return data
                return []
            return []
        except Exception as exc:
            log_exception(self.logger, exc, "anythingllm.list_workspaces")
            return []

    def list_documents(self) -> list[dict]:
        """
        List all documents stored in AnythingLLM.

        Returns:
            List of document dicts
        """
        self._ensure_not_closed()
        try:
            resp = self._request("GET", "/api/v1/documents")
            if resp.ok:
                data = resp.json()
                if isinstance(data, dict):
                    # Normalize: flatten localFiles items
                    local_files = data.get("localFiles", {})
                    items = local_files.get("items", [])
                    docs: list[dict] = []
                    for folder in items:
                        if isinstance(folder, dict):
                            for doc in folder.get("items", []):
                                if isinstance(doc, dict):
                                    docs.append(doc)
                    return docs
                elif isinstance(data, list):
                    return data
            return []
        except Exception as exc:
            log_exception(self.logger, exc, "anythingllm.list_documents")
            return []

    def upload_document(
        self,
        filepath: Path,
        folder_name: str = "default",
        workspace_ids: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> UploadResult:
        """
        Upload document to AnythingLLM.

        Args:
            filepath: Path to file to upload
            folder_name: Folder name for organization (default: "default")
            workspace_ids: List of workspace IDs to add document to
            metadata: Optional metadata dictionary

        Returns:
            UploadResult with success status and document ID
        """
        self._ensure_not_closed()
        if not filepath.exists():
            return UploadResult(
                success=False,
                error=f"File not found: {filepath}",
                filename=filepath.name,
            )

        try:
            # Prepare multipart form data
            data = {}

            # Add workspace IDs if provided
            if workspace_ids:
                data["addToWorkspaces"] = ",".join(workspace_ids)
            elif self.workspace_id:
                data["addToWorkspaces"] = self.workspace_id

            # Add metadata if provided
            if metadata:
                # AnythingLLM expects metadata as JSON string or individual fields
                data["metadata"] = json.dumps(metadata)

            # Use context manager to ensure file is always closed
            with open(filepath, "rb") as f:
                files = {"file": f}
                resp = self._request(
                    "POST",
                    "/api/v1/document/upload",
                    files=files,
                    data=data,
                )

            if resp.ok:
                response_data = resp.json()
                # Validate response_data is a dict
                if not isinstance(response_data, dict):
                    self.logger.warning(
                        f"Upload response is not a dict: {type(response_data).__name__} - {response_data}"
                    )
                    return UploadResult(
                        success=True,
                        filename=filepath.name,
                        workspace_id=self.workspace_id,
                    )

                # Check for documents array (actual API format)
                if "documents" in response_data and response_data["documents"]:
                    doc = response_data["documents"][0]
                    # Validate doc is a dict before accessing fields
                    if not isinstance(doc, dict):
                        self.logger.warning(
                            f"Document item is not a dict: {type(doc).__name__} - {doc}"
                        )
                        return UploadResult(
                            success=True,
                            filename=filepath.name,
                            workspace_id=self.workspace_id,
                        )
                    effective_workspace_id = (
                        (workspace_ids[0] if workspace_ids else None)
                        or doc.get("workspace_id")
                        or doc.get("workspaceId")
                        or self.workspace_id
                    )
                    return UploadResult(
                        success=True,
                        document_id=doc.get("id"),
                        filename=filepath.name,
                        workspace_id=effective_workspace_id,
                    )

                # Fallback to direct fields
                doc_id = response_data.get("id") or response_data.get("document_id")
                workspace = (
                    response_data.get("workspace_id")
                    or response_data.get("workspaceId")
                    or (workspace_ids[0] if workspace_ids else self.workspace_id)
                )
                return UploadResult(
                    success=True,
                    document_id=doc_id,
                    filename=filepath.name,
                    workspace_id=workspace,
                )

            sanitized_text = self._sanitize_response_text(resp.text)
            return UploadResult(
                success=False,
                error=f"Upload failed: {resp.status_code} - {sanitized_text}",
                filename=filepath.name,
            )

        except Exception as exc:
            error_msg = f"Upload failed: {exc}"
            log_exception(self.logger, exc, "anythingllm.upload_document")
            return UploadResult(
                success=False,
                error=error_msg,
                filename=filepath.name,
            )

    def _sanitize_response_text(self, text: str, max_len: int = 500) -> str:
        """
        Sanitize and truncate response text for error messages.

        Args:
            text: Raw response text
            max_len: Maximum length of returned string

        Returns:
            Sanitized and potentially truncated text
        """
        if not text:
            return ""

        # Remove control characters and excessive whitespace
        sanitized = "".join(ch for ch in text if ch.isprintable())
        sanitized = " ".join(sanitized.split())

        if len(sanitized) > max_len:
            return sanitized[:max_len] + "..."
        return sanitized


__all__ = [
    "AnythingLLMClient",
    "UploadResult",
]
