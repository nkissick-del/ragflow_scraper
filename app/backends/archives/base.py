"""Abstract base class for archive backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ArchiveResult:
    """Result from archiving a document."""

    success: bool
    document_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    archive_name: str = ""

    def __post_init__(self):
        """Validate result consistency."""
        if self.success and not self.document_id:
            raise ValueError("Successful archive must include document_id")
        if not self.success and not self.error:
            raise ValueError("Failed archive must include error message")


class ArchiveBackend(ABC):
    """Abstract base class for document archives."""

    @abstractmethod
    def archive_document(
        self,
        file_path: Path,
        title: str,
        created: Optional[str] = None,
        correspondent: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> ArchiveResult:
        """
        Archive a document with metadata.

        Args:
            file_path: Path to file to archive
            title: Document title
            created: Document creation date (ISO format)
            correspondent: Source organization
            tags: List of tags
            metadata: Additional metadata dict

        Returns:
            ArchiveResult with document_id for verification
        """
        raise NotImplementedError

    @abstractmethod
    def verify_document(self, document_id: str, timeout: int = 60) -> bool:
        """
        Verify document was successfully archived (Sonarr-style polling).

        Args:
            document_id: Document ID from archive_document()
            timeout: Max seconds to wait for verification

        Returns:
            True if document verified in archive
        """
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if archive backend is properly configured.

        Returns:
            True if backend has valid configuration
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Get archive name for logging/identification."""
        raise NotImplementedError
