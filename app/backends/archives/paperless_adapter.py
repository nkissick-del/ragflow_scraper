"""Paperless-ngx archive backend adapter."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.backends.archives.base import ArchiveBackend, ArchiveResult
from app.services.paperless_client import PaperlessClient
from app.utils import get_logger


class PaperlessArchiveBackend(ArchiveBackend):
    """Archive backend using Paperless-ngx."""

    def __init__(self, client: Optional[PaperlessClient] = None):
        """
        Initialize Paperless archive backend.

        Args:
            client: Optional PaperlessClient instance (for testing/DI)
        """
        self.client = client or PaperlessClient()
        self.logger = get_logger("backends.archive.paperless")
        self._pending_metadata: dict[str, dict] = {}  # task_id -> metadata

    @property
    def name(self) -> str:
        """Get archive name."""
        return "paperless"

    def is_configured(self) -> bool:
        """Check if Paperless is properly configured."""
        return self.client.is_configured

    def archive_document(
        self,
        file_path: Path,
        title: str,
        created: Optional[str] = None,
        correspondent: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,  # Reserved for future use
    ) -> ArchiveResult:
        """
        Archive document to Paperless-ngx.

        Args:
            file_path: Path to file to archive
            title: Document title
            created: ISO format date string
            correspondent: Source organization
            tags: List of tags
            metadata: Additional metadata (applied as custom fields after verification)

        Returns:
            ArchiveResult with task_id as document_id (Note: document_id is the Paperless task id)

        """
        if not self.is_configured():
            error_msg = "Paperless not configured (missing URL or token)"
            self.logger.error(error_msg)
            return ArchiveResult(success=False, error=error_msg, archive_name=self.name)

        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            self.logger.error(error_msg)
            return ArchiveResult(success=False, error=error_msg, archive_name=self.name)

        # Convert created string to datetime if provided
        created_dt = None
        if created:
            try:
                # Normalize 'Z' to '+00:00' for ISO format parsing
                normalized_date = (
                    created[:-1] + "+00:00" if created.endswith("Z") else created
                )
                created_dt = datetime.fromisoformat(normalized_date)
            except ValueError as e:
                self.logger.warning(f"Invalid date format '{created}': {e}")

        # Upload to Paperless
        task_id = self.client.post_document(
            file_path=file_path,
            title=title,
            created=created_dt,
            correspondent=correspondent,  # type: ignore[arg-type]
            tags=tags,  # type: ignore[arg-type]
        )

        if not task_id:
            error_msg = "Paperless upload failed (no task_id returned)"
            self.logger.error(error_msg)
            return ArchiveResult(success=False, error=error_msg, archive_name=self.name)

        # Store metadata keyed by task_id for custom fields (applied after verification).
        # Evict oldest entry if at capacity to prevent unbounded growth.
        if metadata:
            _MAX_PENDING = 100
            if len(self._pending_metadata) >= _MAX_PENDING:
                oldest_key = next(iter(self._pending_metadata))
                self._pending_metadata.pop(oldest_key, None)
            self._pending_metadata[task_id] = metadata

        self.logger.info(f"Document archived to Paperless: task_id={task_id}")
        return ArchiveResult(
            success=True,
            document_id=task_id,
            url=f"{self.client.url}/tasks/{task_id}",
            archive_name=self.name,
        )

    def verify_document(self, document_id: str, timeout: int = 60) -> bool:
        """
        Verify document was successfully archived (Sonarr-style polling).

        Args:
            document_id: Task ID from archive_document()
            timeout: Max seconds to wait

        Returns:
            True if document verified in Paperless
        """
        if not self.is_configured():
            self.logger.error("Cannot verify - Paperless not configured")
            return False

        verified_id = self.client.verify_document_exists(
            task_id=document_id, timeout=timeout, poll_interval=2
        )

        # Retrieve and always clean up pending metadata for this task
        pending = self._pending_metadata.pop(document_id, None)

        if verified_id is not None and pending:
            # Apply custom fields (non-fatal)
            try:
                self.client.set_custom_fields(int(verified_id), pending)
            except Exception as e:
                self.logger.warning(f"Failed to set custom fields: {e}")

        return verified_id is not None
