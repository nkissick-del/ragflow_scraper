"""
RAGFlow API client for document ingestion.

Handles authentication, document upload, and parsing status monitoring.
Supports both API key auth (for document operations) and session auth (for admin APIs).
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests
from Crypto.PublicKey import RSA  # type: ignore[import-untyped]
from Crypto.Cipher import PKCS1_v1_5  # type: ignore[import-untyped]

from app.config import Config
from app.utils import get_logger


# RAGFlow default public key for password encryption
# This is the standard key bundled with RAGFlow installations
# See: https://github.com/infiniflow/ragflow/blob/main/conf/public.pem
RAGFLOW_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArq9XTUSeYr2+N1h3Afl/
z8Dse/2yD0ZGrKwx+EEEcdsBLca9Ynmx3nIB5obmLlSfmskLpBo0UACBmB5rEjBp
2Q2f3AG3Hjd4B+gNCG6BDaawuDlgANIhGnaTLrIqWrrcm4EMzJOnAOI1fgzJRsOO
UEfaS318Eq9OVO3apEyCCt0lOQK6PuksduOjVxtltDav+guVAA068NrPYmRNabVK
RNLJpL8w4D44sfth5RvZ3q9t+6RTArpEtc5sh5ChzvqPOzKGMXW83C95TxmXqpbK
6olN4RevSfVjEAgCydH6HN6OhtOQEcnrU97r9H0iZOWwbw3pVrZiUkuRD1R56Wzs
2wIDAQAB
-----END PUBLIC KEY-----"""

# Available chunk methods in RAGFlow (validated by API)
# These are the values accepted by RAGFlow's dataset creation endpoint
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

# Available PDF parsers for layout_recognize in parser_config
# Note: MinerU and Docling require server-side configuration (USE_MINERU, USE_DOCLING)
# If not configured, parsing will fail gracefully with an error
PDF_PARSERS = [
    "DeepDOC",   # Default - OCR, table structure, layout recognition
    "Naive",     # Plain text extraction, no OCR (good for markdown)
    "MinerU",    # Experimental - requires USE_MINERU=true in RAGFlow docker/.env
    "Docling",   # Experimental - requires USE_DOCLING=true in RAGFlow docker/.env
]


