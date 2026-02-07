"""
Apache Tika client for text and metadata extraction.

Provides HTTP client for interacting with Apache Tika server:
- Text extraction from any supported document format
- Metadata extraction (Dublin Core normalized)
- MIME type detection
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests

from app.config import Config
from app.utils import get_logger


# Dublin Core → standard key mapping
_METADATA_KEY_MAP = {
    "dc:title": "title",
    "dc:creator": "author",
    "dc:description": "description",
    "dc:subject": "subject",
    "dc:language": "language",
    "dcterms:created": "creation_date",
    "dcterms:modified": "modification_date",
    "meta:page-count": "page_count",
    "xmpTPg:NPages": "page_count",
    "meta:word-count": "word_count",
    "meta:author": "author",
    "meta:creation-date": "creation_date",
    "pdf:PDFVersion": "pdf_version",
    "Content-Type": "content_type",
}


class TikaClient:
    """Client for Apache Tika server API."""

    def __init__(
        self,
        url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.url = (url or Config.TIKA_SERVER_URL or "").rstrip("/")
        self.timeout = timeout or getattr(Config, "TIKA_TIMEOUT", 120)
        self.logger = get_logger("tika.client")

    @property
    def is_configured(self) -> bool:
        """Check if Tika server URL is set."""
        return bool(self.url)

    def health_check(self) -> bool:
        """Check Tika server health (GET /tika)."""
        if not self.url:
            return False
        try:
            resp = requests.get(f"{self.url}/tika", timeout=10)
            return resp.ok
        except Exception:
            return False

    def extract_text(self, file_path: Path) -> str:
        """
        Extract plain text from a document.

        Uses PUT /tika with file bytes in request body.

        Args:
            file_path: Path to document

        Returns:
            Extracted text content

        Raises:
            requests.HTTPError: On non-2xx response
            requests.RequestException: On connection failure
        """
        with open(file_path, "rb") as f:
            data = f.read()

        resp = requests.put(
            f"{self.url}/tika",
            data=data,
            headers={"Accept": "text/plain"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.text

    def extract_metadata(self, file_path: Path) -> dict:
        """
        Extract and normalize metadata from a document.

        Uses PUT /meta with file bytes in request body.
        Normalizes Dublin Core keys to standard names.

        Args:
            file_path: Path to document

        Returns:
            Normalized metadata dict
        """
        with open(file_path, "rb") as f:
            data = f.read()

        resp = requests.put(
            f"{self.url}/meta",
            data=data,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        raw = resp.json()

        return self._normalize_metadata(raw)

    def detect_mime_type(self, file_path: Path) -> str:
        """
        Detect MIME type of a file.

        Uses PUT /detect/stream.

        Args:
            file_path: Path to file

        Returns:
            MIME type string (e.g. "application/pdf")
        """
        with open(file_path, "rb") as f:
            data = f.read()

        resp = requests.put(
            f"{self.url}/detect/stream",
            data=data,
            headers={"Accept": "text/plain"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.text.strip()

    def _normalize_metadata(self, raw: dict) -> dict:
        """
        Normalize Tika metadata keys to standard names.

        Args:
            raw: Raw metadata dict from Tika

        Returns:
            Normalized metadata dict
        """
        normalized: dict = {}

        for raw_key, value in raw.items():
            mapped_key = _METADATA_KEY_MAP.get(raw_key)
            if mapped_key:
                # Don't overwrite existing values (first match wins)
                if mapped_key not in normalized:
                    # Convert page_count / word_count to int
                    if mapped_key in ("page_count", "word_count"):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            continue
                    normalized[mapped_key] = value

        return normalized


__all__ = ["TikaClient"]
