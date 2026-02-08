"""Abstract base class for RAG backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class RAGResult:
    """Result from ingesting a document to RAG."""

    success: bool
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    error: Optional[str] = None
    rag_name: str = ""

    def __post_init__(self):
        """Validate result consistency."""
        if not self.rag_name:
            raise ValueError("rag_name must be provided and non-empty")
        if self.success:
            if not self.document_id:
                raise ValueError("Successful RAG ingestion must include document_id")
            if self.error:
                raise ValueError(
                    "Successful RAG ingestion must not include error message"
                )
        else:
            if not self.error:
                raise ValueError("Failed RAG ingestion must include error message")


class RAGBackend(ABC):
    """Abstract base class for RAG systems."""

    @abstractmethod
    def ingest_document(
        self,
        markdown_path: Path,
        metadata: dict[str, Any],
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        """
        Ingest a Markdown document into RAG system.

        Args:
            markdown_path: Path to Markdown file
            metadata: Document metadata dict
            collection_id: Optional collection/dataset ID

        Returns:
            RAGResult with document_id and status
        """
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if RAG backend is properly configured.

        Returns:
            True if backend has valid configuration
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """
        Check if RAG backend is available for use.

        Default implementation delegates to is_configured().
        Subclasses may override to add connectivity checks.

        Returns:
            True if backend is available
        """
        return self.is_configured()

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test connection to RAG service.

        Returns:
            True if service is reachable
        """
        raise NotImplementedError

    def list_documents(self, collection_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        List documents in a RAG collection/dataset.

        Not all backends support this. Default returns empty list.

        Args:
            collection_id: Optional collection/dataset ID

        Returns:
            List of document dicts with at least 'id' and optional 'name' keys
        """
        return []

    @property
    @abstractmethod
    def name(self) -> str:
        """Get RAG backend name for logging/identification."""
        raise NotImplementedError