class RAGFlowSession:
    """
    Session-based auth for RAGFlow internal APIs.

    Used to access admin endpoints like model listing that require
    user login rather than API key auth.
    """

    def __init__(
        self,
        api_url: str,
        username: str,
        password: str,
        timeout: int = 30,
    ):
        """
        Initialize session client.

        Args:
            api_url: RAGFlow API base URL
            username: User email for login
            password: User password
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._session = requests.Session()
        self._token: Optional[str] = None
        self.logger = get_logger("ragflow.session")

    def _encrypt_password(self, password: str) -> str:
        """
        Encrypt password using RSA public key (PKCS1_v1.5 padding).

        RAGFlow expects: base64(RSA_encrypt(base64(password)))
        Uses the standard RAGFlow public key.

        Args:
            password: Plain text password

        Returns:
            Base64-encoded encrypted password
        """
        # First base64 encode the password
        password_b64 = base64.b64encode(password.encode("utf-8"))

        # Load the public key (using the standard RAGFlow key)
        public_key = RSA.import_key(RAGFLOW_PUBLIC_KEY)
        cipher = PKCS1_v1_5.new(public_key)

        # Encrypt and base64 encode the result
        encrypted = cipher.encrypt(password_b64)
        return base64.b64encode(encrypted).decode("utf-8")

    def login(self) -> bool:
        """
        Login and get session token.

        Note: RAGFlow uses /v1/ prefix (not /api/v1/) for user endpoints.
        Password must be RSA encrypted before sending.
        The token comes from the 'authorization' response header (not the body).

        Returns:
            True if login successful
        """
        try:
            # Encrypt the password using the standard RAGFlow public key
            encrypted_password = self._encrypt_password(self.password)

            # Login with encrypted password
            response = self._session.post(
                f"{self.api_url}/v1/user/login",
                json={"email": self.username, "password": encrypted_password},
                timeout=self.timeout,
            )

            if response.ok:
                data = response.json()
                if data.get("code") == 0:
                    # Token comes from the 'authorization' header (lowercase)
                    # Format: encoded JWT-like token, NOT "Bearer xxx"
                    self._token = response.headers.get("authorization", "")
                    if self._token:
                        self.logger.debug("Session login successful")
                        return True

            self.logger.warning(f"Session login failed: {response.text}")
            return False

        except Exception as e:
            self.logger.error(f"Session login error: {e}")
            return False

    def _ensure_authenticated(self) -> bool:
        """
        Ensure we have a valid session.

        Returns:
            True if authenticated
        """
        if not self._token:
            return self.login()
        return True

    def get(self, endpoint: str, **kwargs) -> dict:
        """
        Make authenticated GET request.

        Args:
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON as dictionary
        """
        if not self._ensure_authenticated():
            return {}

        kwargs.setdefault("timeout", self.timeout)
        headers = kwargs.pop("headers", {})
        # Token is already in the correct format from the login response header
        headers["Authorization"] = self._token

        try:
            response = self._session.get(
                f"{self.api_url}{endpoint}",
                headers=headers,
                **kwargs,
            )
            if response.ok:
                return response.json()
            self.logger.warning(f"GET {endpoint} failed: {response.status_code}")
            return {}
        except Exception as e:
            self.logger.error(f"GET {endpoint} error: {e}")
            return {}


@dataclass
class UploadResult:
    """Result of a document upload operation."""

    success: bool
    document_id: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    skipped_duplicate: bool = False  # Skipped due to hash match (deduplication)
    metadata_pushed: bool = False  # Metadata successfully set via API


@dataclass
class DatasetInfo:
    """Information about a RAGFlow dataset."""

    id: str
    name: str
    document_count: int = 0
    chunk_count: int = 0
    status: str = "unknown"


class RAGFlowClient:
    """
    Client for interacting with the RAGFlow API.

    Provides methods for:
    - Creating datasets
    - Uploading documents (batch)
    - Triggering parsing
    - Monitoring parsing status
    - Listing available models (via session auth)

    All methods include retry logic with exponential backoff.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """
        Initialize the RAGFlow client.

        Args:
            api_url: RAGFlow API base URL (defaults to config)
            api_key: RAGFlow API key (defaults to config)
            username: RAGFlow username for session auth (defaults to config)
            password: RAGFlow password for session auth (defaults to config)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_url = (api_url or Config.RAGFLOW_API_URL).rstrip("/")
        self.api_key = api_key or Config.RAGFLOW_API_KEY
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_logger("ragflow")

        # Session auth credentials
        self._username = username or Config.RAGFLOW_USERNAME
        self._password = password or Config.RAGFLOW_PASSWORD
        self._session_client: Optional[RAGFlowSession] = None

        if not self.api_key:
            self.logger.warning("RAGFlow API key not configured")

    @property
    def session_configured(self) -> bool:
        """Check if session auth is configured."""
        return bool(self._username and self._password)

    def _get_session_client(self) -> Optional[RAGFlowSession]:
        """Get or create session client for admin APIs."""
        if not self.session_configured:
            return None

        if self._session_client is None:
            self._session_client = RAGFlowSession(
                api_url=self.api_url,
                username=self._username,
                password=self._password,
                timeout=self.timeout,
            )
        return self._session_client

    @property
    def headers(self) -> dict:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict:
        """
        Make an API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON as dictionary

        Raises:
            requests.RequestException: If request fails after retries
        """
        url = f"{self.api_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", self.headers)

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"{method} {url}")
                response = requests.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()

            except requests.RequestException as e:
                self.logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    self.logger.debug(f"Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    raise

    def test_connection(self) -> bool:
        """
        Test the connection to RAGFlow.

        Returns:
            True if connection is successful
        """
        try:
            # Try to list datasets as a connection test
            self._make_request("GET", "/api/v1/datasets")
            self.logger.info("RAGFlow connection successful")
            return True
        except Exception as e:
            self.logger.error(f"RAGFlow connection failed: {e}")
            return False

    def list_embedding_models(self) -> list[dict]:
        """
        List available embedding models from RAGFlow.

        Requires session auth (username/password).

        Returns:
            List of model dictionaries with 'llm_name' and optionally other fields
        """
        session = self._get_session_client()
        if not session:
            self.logger.warning("Session auth not configured, cannot list models")
            return []

        try:
            # RAGFlow uses /v1/ prefix for internal APIs (not /api/v1/)
            response = session.get("/v1/llm/list", params={"model_type": "embedding"})

            if response.get("code") == 0:
                # Response data is grouped by provider: {"Builtin": [...], "Voyage AI": [...]}
                # Flatten into a single list of models
                data = response.get("data", {})
                models = []
                if isinstance(data, dict):
                    for provider, provider_models in data.items():
                        if isinstance(provider_models, list):
                            for model in provider_models:
                                # Only include models that are configured/available
                                if model.get("available", False):
                                    model["provider"] = provider
                                    models.append(model)
                elif isinstance(data, list):
                    models = data

                self.logger.debug(f"Found {len(models)} embedding models")
                return models

            self.logger.warning(f"Failed to list models: {response}")
            return []

        except Exception as e:
            self.logger.error(f"Error listing embedding models: {e}")
            return []

    def list_chunk_methods(self) -> list[str]:
        """
        Return available chunk methods.

        These are validated by RAGFlow's API - invalid values will be rejected.

        Returns:
            List of chunk method names
        """
        return CHUNK_METHODS.copy()

    def list_pdf_parsers(self) -> list[str]:
        """
        Return available PDF parsers for layout_recognize in parser_config.

        Note: MinerU and Docling require server-side configuration.
        If not configured, parsing will fail when documents are processed.

        Returns:
            List of parser names
        """
        return PDF_PARSERS.copy()

    def list_ingestion_pipelines(self) -> list[dict]:
        """
        List available custom ingestion pipelines (dataflow canvases).

        Requires session auth (username/password).

        Returns:
            List of {"id": str, "title": str, "description": str}
        """
        session = self._get_session_client()
        if not session:
            self.logger.debug("Session auth not configured, cannot list pipelines")
            return []

        try:
            result = session.get("/v1/canvas/list")
            if result.get("code") == 0:
                canvases = result.get("data", {}).get("canvas", [])
                pipelines = [
                    {
                        "id": c.get("id"),
                        "title": c.get("title"),
                        "description": c.get("description") or "",
                    }
                    for c in canvases
                    if c.get("canvas_category") == "dataflow_canvas"
                ]
                self.logger.debug(f"Found {len(pipelines)} ingestion pipelines")
                return pipelines

            self.logger.warning(f"Failed to list pipelines: {result}")
            return []

        except Exception as e:
            self.logger.error(f"Error listing ingestion pipelines: {e}")
            return []

    def list_llm_factories(self) -> list[dict]:
        """
        List available LLM providers/factories.

        Requires session auth (username/password).

        Returns:
            List of factory dictionaries
        """
        session = self._get_session_client()
        if not session:
            self.logger.warning("Session auth not configured, cannot list factories")
            return []

        try:
            # RAGFlow uses /v1/ prefix for internal APIs (not /api/v1/)
            response = session.get("/v1/llm/factories")

            if response.get("code") == 0:
                factories = response.get("data", [])
                self.logger.debug(f"Found {len(factories)} LLM factories")
                return factories

            self.logger.warning(f"Failed to list factories: {response}")
            return []

        except Exception as e:
            self.logger.error(f"Error listing LLM factories: {e}")
            return []

    def create_dataset(
        self,
        name: str,
        description: str = "",
        embedding_model: Optional[str] = None,
        chunk_method: str = "naive",
        parser_config: Optional[dict] = None,
        pipeline_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a new dataset in RAGFlow.

        Args:
            name: Dataset name
            description: Dataset description
            embedding_model: Embedding model (format: "model_name@Provider", None for default)
            chunk_method: Chunking method for built-in ingestion
            parser_config: Parser configuration (e.g., {"layout_recognize": "DeepDOC"})
            pipeline_id: Custom pipeline ID for custom ingestion mode

        Returns:
            Dataset ID if successful, None otherwise
        """
        try:
            payload = {
                "name": name,
                "description": description,
                "chunk_method": chunk_method,
            }

            # Only include optional fields if set
            if embedding_model:
                payload["embedding_model"] = embedding_model
            if parser_config:
                payload["parser_config"] = parser_config
            if pipeline_id:
                payload["pipeline_id"] = pipeline_id

            response = self._make_request(
                "POST",
                "/api/v1/datasets",
                json=payload,
            )

            dataset_id = response.get("data", {}).get("id")
            if dataset_id:
                self.logger.info(f"Created dataset: {name} (ID: {dataset_id})")
                return dataset_id

            self.logger.error(f"Failed to create dataset: {response}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to create dataset: {e}")
            return None

    def list_datasets(self) -> list[DatasetInfo]:
        """
        List all datasets.

        Returns:
            List of DatasetInfo objects
        """
        try:
            response = self._make_request("GET", "/api/v1/datasets")
            datasets = response.get("data", [])

            return [
                DatasetInfo(
                    id=ds.get("id", ""),
                    name=ds.get("name", ""),
                    document_count=ds.get("document_count", 0),
                    chunk_count=ds.get("chunk_count", 0),
                    status=ds.get("status", "unknown"),
                )
                for ds in datasets
            ]

        except Exception as e:
            self.logger.error(f"Failed to list datasets: {e}")
            return []

    def find_dataset_by_name(self, name: str) -> Optional[str]:
        """
        Find a dataset by exact name match.

        Args:
            name: Exact dataset name to search for

        Returns:
            Dataset ID if found, None otherwise
        """
        try:
            response = self._make_request(
                "GET",
                "/api/v1/datasets",
                params={"name": name, "page_size": 1},
            )
            datasets = response.get("data", [])

            # Verify exact match (RAGFlow may do partial matching)
            for ds in datasets:
                if ds.get("name") == name:
                    dataset_id = ds.get("id")
                    self.logger.info(f"Found existing dataset: {name} (ID: {dataset_id})")
                    return dataset_id

            self.logger.debug(f"No dataset found with name: {name}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to find dataset by name '{name}': {e}")
            return None

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """
        Get information about a specific dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            DatasetInfo if found, None otherwise
        """
        try:
            response = self._make_request("GET", f"/api/v1/datasets/{dataset_id}")
            ds = response.get("data", {})

            return DatasetInfo(
                id=ds.get("id", ""),
                name=ds.get("name", ""),
                document_count=ds.get("document_count", 0),
                chunk_count=ds.get("chunk_count", 0),
                status=ds.get("status", "unknown"),
            )

        except Exception as e:
            self.logger.error(f"Failed to get dataset {dataset_id}: {e}")
            return None

    def upload_document(
        self,
        dataset_id: str,
        file_path: Path,
    ) -> UploadResult:
        """
        Upload a single document to a dataset.

        Args:
            dataset_id: Target dataset ID
            file_path: Path to the file to upload

        Returns:
            UploadResult with success status and document ID
        """
        try:
            if not file_path.exists():
                return UploadResult(
                    success=False,
                    filename=file_path.name,
                    error=f"File not found: {file_path}",
                )

            # Upload using multipart form data
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                headers = {"Authorization": f"Bearer {self.api_key}"}

                response = requests.post(
                    f"{self.api_url}/api/v1/datasets/{dataset_id}/documents",
                    files=files,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

            # Handle response - data can be a dict or list
            response_data = data.get("data", {})
            doc_id = None
            if isinstance(response_data, dict):
                doc_id = response_data.get("id")
            elif isinstance(response_data, list) and len(response_data) > 0:
                # Sometimes returns a list of uploaded documents
                doc_id = response_data[0].get("id") if isinstance(response_data[0], dict) else None

            if doc_id:
                self.logger.info(f"Uploaded: {file_path.name} (ID: {doc_id})")
                return UploadResult(
                    success=True,
                    document_id=doc_id,
                    filename=file_path.name,
                )

            # Check if code=0 indicates success even without doc_id
            if data.get("code") == 0:
                self.logger.info(f"Uploaded: {file_path.name}")
                return UploadResult(
                    success=True,
                    filename=file_path.name,
                )

            return UploadResult(
                success=False,
                filename=file_path.name,
                error=data.get("message", "No document ID in response"),
            )

        except Exception as e:
            self.logger.error(f"Failed to upload {file_path.name}: {e}")
            return UploadResult(
                success=False,
                filename=file_path.name,
                error=str(e),
            )

    def upload_documents(
        self,
        dataset_id: str,
        file_paths: list[Path],
    ) -> list[UploadResult]:
        """
        Upload multiple documents to a dataset.

        Args:
            dataset_id: Target dataset ID
            file_paths: List of file paths to upload

        Returns:
            List of UploadResult for each file
        """
        results = []
        for file_path in file_paths:
            result = self.upload_document(dataset_id, file_path)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        self.logger.info(f"Uploaded {successful}/{len(file_paths)} documents")

        return results

    def trigger_parsing(
        self,
        dataset_id: str,
        document_ids: Optional[list[str]] = None,
    ) -> bool:
        """
        Trigger parsing for documents in a dataset.

        Args:
            dataset_id: Dataset ID
            document_ids: Specific document IDs to parse (None for all)

        Returns:
            True if parsing was triggered successfully
        """
        try:
            payload = {}
            if document_ids:
                payload["document_ids"] = document_ids

            self._make_request(
                "POST",
                f"/api/v1/datasets/{dataset_id}/chunks",
                json=payload,
            )

            self.logger.info(f"Parsing triggered for dataset {dataset_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to trigger parsing: {e}")
            return False

    def get_parsing_status(
        self,
        dataset_id: str,
    ) -> dict[str, Any]:
        """
        Get parsing status for a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            Status information dictionary
        """
        try:
            response = self._make_request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents",
            )

            documents = response.get("data", [])
            status = {
                "total": len(documents),
                "parsed": 0,
                "parsing": 0,
                "failed": 0,
                "pending": 0,
            }

            for doc in documents:
                doc_status = doc.get("status", "").lower()
                if doc_status == "parsed":
                    status["parsed"] += 1
                elif doc_status in ("parsing", "processing"):
                    status["parsing"] += 1
                elif doc_status == "failed":
                    status["failed"] += 1
                else:
                    status["pending"] += 1

            return status

        except Exception as e:
            self.logger.error(f"Failed to get parsing status: {e}")
            return {}

    def wait_for_parsing(
        self,
        dataset_id: str,
        poll_interval: int = 5,
        timeout: int = 300,
    ) -> bool:
        """
        Wait for all documents in a dataset to be parsed.

        Args:
            dataset_id: Dataset ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            True if all documents parsed successfully
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_parsing_status(dataset_id)

            if not status:
                self.logger.warning("Could not get parsing status")
                time.sleep(poll_interval)
                continue

            self.logger.info(
                f"Parsing status: {status['parsed']}/{status['total']} parsed, "
                f"{status['parsing']} in progress, {status['failed']} failed"
            )

            # Check if all documents are processed
            if status["parsing"] == 0 and status["pending"] == 0:
                if status["failed"] > 0:
                    self.logger.warning(
                        f"Parsing completed with {status['failed']} failures"
                    )
                else:
                    self.logger.info("All documents parsed successfully")
                return status["failed"] == 0

            time.sleep(poll_interval)

        self.logger.error(f"Parsing timed out after {timeout}s")
        return False

    def check_document_exists(
        self,
        dataset_id: str,
        file_hash: str,
    ) -> Optional[str]:
        """
        Check if a document with the given hash already exists in the dataset.

        Args:
            dataset_id: Dataset ID
            file_hash: SHA256 hash of the file

        Returns:
            Document ID if exists, None otherwise
        """
        try:
            response = self._make_request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents",
            )

            documents = response.get("data", [])
            for doc in documents:
                if doc.get("hash") == file_hash or doc.get("file_hash") == file_hash:
                    doc_id = doc.get("id")
                    self.logger.info(f"Found existing document with hash {file_hash[:8]}...")
                    return doc_id

            return None

        except Exception as e:
            self.logger.error(f"Failed to check document existence: {e}")
            return None

    def get_document_status(
        self,
        dataset_id: str,
        document_id: str,
    ) -> Optional[str]:
        """
        Get the status of a specific document.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID

        Returns:
            Document status string or None if request fails
        """
        try:
            response = self._make_request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
            )

            return response.get("data", {}).get("status")

        except Exception as e:
            self.logger.debug(f"Failed to get document status: {e}")
            return None

    def wait_for_document_ready(
        self,
        dataset_id: str,
        document_id: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Wait for a document to be ready (registered/parsing state).

        Polls the document status API until the document reaches a ready state
        or timeout is reached.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between status checks

        Returns:
            True if document is ready, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_document_status(dataset_id, document_id)

            if status in ("registered", "parsing", "parsed"):
                self.logger.debug(f"Document {document_id[:8]}... ready (status: {status})")
                return True

            if status == "failed":
                self.logger.warning(f"Document {document_id[:8]}... failed parsing")
                return False

            time.sleep(poll_interval)

        self.logger.warning(f"Document {document_id[:8]}... timeout waiting for ready state")
        return False

    def set_document_metadata(
        self,
        dataset_id: str,
        document_id: str,
        metadata: dict,
        max_retries: int = 3,
    ) -> bool:
        """
        Set metadata for a document via RAGFlow API.

        Args:
            dataset_id: Dataset ID
            document_id: Document ID
            metadata: Metadata dictionary (flat, string/number values only)
            max_retries: Maximum retry attempts

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                response = self._make_request(
                    "PUT",
                    f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
                    json={"meta_fields": metadata},
                )

                if response.get("code") == 0:
                    self.logger.debug(f"Metadata set for document {document_id[:8]}...")
                    return True

                self.logger.warning(
                    f"Metadata set failed (attempt {attempt + 1}): {response.get('message')}"
                )

            except Exception as e:
                self.logger.warning(f"Metadata set attempt {attempt + 1} failed: {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff

        return False

    def upload_documents_with_metadata(
        self,
        dataset_id: str,
        docs: list[dict],
        check_duplicates: bool = True,
        wait_timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> list[UploadResult]:
        """
        Upload documents with metadata to RAGFlow.

        This method handles the complete workflow:
        1. Check for duplicates by hash (optional)
        2. Upload new documents
        3. Wait for documents to be registered
        4. Set metadata for each document

        Args:
            dataset_id: Target dataset ID
            docs: List of dicts with 'filepath' (Path) and 'metadata' (DocumentMetadata) keys
            check_duplicates: Enable hash-based deduplication
            wait_timeout: Max wait time per document for registration (seconds)
            poll_interval: Poll interval for document status (seconds)

        Returns:
            List of UploadResult with metadata_pushed and skipped_duplicate flags
        """
        from pathlib import Path
        from app.scrapers.base_scraper import DocumentMetadata
        from app.services.ragflow_metadata import prepare_metadata_for_ragflow

        results = []

        for doc_info in docs:
            filepath = doc_info["filepath"]
            metadata = doc_info.get("metadata")

            # Phase 1: Check for duplicates
            if check_duplicates and metadata and metadata.hash:
                existing_id = self.check_document_exists(dataset_id, metadata.hash)
                if existing_id:
                    self.logger.info(f"Skipping duplicate: {filepath.name}")
                    results.append(
                        UploadResult(
                            success=True,
                            document_id=existing_id,
                            filename=filepath.name,
                            skipped_duplicate=True,
                            metadata_pushed=False,
                        )
                    )
                    continue

            # Phase 2: Upload document
            upload_result = self.upload_document(dataset_id, filepath)

            if not upload_result.success or not upload_result.document_id:
                # Upload failed - return as-is
                results.append(upload_result)
                continue

            # Phase 3: Wait for document to be registered
            if metadata:
                ready = self.wait_for_document_ready(
                    dataset_id,
                    upload_result.document_id,
                    timeout=wait_timeout,
                    poll_interval=poll_interval,
                )

                if not ready:
                    self.logger.warning(
                        f"Document {filepath.name} not ready, will attempt metadata push anyway"
                    )

                # Phase 4: Set metadata
                ragflow_metadata = prepare_metadata_for_ragflow(metadata.to_ragflow_metadata())

                metadata_success = self.set_document_metadata(
                    dataset_id,
                    upload_result.document_id,
                    ragflow_metadata,
                )

                if metadata_success:
                    self.logger.info(f"✓ {filepath.name}: uploaded with metadata")
                else:
                    self.logger.warning(f"✓ {filepath.name}: uploaded (metadata push failed)")

                upload_result.metadata_pushed = metadata_success

            results.append(upload_result)

        # Summary
        uploaded = sum(1 for r in results if r.success and not r.skipped_duplicate)
        skipped = sum(1 for r in results if r.skipped_duplicate)
        with_metadata = sum(1 for r in results if r.metadata_pushed)

        self.logger.info(
            f"Upload complete: {uploaded} uploaded, {skipped} skipped (duplicates), "
            f"{with_metadata} with metadata"
        )

        return results
