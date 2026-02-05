"""
Client for interacting with Paperless-ngx API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import requests
import time

from app.config import Config
from app.utils import get_logger


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

    @property
    def is_configured(self) -> bool:
        """Check if client has necessary credentials."""
        return bool(self.url and self.token)

    def post_document(
        self,
        file_path: Union[str, Path],
        title: str,
        created: Optional[datetime] = None,
        correspondent: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Optional[str]:
        """
        Upload a document to Paperless.

        Args:
            file_path: Path to file to upload
            title: Document title
            created: Document creation date
            correspondent: Sender/Author
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
        data = {"title": title}

        if created:
            data["created"] = created.isoformat()

        if correspondent:
            # Paperless API requires IDs (integers). Omit if it looks like a name.
            if isinstance(correspondent, int) or (
                isinstance(correspondent, str) and correspondent.isdigit()
            ):
                data["correspondent"] = correspondent
            else:
                self.logger.warning(
                    f"Paperless API requires IDs, received name: '{correspondent}'. "
                    "Skipping correspondent field. TODO: Implement lookup."
                )

        if tags:
            # Paperless API requires IDs (integers). Omit if they are names.
            numeric_tags = []
            for t in tags:
                if isinstance(t, int) or (isinstance(t, str) and t.isdigit()):
                    numeric_tags.append(t)

            if numeric_tags:
                data["tags"] = numeric_tags
            if len(numeric_tags) < len(tags):
                self.logger.warning(
                    f"Paperless API requires IDs, received tags: {tags}. "
                    "Non-numeric tags were omitted. TODO: Implement lookup."
                )

        self.logger.info(f"Uploading to Paperless: {title}")

        try:
            with open(path, "rb") as f:
                files = {"document": (path.name, f)}
                response = self.session.post(
                    endpoint, data=data, files=files, timeout=60
                )

            response.raise_for_status()

            # Paperless returns task_id (UUID string).
            task_id = response.text
            self.logger.info(f"Upload successful. Task ID: {task_id}")

            return task_id

        except requests.HTTPError as e:
            error_text = getattr(e, "response", None) and e.response.text or str(e)
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

        # Use direct task endpoint for better performance
        endpoint = f"{self.url}/api/tasks/{task_id}/"
        try:
            response = self.session.get(endpoint, timeout=10)
            if response.status_code == 404:
                self.logger.warning(f"Task {task_id} not found at {endpoint}")
                return None
            response.raise_for_status()
            return response.json()

        except Exception as e:
            self.logger.error(f"Failed to query task status: {e}")
            return None

    def verify_document_exists(
        self, task_id: str, timeout: int = 60, poll_interval: int = 2
    ) -> bool:
        """
        Poll task status until document is verified (Sonarr-style).

        Args:
            task_id: Task ID from post_document()
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            True if document verified successfully
        """

        if not self.is_configured:
            return False

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
                return True

            if status == "FAILURE":
                self.logger.error(f"Task {task_id} failed: {task_status}")
                return False

            # Status is PENDING or STARTED, keep polling
            self.logger.debug(f"Task {task_id} status: {status}, waiting...")
            time.sleep(poll_interval)

        self.logger.warning(
            f"Document verification timed out after {timeout}s for task {task_id}"
        )
        return False
