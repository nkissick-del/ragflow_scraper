"""HTTP download mixin for scraper file downloads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, List, Any, TYPE_CHECKING

import requests

from app.config import Config
from app.utils import (
    ensure_dir,
    sanitize_filename,
    CHUNK_SIZE,
)
from app.utils.errors import DownloadError, NetworkError, ScraperError
from app.utils.retry import retry_on_error

if TYPE_CHECKING:
    from app.scrapers.models import DocumentMetadata


class HttpDownloadMixin:
    # Expected attributes
    dry_run: bool = False
    download_timeout: int = 30

    def __init__(self):
        super().__init__()
        self._errors: List[str] = []

    logger: Any = None
    name: str = ""

    # Provide a metadata save hook signature so Pylance knows this exists
    def _save_metadata(
        self, metadata: "DocumentMetadata"
    ) -> None:  # pragma: no cover - overridden by MetadataIOMixin
        raise NotImplementedError()

    def _download_file(
        self,
        url: str,
        filename: str,
        metadata: Optional["DocumentMetadata"] = None,
    ) -> Optional[Path]:
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would download: {url}")
            return None

        safe_filename = sanitize_filename(filename)
        download_path = ensure_dir(Config.DOWNLOAD_DIR / self.name) / safe_filename

        @retry_on_error(exceptions=(NetworkError, DownloadError), max_attempts=None)
        def _attempt_download() -> Path:
            try:
                self.logger.info(f"Downloading: {url}")

                # Use session if available (from BaseScraper), otherwise fallback to requests
                session = getattr(self, "_session", None) or requests

                response = session.get(
                    url,
                    timeout=self.download_timeout,
                    stream=True,
                    headers={"User-Agent": "Mozilla/5.0 PDF Scraper"},
                )
                response.raise_for_status()
            except requests.RequestException:
                raise NetworkError(
                    f"Failed to fetch {url}",
                    scraper=self.name,
                    context={"url": url},
                )

            try:
                hash_obj = hashlib.sha256()
                file_size = 0
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                        hash_obj.update(chunk)
                        file_size += len(chunk)
            except Exception:
                raise DownloadError(
                    f"Failed to write file for {url}",
                    scraper=self.name,
                    recoverable=False,
                    context={"url": url, "path": str(download_path)},
                )

            self.logger.info(f"Downloaded: {download_path}")

            if metadata:
                metadata.local_path = str(download_path)
                metadata.hash = hash_obj.hexdigest()
                # Update file_size if not already present or if different (trust actual download size)
                if metadata.file_size is None or metadata.file_size == 0:
                    metadata.file_size = file_size

                self._save_metadata(metadata)

            return download_path

        try:
            return _attempt_download()
        except ScraperError as exc:
            self.logger.warning(str(exc))
            self._errors.append(str(exc))
            return None
