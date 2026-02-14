"""
Client for interacting with Paperless-ngx API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import requests
from requests.adapters import HTTPAdapter
import threading
import time
import uuid
from urllib3.util.retry import Retry

from app.config import Config
from app.utils import get_logger

# Maps metadata dict keys to (Paperless custom field name, Paperless data type)
CUSTOM_FIELD_MAPPING: dict[str, tuple[str, str]] = {
    "url": ("Original URL", "url"),
    "source_page": ("Source Page", "url"),
    "scraped_at": ("Scraped Date", "string"),
    "scraper_name": ("Scraper Name", "string"),
    "organization": ("Organization", "string"),
    "author": ("Author", "string"),
    "description": ("Description", "string"),
    "language": ("Language", "string"),
    "llm_summary": ("LLM Summary", "string"),
    "llm_keywords": ("LLM Keywords", "string"),
    "llm_entities": ("LLM Entities", "string"),
    "llm_topics": ("LLM Topics", "string"),
}


def flatten_metadata_extras(metadata: dict[str, Any]) -> dict[str, Any]:
    """Flatten the 'extra' dict into top-level metadata for custom field lookup.

    LLM enrichment fields are stored in metadata["extra"]["llm_summary"] etc.
    This flattens them to the top level so CUSTOM_FIELD_MAPPING can find them.
    Does not overwrite existing top-level keys.
    """
    flattened = dict(metadata)
    extra = metadata.get("extra", {})
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in CUSTOM_FIELD_MAPPING and key not in flattened:
                flattened[key] = value
    return flattened


def build_paperless_native_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build Paperless-ngx native field values from document metadata.

    Returns dict with keys: title, created, correspondent, document_type, tags.
    Correspondent uses author with organization as fallback.
    """
    return {
        "title": metadata.get("title"),
        "created": metadata.get("publication_date"),
        "correspondent": metadata.get("author") or metadata.get("organization"),
        "document_type": metadata.get("document_type"),
        "tags": metadata.get("tags", []),
    }


