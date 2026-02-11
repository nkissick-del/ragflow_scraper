"""Abstract base class for vector store backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class VectorStoreResult:
    """Result from storing chunks in a vector store."""

    success: bool
    chunks_stored: int = 0
    error: Optional[str] = None
    store_name: str = ""

    def __post_init__(self):
        """Validate result consistency."""
        if not self.store_name:
            raise ValueError("store_name must be provided and non-empty")
        if self.success:
            if self.chunks_stored < 0:
                raise ValueError("chunks_stored must be non-negative on success")
            if self.error:
                raise ValueError(
                    "Successful store result must not include error message"
                )
        else:
            if not self.error:
                raise ValueError("Failed store result must include error message")


class VectorStoreBackend(ABC):
    """Abstract base class for vector storage systems."""

    @abstractmethod
    def store_chunks(
        self,
        source: str,
        filename: str,
        chunks: list[dict[str, Any]],
        document_id: Optional[str] = None,
    ) -> int:
        """Store document chunks with embeddings.

        Args:
            source: Source/partition name (e.g., scraper name)
            filename: Document filename
            chunks: List of dicts with keys: content, embedding, metadata, chunk_index
            document_id: Optional document ID to store in metadata

        Returns:
            Number of chunks stored
        """
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, source: str, filename: str) -> int:
        """Delete all chunks for a document.

        Args:
            source: Source/partition name
            filename: Document filename

        Returns:
            Number of chunks deleted
        """
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        sources: Optional[list[str]] = None,
        metadata_filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query vector
            sources: Optional list of source names to filter by
            metadata_filter: Optional metadata filter
            limit: Maximum results to return

        Returns:
            List of result dicts with: source, filename, chunk_index,
            content, metadata, score
        """
        raise NotImplementedError

    @abstractmethod
    def get_sources(self) -> list[dict[str, Any]]:
        """List all sources with their chunk counts.

        Returns:
            List of dicts with: source, chunk_count
        """
        raise NotImplementedError

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Get overall statistics.

        Returns:
            Dict with: total_chunks, total_documents, total_sources
        """
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the vector store is properly configured.

        Returns:
            True if backend has valid configuration
        """
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity to the vector store.

        Returns:
            True if service is reachable
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Get vector store backend name for logging/identification."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if the vector store is available for use.

        Default implementation delegates to is_configured().
        Subclasses may override to add connectivity checks.

        Returns:
            True if backend is available
        """
        return self.is_configured()

    def ensure_ready(self) -> None:
        """Ensure the vector store is ready (schema, indexes, etc.).

        Default is a no-op. Implementations may create tables, indexes, etc.
        """

    def close(self) -> None:
        """Close connections and release resources.

        Default is a no-op. Implementations may close connection pools, etc.
        """

    def get_document_chunks(
        self, source: str, filename: str
    ) -> list[dict[str, Any]]:
        """Get all chunks for a specific document.

        Default returns empty list. Not all backends may support this.

        Args:
            source: Source/partition name
            filename: Document filename

        Returns:
            List of dicts with: chunk_index, content, metadata
        """
        return []
