"""
Lean RAGFlow client composed of small, testable units.

Responsibilities:
- HTTP adapter with shared retry/backoff
- API-key document ingestion (upload, trigger parse, poll)
- Optional session auth for catalog endpoints
- Metadata push with duplicate detection
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional

import requests
from requests import Response, Session

from app.config import Config
from app.utils import get_logger
from app.utils.logging_config import log_exception

if TYPE_CHECKING:
    from app.services.ragflow_ingestion import RAGFlowIngestionWorkflow

# Static catalogs
CHUNK_METHODS = [
    "naive",
    "book",
    "email",
    "laws",
    "manual",
    "one",
    "paper",
    "picture",
    "presentation",
    "qa",
    "table",
    "tag",
]

PDF_PARSERS = [
    "DeepDOC",
    "Naive",
    "MinerU",
    "Docling",
]


@dataclass
class UploadResult:
    success: bool
    document_id: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    skipped_duplicate: bool = False
    metadata_pushed: bool = False


@dataclass
class DatasetInfo:
    id: str
    name: str
    document_count: int = 0
    chunk_count: int = 0
    status: str = "unknown"


class HttpAdapter:
    """HTTP helper with shared retry/backoff."""

    def __init__(self, api_url: str, api_key: Optional[str], timeout: int = 60, max_retries: int = 3):
        self.base_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session: Session = requests.Session()
        self.logger = get_logger("ragflow.http")

    def request(self, method: str, path: str, **kwargs) -> Response:
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        kwargs.setdefault("timeout", self.timeout)
        url = f"{self.base_url}{path}"

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(method, url, headers=headers, **kwargs)
                if resp.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(0.5 * attempt)
                    continue
                return resp
            except requests.RequestException as exc:  # pragma: no cover - network failure path
                if attempt == self.max_retries:
                    raise
                self.logger.warning(f"{method} {url} failed (attempt {attempt}): {exc}")
                time.sleep(0.5 * attempt)

        raise RuntimeError(f"Request failed after {self.max_retries} attempts: {method} {path}")


class RAGFlowSession:
    """Session-based auth for admin/catalog endpoints."""

    PUBLIC_KEY = (
        getattr(Config, "RAGFLOW_PUBLIC_KEY", "")
        or """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArq9XTUSeYr2+N1h3Afl/