class PaperlessClient:
    """
    Client for interacting with Paperless-ngx.

    Handles:
    - Document uploading
    - Metadata mapping
    - Existence checks
    """

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None):
        """
        Initialize Paperless client.

        Args:
            url: Base URL of Paperless instance (e.g. http://localhost:8000)
            token: API Token
        """
        base_url = url or Config.PAPERLESS_API_URL
        self.url = base_url.rstrip("/") if base_url else None
        self.token = token or Config.PAPERLESS_API_TOKEN
        self.logger = get_logger("services.paperless")

        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Token {self.token}"})

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Caches for name-to-ID lookups (populated on first use)
        self._correspondent_cache: dict[str, int] = {}
        self._correspondent_cache_populated = False
        self._correspondent_lock = threading.RLock()
        self._tag_cache: dict[str, int] = {}
        self._tag_cache_populated = False
        self._tag_lock = threading.RLock()
        self._document_type_cache: dict[str, int] = {}
        self._document_type_cache_populated = False
        self._document_type_lock = threading.RLock()
        self._custom_field_cache: dict[str, int] = {}
        self._custom_field_cache_populated = False
        self._custom_field_lock = threading.RLock()

    @property
    def is_configured(self) -> bool:
        """Check if client has necessary credentials."""
        return bool(self.url and self.token)

    def _fetch_correspondents(self) -> dict[str, int]:
        """
        Fetch all correspondents from Paperless API with pagination.

        Returns:
            Dict mapping correspondent names to IDs
        """
        if not self.is_configured:
            return {}

        correspondents: dict[str, int] = {}
        next_url: Optional[str] = f"{self.url}/api/correspondents/"

        while next_url:
            response = self.session.get(next_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                name = item.get("name")
                corr_id = item.get("id")
                if name and corr_id:
                    correspondents[name] = corr_id

            next_url = data.get("next")

        return correspondents

    def get_or_create_correspondent(self, name: str) -> Optional[int]:
        """
        Get correspondent ID by name, creating if not exists.

        Args:
            name: Correspondent name

        Returns:
            Correspondent ID, or None if lookup/creation failed
        """
        if not self.is_configured or not name:
            return None

        with self._correspondent_lock:
            # Check cache first (locked)
            if name in self._correspondent_cache:
                return self._correspondent_cache[name]

            # Populate cache if not yet fetched
            if not self._correspondent_cache_populated:
                try:
                    fetched = self._fetch_correspondents()
                    self._correspondent_cache = fetched
                    self._correspondent_cache_populated = True
                except Exception as e:
                    self.logger.error(f"Failed to populate correspondent cache: {e}")

            # Check again after potential fetch
            if name in self._correspondent_cache:
                return self._correspondent_cache[name]

            # Create new correspondent
            try:
                response = self.session.post(
                    f"{self.url}/api/correspondents/",
                    json={"name": name, "owner": None},
                    timeout=30,
                )
                if response.status_code == 409:
                    self.logger.debug(
                        f"Correspondent '{name}' already exists (409 Conflict), re-fetching..."
                    )
                    # Re-fetch under lock to resolve race
                    self._correspondent_cache = self._fetch_correspondents()
                    return self._correspondent_cache.get(name)

                response.raise_for_status()
                data = response.json()
                corr_id = data.get("id")

                if corr_id:
                    self._correspondent_cache[name] = corr_id
                    self.logger.info(
                        f"Created correspondent '{name}' with ID {corr_id}"
                    )
                    return corr_id

            except Exception as e:
                self.logger.error(f"Failed to create correspondent '{name}': {e}")

        return None

    def _fetch_document_types(self) -> dict[str, int]:
        """
        Fetch all document types from Paperless API with pagination.

        Returns:
            Dict mapping document type names to IDs
        """
        if not self.is_configured:
            return {}

        doc_types: dict[str, int] = {}
        next_url: Optional[str] = f"{self.url}/api/document_types/"

        while next_url:
            response = self.session.get(next_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                name = item.get("name")
                dt_id = item.get("id")
                if name and dt_id:
                    doc_types[name] = dt_id

            next_url = data.get("next")

        return doc_types

    def get_or_create_document_type(self, name: str) -> Optional[int]:
        """
        Get document type ID by name, creating if not exists.

        Args:
            name: Document type name (e.g. "Article", "Report")

        Returns:
            Document type ID, or None if lookup/creation failed
        """
        if not self.is_configured or not name:
            return None

        with self._document_type_lock:
            # Check cache first
            if name in self._document_type_cache:
                return self._document_type_cache[name]

            # Populate cache if not yet fetched
            if not self._document_type_cache_populated:
                try:
                    fetched = self._fetch_document_types()
                    self._document_type_cache = fetched
                    self._document_type_cache_populated = True
                except Exception as e:
                    self.logger.error(f"Failed to populate document type cache: {e}")

            # Check again after potential fetch
            if name in self._document_type_cache:
                return self._document_type_cache[name]

            # Create new document type
            try:
                response = self.session.post(
                    f"{self.url}/api/document_types/",
                    json={"name": name, "owner": None},
                    timeout=30,
                )
                if response.status_code == 409:
                    self.logger.debug(
                        f"Document type '{name}' already exists (409 Conflict), re-fetching..."
                    )
                    self._document_type_cache = self._fetch_document_types()
                    return self._document_type_cache.get(name)

                response.raise_for_status()
                data = response.json()
                dt_id = data.get("id")

                if dt_id:
                    self._document_type_cache[name] = dt_id
                    self.logger.info(
                        f"Created document type '{name}' with ID {dt_id}"
                    )
                    return dt_id

            except Exception as e:
                self.logger.error(f"Failed to create document type '{name}': {e}")

        return None

    def _fetch_tags(self) -> dict[str, int]:
        """
        Fetch all tags from Paperless API with pagination.

        Returns:
            Dict mapping tag names to IDs
        """
        if not self.is_configured:
            return {}

        tags: dict[str, int] = {}
        next_url: Optional[str] = f"{self.url}/api/tags/"

        while next_url:
            response = self.session.get(next_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                name = item.get("name")
                tag_id = item.get("id")
                if name and tag_id:
                    tags[name] = tag_id

            next_url = data.get("next")

        return tags

    def get_or_create_tags(self, names: list[str]) -> list[int]:
        """
        Get tag IDs by names, creating any that don't exist.

        Args:
            names: List of tag names

        Returns:
            List of tag IDs (preserving order, skipping failures)
        """
        if not self.is_configured or not names:
            return []

        # Populate cache if not yet fetched
        if not self._tag_cache_populated:
            try:
                fetched = self._fetch_tags()
                self._tag_cache = fetched
                self._tag_cache_populated = True
            except Exception as e:
                self.logger.error(f"Failed to populate tag cache: {e}")
                # Leave flag False for retries

        result_ids: list[int] = []

        for name in names:
            if not name:
                continue

            # Check cache
            if name in self._tag_cache:
                result_ids.append(self._tag_cache[name])
                continue

            # Create new tag
            try:
                response = self.session.post(
                    f"{self.url}/api/tags/",
                    json={"name": name, "owner": None},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                tag_id = data.get("id")

                if tag_id:
                    self._tag_cache[name] = tag_id
                    self.logger.info(f"Created tag '{name}' with ID {tag_id}")
                    result_ids.append(tag_id)

            except Exception as e:
                self.logger.warning(f"Failed to create tag '{name}': {e}")

        return result_ids

    def _fetch_custom_fields(self) -> dict[str, int]:
        """
        Fetch all custom fields from Paperless API with pagination.

        Returns:
            Dict mapping custom field names to IDs
        """
        if not self.is_configured:
            return {}

        fields: dict[str, int] = {}
        next_url: Optional[str] = f"{self.url}/api/custom_fields/"

        while next_url:
            response = self.session.get(next_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                name = item.get("name")
                field_id = item.get("id")
                if name and field_id:
                    fields[name] = field_id

            next_url = data.get("next")

        return fields

    def get_or_create_custom_field(self, name: str, data_type: str) -> Optional[int]:
        """
        Get custom field ID by name, creating if not exists.

        Args:
            name: Custom field name
            data_type: Paperless custom field data type (e.g. "url", "string", "integer")

        Returns:
            Custom field ID, or None if lookup/creation failed
        """
        if not self.is_configured or not name:
            return None

        with self._custom_field_lock:
            # Check cache first
            if name in self._custom_field_cache:
                return self._custom_field_cache[name]

            # Populate cache if not yet fetched
            if not self._custom_field_cache_populated:
                try:
                    fetched = self._fetch_custom_fields()
                    self._custom_field_cache = fetched
                    self._custom_field_cache_populated = True
                except Exception as e:
                    self.logger.error(f"Failed to populate custom field cache: {e}")

            # Check again after potential fetch
            if name in self._custom_field_cache:
                return self._custom_field_cache[name]

            # Create new custom field
            try:
                response = self.session.post(
                    f"{self.url}/api/custom_fields/",
                    json={"name": name, "data_type": data_type, "owner": None},
                    timeout=30,
                )
                if response.status_code == 409:
                    self.logger.debug(
                        f"Custom field '{name}' already exists (409 Conflict), re-fetching..."
                    )
                    self._custom_field_cache = self._fetch_custom_fields()
                    return self._custom_field_cache.get(name)

                response.raise_for_status()
                data = response.json()
                field_id = data.get("id")

                if field_id:
                    self._custom_field_cache[name] = field_id
                    self.logger.info(
                        f"Created custom field '{name}' (type={data_type}) with ID {field_id}"
                    )
                    return field_id

            except Exception as e:
                self.logger.error(f"Failed to create custom field '{name}': {e}")

        return None

    def set_custom_fields(self, document_id: int, metadata: dict) -> bool:
        """
        Set custom field values on a Paperless document.

        Maps metadata keys via CUSTOM_FIELD_MAPPING to Paperless custom field IDs,
        then PATCHes the document.

        Args:
            document_id: Real Paperless document ID (integer)
            metadata: Metadata dict with keys matching CUSTOM_FIELD_MAPPING

        Returns:
            True if successful, False on failure (non-fatal)
        """
        if not self.is_configured or not metadata:
            return not metadata  # True if empty/None, False if has data but not configured

        # Flatten extra dict into top level so LLM fields are discoverable
        flattened = flatten_metadata_extras(metadata)

        custom_fields_payload: list[dict] = []

        for meta_key, (field_name, data_type) in CUSTOM_FIELD_MAPPING.items():
            value = flattened.get(meta_key)
            if value is None or value == "":
                continue

            field_id = self.get_or_create_custom_field(field_name, data_type)
            if field_id is None:
                self.logger.warning(
                    f"Could not resolve custom field '{field_name}', skipping"
                )
                continue

            # Coerce integer types
            if data_type == "integer":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    self.logger.warning(
                        f"Cannot convert '{value}' to integer for field '{field_name}', skipping"
                    )
                    continue

            # Paperless-ngx "string" fields have a 128-character limit
            if data_type == "string" and isinstance(value, str) and len(value) > 128:
                value = value[:125] + "..."

            custom_fields_payload.append({"field": field_id, "value": value})

        if not custom_fields_payload:
            self.logger.debug("No custom fields to set")
            return True

        try:
            response = self.session.patch(
                f"{self.url}/api/documents/{document_id}/",
                json={"custom_fields": custom_fields_payload},
                timeout=30,
            )
            response.raise_for_status()
            self.logger.info(
                f"Set {len(custom_fields_payload)} custom fields on document {document_id}"
            )
            return True
        except requests.exceptions.HTTPError as e:
            body = ""
            if e.response is not None:
                try:
                    body = f" Response: {e.response.text[:500]}"
                except Exception:
                    pass
            self.logger.error(
                f"Failed to set custom fields on document {document_id}: {e}{body}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Failed to set custom fields on document {document_id}: {e}"
            )
            return False

    def _resolve_tag_ids(self, tags: list[Union[str, int]]) -> list[int]:
        """Convert a mixed string/int tag list to integer IDs via cache lookup."""
        tag_ids: list[int] = []
        string_tags: list[str] = []

        for t in tags:
            if isinstance(t, int):
                tag_ids.append(t)
            elif isinstance(t, str) and t.isdigit():
                tag_ids.append(int(t))
            elif isinstance(t, str):
                string_tags.append(t)

        if string_tags:
            resolved_ids = self.get_or_create_tags(string_tags)
            tag_ids.extend(resolved_ids)

        return tag_ids

    def _extract_task_id_from_response(self, response: requests.Response) -> Optional[str]:
        """Extract raw task ID string from a Paperless upload response.

        Handles JSON (dict, list) and plain-text response formats.
        """
        raw_text = response.text.strip()

        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("application/json") or raw_text.startswith(("{", "[")):
            try:
                response_data = response.json()
                if isinstance(response_data, dict):
                    return response_data.get("task_id")
                elif (
                    isinstance(response_data, list)
                    and response_data
                    and isinstance(response_data[0], dict)
                ):
                    return response_data[0].get("task_id")
                else:
                    return response_data if isinstance(response_data, str) else None
            except Exception:
                return raw_text.strip("'\"")
        else:
            return raw_text.strip("'\"")

    def _validate_task_id(self, raw: Any) -> Optional[str]:
        """Validate and normalize a raw task ID to a UUID string."""
        if not raw:
            self.logger.error("No task_id received from Paperless")
            return None
        try:
            uuid.UUID(str(raw))
            return str(raw)
        except (ValueError, TypeError, AttributeError):
            self.logger.error(f"Invalid task_id received from Paperless: {raw}")
            return None

    def post_document(
        self,
        file_path: Union[str, Path],
        title: str,
        created: Optional[datetime] = None,
        correspondent: Optional[Union[str, int]] = None,
        document_type: Optional[Union[str, int]] = None,
        tags: Optional[list[Union[str, int]]] = None,
    ) -> Optional[str]:
        """
        Upload a document to Paperless.

        Args:
            file_path: Path to file to upload
            title: Document title
            created: Document creation date
            correspondent: Sender/Author (name or numeric ID)
            document_type: Document type (name or numeric ID)
            tags: List of tags

        Returns:
            Task ID if successful, None otherwise
        """
        if not self.is_configured:
            self.logger.warning("Paperless not configured, skipping upload")
            return None

        path = Path(file_path)
        if not path.exists():
            self.logger.error(f"File not found: {path}")
            return None

        endpoint = f"{self.url}/api/documents/post_document/"

        # Prepare metadata
        data: dict[str, Any] = {"title": title}

        if created:
            data["created"] = created.isoformat()

        if correspondent:
            if isinstance(correspondent, int):
                data["correspondent"] = correspondent
            elif isinstance(correspondent, str) and correspondent.isdigit():
                data["correspondent"] = int(correspondent)
            else:
                corr_id = self.get_or_create_correspondent(correspondent)
                if corr_id:
                    data["correspondent"] = corr_id
                else:
                    self.logger.warning(
                        f"Could not resolve correspondent '{correspondent}', skipping"
                    )

        if document_type:
            if isinstance(document_type, int):
                data["document_type"] = document_type
            elif isinstance(document_type, str) and document_type.isdigit():
                data["document_type"] = int(document_type)
            else:
                dt_id = self.get_or_create_document_type(document_type)
                if dt_id:
                    data["document_type"] = dt_id
                else:
                    self.logger.warning(
                        f"Could not resolve document type '{document_type}', skipping"
                    )

        if tags:
            tag_ids = self._resolve_tag_ids(tags)
            if tag_ids:
                data["tags"] = tag_ids

        self.logger.info(f"Uploading to Paperless: {title}")

        try:
            with open(path, "rb") as f:
                files = {"document": (path.name, f)}
                response = self.session.post(
                    endpoint, data=data, files=files, timeout=60
                )

            response.raise_for_status()

            raw_task_id = self._extract_task_id_from_response(response)
            task_id = self._validate_task_id(raw_task_id)
            if not task_id:
                return None

            self.logger.info(f"Upload successful. Task ID: {task_id}")
            return task_id

        except requests.HTTPError as e:
            error_text = e.response.text if e.response is not None else str(e)
            self.logger.error(f"Paperless upload HTTP error: {error_text}")
            return None
        except Exception as e:
            self.logger.error(f"Paperless upload failed: {e}")
            return None

    def check_alive(self) -> bool:
        """Check if Paperless is reachable."""
        if not self.is_configured:
            return False
        try:
            res = self.session.get(f"{self.url}/api/", timeout=5)
            return res.status_code == 200
        except Exception:
            return False

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """
        Query task status from Paperless API.

        Args:
            task_id: Task ID returned from post_document()

        Returns:
            Task status dict
            None if task not found or API error
        """
        if not self.is_configured:
            return None

        # Validate task_id is a proper UUID
        try:
            uuid.UUID(task_id)
        except (ValueError, TypeError, AttributeError):
            self.logger.warning(f"Invalid task_id format: {task_id}")
            return None

        # Search the task list endpoint and filter by task_id.
        # Paperless-ngx does not expose /api/tasks/{id}/ — only the list.
        next_url: Optional[str] = f"{self.url}/api/tasks/"
        try:
            while next_url:
                response = self.session.get(next_url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Handle both flat list and paginated dict responses
                if isinstance(data, list):
                    tasks = data
                    next_url = None
                elif isinstance(data, dict):
                    tasks = data.get("results", [])
                    next_url = data.get("next")
                else:
                    self.logger.debug("Unexpected response format for tasks")
                    return None

                for task in tasks:
                    if task.get("task_id") == task_id:
                        return task

            self.logger.debug(f"Task {task_id} not found in task list")
            return None

        except Exception as e:
            self.logger.error(f"Failed to query task status: {e}")
            return None

    def verify_document_exists(
        self, task_id: str, timeout: int = 60, poll_interval: int = 2
    ) -> Optional[str]:
        """
        Poll task status until document is verified (Sonarr-style).

        Args:
            task_id: Task ID from post_document()
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Document ID string if verified successfully, None otherwise
        """

        if not self.is_configured:
            return None

        start_time = time.time()
        self.logger.info(f"Verifying document for task {task_id}...")

        while time.time() - start_time < timeout:
            task_status = self.get_task_status(task_id)

            if not task_status:
                self.logger.warning(f"Task {task_id} not found, retrying...")
                time.sleep(poll_interval)
                continue

            status = task_status.get("status")
            document_id = task_status.get("related_document")

            if status == "SUCCESS" and document_id:
                self.logger.info(
                    f"Document verified: task={task_id}, document_id={document_id}"
                )
                return str(document_id)

            if status == "SUCCESS" and not document_id:
                self.logger.warning(
                    f"Task {task_id} marked SUCCESS but no related_document found. "
                    f"Status: {status}"
                )
                return None

            if status == "FAILURE":
                self.logger.error(f"Task {task_id} failed: {task_status}")
                return None

            # Status is PENDING or STARTED, keep polling
            self.logger.debug(f"Task {task_id} status: {status}, waiting...")
            time.sleep(poll_interval)

        self.logger.warning(
            f"Document verification timed out after {timeout}s for task {task_id}"
        )
        return None

    def get_documents(
        self,
        filters: Optional[dict[str, Any]] = None,
        page_size: int = 100,
    ) -> list[dict]:
        """
        Fetch documents from Paperless API with pagination.

        Args:
            filters: Optional query params (e.g. {"correspondent__id": 5})
            page_size: Number of results per page

        Returns:
            List of document dicts (includes custom_fields array)
        """
        if not self.is_configured:
            return []

        documents: list[dict] = []
        params: dict[str, Any] = {"page_size": page_size}
        if filters:
            params.update(filters)

        next_url: Optional[str] = f"{self.url}/api/documents/"

        try:
            while next_url:
                response = self.session.get(next_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    documents.append(item)

                next_url = data.get("next")
                # After first request, params are embedded in next_url
                params = {}

            return documents
        except Exception as e:
            self.logger.error(f"Failed to fetch documents: {e}")
            return documents  # Return partial results

    def download_document(self, document_id: int) -> Optional[bytes]:
        """
        Download the original file for a document.

        Args:
            document_id: Paperless document ID

        Returns:
            Raw file bytes, or None on failure
        """
        if not self.is_configured:
            return None

        try:
            response = self.session.get(
                f"{self.url}/api/documents/{document_id}/download/",
                timeout=60,
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            self.logger.error(f"Failed to download document {document_id}: {e}")
            return None

    def get_scraper_document_urls(self, scraper_name: str) -> dict[str, int]:
        """
        Get URLs of all documents for a given scraper.

        Strategy:
        1. Pre-filter by correspondent name (reduces result set)
        2. Filter client-side by Scraper Name custom field
        3. Fall back to correspondent-only match for pre-existing docs

        Args:
            scraper_name: Scraper name to filter by

        Returns:
            Dict mapping source URLs to document IDs
        """
        if not self.is_configured:
            return {}

        url_map: dict[str, int] = {}

        # Get correspondent ID for pre-filtering (thread-safe)
        correspondent_id: Optional[int] = None
        with self._correspondent_lock:
            if not self._correspondent_cache_populated:
                try:
                    self._correspondent_cache = self._fetch_correspondents()
                    self._correspondent_cache_populated = True
                except Exception as e:
                    self.logger.warning(f"Failed to fetch correspondents for filtering: {e}")

            if self._correspondent_cache_populated:
                for name, cid in self._correspondent_cache.items():
                    if name.lower() == scraper_name.lower():
                        correspondent_id = cid
                        break

        # Build filters
        filters: dict[str, Any] = {}
        if correspondent_id is not None:
            filters["correspondent__id"] = correspondent_id

        documents = self.get_documents(filters=filters)

        # Resolve custom field names to IDs
        scraper_name_field = "Scraper Name"
        original_url_field = "Original URL"

        for doc in documents:
            doc_id = doc.get("id")
            if not doc_id:
                continue

            custom_fields = doc.get("custom_fields", [])

            # Extract field values
            doc_scraper_name: Optional[str] = None
            doc_url: Optional[str] = None

            for cf in custom_fields:
                field_id = cf.get("field")
                value = cf.get("value")

                # Resolve field ID to name via cache
                field_name = self._resolve_custom_field_name(field_id)
                if field_name == scraper_name_field:
                    doc_scraper_name = value
                elif field_name == original_url_field:
                    doc_url = value

            # Match: either scraper_name field matches, or it's absent
            # (fallback for pre-existing docs filtered by correspondent)
            if doc_url:
                if doc_scraper_name and doc_scraper_name.lower() == scraper_name.lower():
                    url_map[doc_url] = doc_id
                elif doc_scraper_name is None and correspondent_id is not None:
                    # Fallback: no scraper_name field, but matched by correspondent
                    url_map[doc_url] = doc_id

        self.logger.info(
            f"Found {len(url_map)} document URLs for scraper '{scraper_name}'"
        )
        return url_map

    def delete_documents_by_tag(self, tag_name: str) -> int:
        """Delete all Paperless documents with a given tag.

        Args:
            tag_name: Tag name to filter by

        Returns:
            Number of documents deleted
        """
        if not self.is_configured or not tag_name:
            return 0

        # Look up tag ID
        tag_id: Optional[int] = None
        with self._tag_lock:
            if not self._tag_cache_populated:
                try:
                    self._tag_cache = self._fetch_tags()
                    self._tag_cache_populated = True
                except Exception as e:
                    self.logger.error(f"Failed to fetch tags: {e}")
                    return 0
            tag_id = next(
                (tid for name, tid in self._tag_cache.items() if name.lower() == tag_name.lower()),
                None,
            )

        if tag_id is None:
            self.logger.warning(f"Tag '{tag_name}' not found, nothing to delete")
            return 0

        # Paginate through documents with this tag
        doc_ids: list[int] = []
        next_url: Optional[str] = f"{self.url}/api/documents/"
        params: dict[str, Any] = {"tags__id": tag_id, "page_size": 100}

        try:
            while next_url:
                response = self.session.get(next_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                for doc in data.get("results", []):
                    doc_id = doc.get("id")
                    if doc_id:
                        doc_ids.append(doc_id)

                next_url = data.get("next")
                params = {}  # params embedded in next_url after first request
        except Exception as e:
            self.logger.error(f"Failed to fetch documents for tag '{tag_name}': {e}")
            return 0

        if not doc_ids:
            self.logger.info(f"No documents found with tag '{tag_name}'")
            return 0

        # Bulk delete
        try:
            response = self.session.post(
                f"{self.url}/api/documents/bulk_edit/",
                json={"documents": doc_ids, "method": "delete", "parameters": {}},
                timeout=60,
            )
            response.raise_for_status()
            self.logger.info(
                f"Deleted {len(doc_ids)} documents with tag '{tag_name}'"
            )
            return len(doc_ids)
        except Exception as e:
            self.logger.error(f"Bulk delete failed for tag '{tag_name}': {e}")
            return 0

    def _resolve_custom_field_name(self, field_id: Optional[int]) -> Optional[str]:
        """Resolve a custom field ID to its name using the cache."""
        if field_id is None:
            return None

        with self._custom_field_lock:
            # Ensure cache is populated
            if not self._custom_field_cache_populated:
                try:
                    self._custom_field_cache = self._fetch_custom_fields()
                    self._custom_field_cache_populated = True
                except Exception:
                    return None

            # Reverse lookup: ID → name
            for name, fid in self._custom_field_cache.items():
                if fid == field_id:
                    return name
            return None
