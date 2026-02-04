"""
Client for interacting with Paperless-ngx API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import requests

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
        self.url = (url or Config.PAPERLESS_API_URL).rstrip("/")
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
    ) -> Optional[int]:
        """
        Upload a document to Paperless.

        Args:
            file_path: Path to file to upload
            title: Document title
            created: Document creation date
            correspondent: Sender/Author
            tags: List of tags

        Returns:
            Document ID if successful (placeholder), None otherwise
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
            # Paperless API often requires IDs for correspondents.
            # For now we attempt to pass the name, but usually this needs an ID lookup.
            # We'll log a warning if this might fail, but attempt it.
            # Ideally we should implement get_or_create_correspondent later.
            data["correspondent"] = correspondent

        if tags:
            # Similar to correspondent, tags usually need IDs.
            data["tags"] = tags

        self.logger.info(f"Uploading to Paperless: {title}")

        try:
            with open(path, "rb") as f:
                files = {"document": (path.name, f)}
                response = self.session.post(
                    endpoint, data=data, files=files, timeout=60
                )

            response.raise_for_status()

            # Paperless returns task_id. For now we assume success if 200 OK.
            result = response.text
            self.logger.info(f"Upload successful. Response: {result}")

            # TODO: Poll task status to get real Doc ID. Returning 1 as success flag.
            return 1

        except requests.HTTPError as e:
            self.logger.error(f"Paperless upload HTTP error: {e.response.text}")
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