z8Dse/2yD0ZGrKwx+EEEcdsBLca9Ynmx3nIB5obmLlSfmskLpBo0UACBmB5rEjBp
2Q2f3AG3Hjd4B+gNCG6BDaawuDlgANIhGnaTLrIqWrrcm4EMzJOnAOI1fgzJRsOO
UEfaS318Eq9OVO3apEyCCt0lOQK6PuksduOjVxtltDav+guVAA068NrPYmRNabVK
RNLJpL8w4D44sfth5RvZ3q9t+6RTArpEtc5sh5ChzvqPOzKGMXW83C95TxmXqpbK
6olN4RevSfVjEAgCydH6HN6OhtOQEcnrU97r9H0iZOWwbw3pVrZiUkuRD1R56Wzs
2wIDAQAB
-----END PUBLIC KEY-----"""
    )

    def __init__(self, api_url: str, username: str, password: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._token: Optional[str] = None
        self._session = requests.Session()
        self.logger = get_logger("ragflow.session")

    def _encrypt_password(self, password: str) -> str:
        try:
            from Crypto.PublicKey import RSA  # type: ignore[import-untyped]
            from Crypto.Cipher import PKCS1_v1_5  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover - Crypto missing
            raise RuntimeError("Crypto dependencies missing for session auth") from exc

        payload = base64.b64encode(password.encode("utf-8"))
        public_key = RSA.import_key(self.PUBLIC_KEY)
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(payload)
        return base64.b64encode(encrypted).decode("utf-8")

    def _ensure_token(self) -> bool:
        if self._token:
            return True
        try:
            encrypted_password = self._encrypt_password(self.password)
            resp = self._session.post(
                f"{self.api_url}/v1/user/login",
                json={"email": self.username, "password": encrypted_password},
                timeout=self.timeout,
            )
            if resp.ok and resp.json().get("code") == 0:
                self._token = resp.headers.get("authorization", "")
                return bool(self._token)
            self.logger.warning(f"Session login failed: {resp.text}")
            return False
        except Exception as exc:
            log_exception(self.logger, exc, "ragflow.session.login")
            return False

    def get(self, endpoint: str) -> dict:
        if not self._ensure_token():
            return {}
        try:
            resp = self._session.get(
                f"{self.api_url}{endpoint}",
                headers={"Authorization": self._token or ""},
                timeout=self.timeout,
            )
            if resp.ok:
                return resp.json()
            return {}
        except Exception as exc:  # pragma: no cover - network failure
            log_exception(self.logger, exc, "ragflow.session.get", endpoint=endpoint)
            return {}


class RAGFlowClient:
    """Facade over HTTP adapter and optional session auth."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        self.api_url = (api_url or Config.RAGFLOW_API_URL).rstrip("/")
        self.api_key = api_key or Config.RAGFLOW_API_KEY
        self.timeout = timeout
        self.http = HttpAdapter(self.api_url, self.api_key, timeout=timeout, max_retries=max_retries)
        self.logger = get_logger("ragflow.client")

        self._session_auth: Optional[RAGFlowSession] = None
        if username or Config.RAGFLOW_USERNAME:
            self._session_auth = RAGFlowSession(
                api_url=self.api_url,
                username=username or Config.RAGFLOW_USERNAME,
                password=password or Config.RAGFLOW_PASSWORD,
                timeout=timeout,
            )

        # Lazy-load ingestion workflow
        self._ingestion_workflow: Optional[RAGFlowIngestionWorkflow] = None

    @property
    def ingestion(self) -> RAGFlowIngestionWorkflow:
        """Get ingestion workflow helper (lazy-loaded)."""
        if self._ingestion_workflow is None:
            from app.services.ragflow_ingestion import RAGFlowIngestionWorkflow

            self._ingestion_workflow = RAGFlowIngestionWorkflow(self)
        return self._ingestion_workflow

    # Catalog helpers
    @property
    def session_configured(self) -> bool:
        return self._session_auth is not None

    def list_pdf_parsers(self) -> list[str]:
        return PDF_PARSERS

    def list_chunk_methods(self) -> list[str]:
        return CHUNK_METHODS

    def list_ingestion_pipelines(self) -> list[dict]:
        try:
            resp = self.http.request("GET", "/api/v1/pipelines")
            if resp.ok:
                return resp.json().get("data", [])
        except Exception as exc:
            log_exception(self.logger, exc, "ragflow.pipelines.fetch")
        return []

    def list_embedding_models(self) -> list[dict]:
        if not self._session_auth:
            return []
        data = self._session_auth.get("/api/v1/models")
        return data.get("data", []) if data else []

    def list_datasets(self) -> list[DatasetInfo]:
        try:
            resp = self.http.request("GET", "/api/v1/datasets")
            if not resp.ok:
                return []
            payload = resp.json().get("data", [])
            return [
                DatasetInfo(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    document_count=item.get("document_count", 0),
                    chunk_count=item.get("chunk_count", 0),
                    status=item.get("status", "unknown"),
                )
                for item in payload
            ]
        except Exception as exc:
            log_exception(self.logger, exc, "ragflow.datasets.list")
            return []

    def test_connection(self) -> bool:
        try:
            resp = self.http.request("GET", "/api/v1/datasets")
            return resp.ok
        except Exception as exc:  # pragma: no cover - network failure
            log_exception(self.logger, exc, "ragflow.test_connection")
            return False

    # Document ingestion
    def upload_document(self, dataset_id: str, filepath: Path) -> UploadResult:
        files = {"file": open(filepath, "rb")}
        try:
            resp = self.http.request("POST", f"/api/v1/datasets/{dataset_id}/documents", files=files)
            if resp.ok:
                data = resp.json().get("data", {})
                return UploadResult(success=True, document_id=data.get("id"), filename=filepath.name)
            return UploadResult(success=False, error=resp.text, filename=filepath.name)
        finally:
            files["file"].close()

    def check_document_exists(self, dataset_id: str, file_hash: str) -> Optional[str]:
        try:
            resp = self.http.request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents/hash/{file_hash}",
            )
            if resp.ok:
                data = resp.json().get("data") or {}
                return data.get("id")
            return None
        except Exception:
            return None

    def wait_for_document_ready(self, dataset_id: str, document_id: str, timeout: float = 10.0, poll_interval: float = 0.5) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            resp = self.http.request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
            )
            if resp.ok:
                status = resp.json().get("data", {}).get("status")
                if status in {"ready", "parsed", "completed"}:
                    return True
            time.sleep(poll_interval)
        return False

    def set_document_metadata(self, dataset_id: str, document_id: str, metadata: dict) -> bool:
        resp = self.http.request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/documents/{document_id}/metadata",
            json=metadata,
        )
        return resp.ok

    def upload_documents(self, dataset_id: str, files: Iterable[Path]) -> list[UploadResult]:
        results: list[UploadResult] = []
        for fp in files:
            results.append(self.upload_document(dataset_id, fp))
        return results

    def upload_documents_with_metadata(
        self,
        dataset_id: str,
        docs: list[dict],
        *,
        check_duplicates: bool = True,
        wait_timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> list[UploadResult]:
        """
        Upload documents with metadata using ingestion workflow.

        Args:
            dataset_id: RAGFlow dataset ID
            docs: List of dicts with 'filepath' (Path) and optional 'metadata' (DocumentMetadata)
            check_duplicates: If True, skip files that already exist (by hash)
            wait_timeout: Max seconds to wait for each document to parse
            poll_interval: Seconds between status checks

        Returns:
            List of UploadResult, one per document
        """
        return self.ingestion.ingest_with_metadata(
            dataset_id,
            docs,
            check_duplicates=check_duplicates,
            wait_timeout=wait_timeout,
            poll_interval=poll_interval,
        )

    def trigger_parsing(self, dataset_id: str, document_ids: Optional[list[str]] = None) -> bool:
        payload: dict[str, Any] = {"document_ids": document_ids or []}
        resp = self.http.request("POST", f"/api/v1/datasets/{dataset_id}/documents/parse", json=payload)
        return resp.ok

    def wait_for_parsing(self, dataset_id: str, document_ids: Optional[list[str]] = None, timeout: float = 120.0, poll_interval: float = 2.0) -> bool:
        start = time.time()
        target_ids = set(document_ids or [])
        while time.time() - start < timeout:
            resp = self.http.request("GET", f"/api/v1/datasets/{dataset_id}/documents")
            if not resp.ok:
                time.sleep(poll_interval)
                continue
            docs = resp.json().get("data", [])
            completed = [d for d in docs if d.get("status") in {"parsed", "completed"}]
            if not target_ids:
                return bool(completed)
            if target_ids.issubset({d.get("id") for d in completed}):
                return True
            time.sleep(poll_interval)
        return False


__all__ = [
    "RAGFlowClient",
    "UploadResult",
    "DatasetInfo",
    "CHUNK_METHODS",
    "PDF_PARSERS",
]
