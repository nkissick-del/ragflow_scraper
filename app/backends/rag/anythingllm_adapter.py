"""AnythingLLM RAG backend adapter."""

import json
from pathlib import Path
from typing import Any, Optional

from app.backends.rag.base import RAGBackend, RAGResult
from app.services.anythingllm_client import AnythingLLMClient
from app.utils import get_logger


class AnythingLLMBackend(RAGBackend):
    """RAG backend using AnythingLLM."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ):
        """
        Initialize AnythingLLM backend.

        Args:
            api_url: AnythingLLM API URL
            api_key: API key for authentication
            workspace_id: Default workspace ID
        """
        self.client = AnythingLLMClient(
            api_url=api_url,
            api_key=api_key,
            workspace_id=workspace_id,
        )
        self.logger = get_logger("backends.rag.anythingllm")

    @property
    def name(self) -> str:
        """Get RAG backend name."""
        return "anythingllm"

    def is_configured(self) -> bool:
        """Check if AnythingLLM is properly configured."""
        return bool(self.client.api_url and self.client.api_key)

    def test_connection(self) -> bool:
        """Test connection to AnythingLLM service."""
        if not self.is_configured():
            self.logger.warning("AnythingLLM not configured (missing URL or API key)")
            return False

        try:
            return self.client.test_connection()
        except Exception as e:
            self.logger.error(f"AnythingLLM connection test failed: {e}")
            return False

    def list_documents(self, collection_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        List documents stored in AnythingLLM.

        Args:
            collection_id: Ignored (AnythingLLM lists all documents globally).
                           Present for RAGBackend interface conformance.
        """
        if not self.is_configured():
            return []
        try:
            _ = collection_id  # interface conformance; AnythingLLM has no per-collection filter
            return self.client.list_documents()
        except Exception as e:
            self.logger.error(f"Failed to list AnythingLLM documents: {e}")
            return []

    def ingest_document(
        self,
        content_path: Path,
        metadata: dict,
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        """
        Ingest document into AnythingLLM.

        Args:
            content_path: Path to content file (HTML, Markdown, etc.)
            metadata: Document metadata dict
            collection_id: Optional workspace ID (overrides default)

        Returns:
            RAGResult with document_id and status
        """
        if not self.is_configured():
            error_msg = "AnythingLLM not configured (missing URL or API key)"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

        if not content_path.exists():
            error_msg = f"Content file not found: {content_path}"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

        try:
            # Prepare metadata for AnythingLLM
            anythingllm_metadata = self._prepare_metadata(metadata)

            # Determine workspace ID
            workspace_ids = None
            if collection_id:
                workspace_ids = [collection_id]
            elif self.client.workspace_id:
                workspace_ids = [self.client.workspace_id]

            # Upload document
            upload_result = self.client.upload_document(
                filepath=content_path,
                folder_name="scraped_documents",
                workspace_ids=workspace_ids,
                metadata=anythingllm_metadata,
            )

            if not upload_result.success:
                error_msg = upload_result.error or "Unknown upload failure"
                self.logger.error(f"AnythingLLM upload failed: {error_msg}")
                return RAGResult(success=False, error=error_msg, rag_name=self.name)

            self.logger.info(
                f"Document ingested to AnythingLLM: {upload_result.document_id} "
                f"(workspace={upload_result.workspace_id or collection_id or 'default'})"
            )

            return RAGResult(
                success=True,
                document_id=upload_result.document_id,
                collection_id=upload_result.workspace_id or collection_id,
                rag_name=self.name,
            )

        except Exception as e:
            error_msg = f"AnythingLLM ingestion failed: {e}"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

    def _prepare_metadata(self, metadata: dict) -> dict:
        """
        Prepare metadata for AnythingLLM ingestion.

        Args:
            metadata: Raw metadata dict from DocumentMetadata

        Returns:
            AnythingLLM-compatible metadata dict
        """
        # AnythingLLM accepts arbitrary metadata fields
        # We'll pass through relevant fields and flatten nested structures
        prepared = {}

        # Core fields
        for field in ["title", "url", "organization", "source", "document_type"]:
            if field in metadata and metadata[field]:
                prepared[field] = metadata[field]

        # Date fields
        for date_field in ["publication_date", "scraped_at"]:
            if date_field in metadata and metadata[date_field]:
                prepared[date_field] = str(metadata[date_field])

        # Numeric fields
        for num_field in ["file_size", "page_count"]:
            if num_field in metadata and metadata[num_field] is not None:
                prepared[num_field] = metadata[num_field]

        # Hash for deduplication
        if "hash" in metadata and metadata["hash"]:
            prepared["file_hash"] = metadata["hash"]

        # Flatten extra metadata
        if "extra" in metadata and isinstance(metadata["extra"], dict):
            for key, value in metadata["extra"].items():
                if key not in prepared and value is not None:
                    # Convert complex types to strings
                    if isinstance(value, (dict, list)):
                        prepared[f"extra_{key}"] = json.dumps(value)
                    else:
                        prepared[f"extra_{key}"] = str(value)

        return prepared
