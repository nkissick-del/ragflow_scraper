"""
Client for interacting with Paperless-ngx API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Any

import requests
import threading
import time
import uuid

from app.config import Config
from app.utils import get_logger

# Maps metadata dict keys to (Paperless custom field name, Paperless data type)
CUSTOM_FIELD_MAPPING: dict[str, tuple[str, str]] = {
    "url": ("Original URL", "url"),
    "scraped_at": ("Scraped Date", "string"),
    "page_count": ("Page Count", "integer"),
    "file_size": ("File Size", "integer"),
    "source_page": ("Source Page", "url"),
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

        # Caches for name-to-ID lookups (populated on first use)
        self._correspondent_cache: dict[str, int] = {}
        self._correspondent_cache_populated = False
        self._correspondent_lock = threading.RLock()
        self._tag_cache: dict[str, int] = {}
        self._tag_cache_populated = False
        self._tag_lock = threading.RLock()
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
                    json={"name": name},
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
                    json={"name": name},
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
                    json={"name": name, "data_type": data_type},
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

        custom_fields_payload: list[dict] = []

        for meta_key, (field_name, data_type) in CUSTOM_FIELD_MAPPING.items():
            value = metadata.get(meta_key)
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
        except Exception as e:
            self.logger.error(
                f"Failed to set custom fields on document {document_id}: {e}"
            )
            return False

    def post_document(
        self,
        file_path: Union[str, Path],
        title: str,
        created: Optional[datetime] = None,
        correspondent: Optional[Union[str, int]] = None,
        tags: Optional[list[Union[str, int]]] = None,
    ) -> Optional[str]:
        """
        Upload a document to Paperless.

        Args:
            file_path: Path to file to upload
            title: Document title
            created: Document creation date
            correspondent: Sender/Author (name or numeric ID)
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
            # Resolve string name to integer ID if needed
            if isinstance(correspondent, int):
                data["correspondent"] = correspondent
            elif isinstance(correspondent, str) and correspondent.isdigit():
                data["correspondent"] = int(correspondent)
            else:
                # Look up or create correspondent by name
                corr_id = self.get_or_create_correspondent(correspondent)
                if corr_id:
                    data["correspondent"] = corr_id
                else:
                    self.logger.warning(
                        f"Could not resolve correspondent '{correspondent}', skipping"
                    )

        if tags:
            # Resolve string names to integer IDs
            tag_ids: list[int] = []
            string_tags: list[str] = []

            for t in tags:
                if isinstance(t, int):
                    tag_ids.append(t)
                elif isinstance(t, str) and t.isdigit():
                    tag_ids.append(int(t))
                elif isinstance(t, str):
                    string_tags.append(t)

            # Look up or create string tags
            if string_tags:
                resolved_ids = self.get_or_create_tags(string_tags)
                tag_ids.extend(resolved_ids)

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

            # Paperless returns task_id (UUID string).
            # We sanitize and validate the response text.
            raw_text = response.text.strip()

            # Handle JSON response if applicable
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("application/json") or raw_text.startswith(
                ("{", "[")
            ):
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict):
                        task_id = response_data.get("task_id")
                    elif (
                        isinstance(response_data, list)
                        and response_data
                        and isinstance(response_data[0], dict)
                    ):
                        task_id = response_data[0].get("task_id")
                    else:
                        task_id = (
                            response_data if isinstance(response_data, str) else None
                        )
                except Exception:
                    task_id = raw_text.strip("'\"")
            else:
                # Strip surrounding quotes if present
                task_id = raw_text.strip("'\"")

            # Validate task_id is a proper UUID
            if task_id:
                try:
                    uuid.UUID(str(task_id))
                    task_id = str(task_id)
                except (ValueError, TypeError, AttributeError):
                    self.logger.error(
                        f"Invalid task_id received from Paperless: {task_id}"
                    )
                    return None
            else:
                self.logger.error("No task_id received from Paperless")
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
