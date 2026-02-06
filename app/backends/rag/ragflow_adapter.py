"""RAGFlow RAG backend adapter."""

from pathlib import Path
from typing import Optional

from app.backends.rag.base import RAGBackend, RAGResult
from app.services.ragflow_client import RAGFlowClient
from app.utils import get_logger


class RAGFlowBackend(RAGBackend):
    """RAG backend using RAGFlow."""

    def __init__(self, client: Optional[RAGFlowClient] = None):
        """
        Initialize RAGFlow backend.

        Args:
            client: Optional RAGFlowClient instance (for testing/DI)
        """
        self.client = client or RAGFlowClient()
        self.logger = get_logger("backends.rag.ragflow")

    @property
    def name(self) -> str:
        """Get RAG backend name."""
        return "ragflow"

    def is_configured(self) -> bool:
        """Check if RAGFlow is properly configured."""
        return bool(self.client.api_url and self.client.api_key)

    def test_connection(self) -> bool:
        """Test connection to RAGFlow service."""
        if not self.is_configured():
            self.logger.warning("RAGFlow not configured (missing URL or API key)")
            return False

        try:
            # Try to list datasets as a connectivity test
            datasets = self.client.list_datasets()
            return isinstance(datasets, list)
        except Exception as e:
            self.logger.error(f"RAGFlow connection test failed: {e}")
            return False

    def ingest_document(
        self,
        markdown_path: Path,
        metadata: dict,
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        """
        Ingest Markdown document into RAGFlow.

        Args:
            markdown_path: Path to Markdown file
            metadata: Document metadata dict
            collection_id: Optional dataset ID (uses default if not provided)

        Returns:
            RAGResult with document_id and status
        """
        if not self.is_configured():
            error_msg = "RAGFlow not configured (missing URL or API key)"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

        if not markdown_path.exists():
            error_msg = f"Markdown file not found: {markdown_path}"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

        # Use provided collection_id or get default dataset
        dataset_id = collection_id
        if not dataset_id:
            # Try to get first dataset as default
            try:
                datasets = self.client.list_datasets()
                if (
                    not datasets
                    or not isinstance(datasets, list)
                    or not isinstance(datasets[0], dict)
                    or "id" not in datasets[0]
                ):
                    error_msg = (
                        "No RAGFlow datasets found or invalid dataset response, "
                        "and no collection_id provided"
                    )
                    self.logger.error(error_msg)
                    return RAGResult(success=False, error=error_msg, rag_name=self.name)
                dataset_id = datasets[0]["id"]
                self.logger.info(f"Using default dataset: {dataset_id}")
            except Exception as e:
                error_msg = f"Failed to get default dataset: {e}"
                self.logger.error(error_msg)
                return RAGResult(success=False, error=error_msg, rag_name=self.name)

        try:
            # Prepare metadata for RAGFlow
            ragflow_metadata = self._prepare_metadata(metadata)

            # Upload document with metadata using ingestion workflow
            upload_result = self.client.upload_documents_with_metadata(
                dataset_id=dataset_id,  # type: ignore
                files_with_metadata=[(markdown_path, ragflow_metadata)],  # type: ignore
            )

            if not upload_result or not upload_result[0].success:
                # Coalesce error message to ensure it's never None
                error_info = ""
                if upload_result and upload_result[0]:
                    res = upload_result[0]
                    error_info = (
                        res.error or res.get("error") if hasattr(res, "get") else None
                    ) or f"Status: {getattr(res, 'status', 'Unknown')}"

                error_msg = (
                    f"RAGFlow upload failure: {error_info}"
                    if error_info
                    else "Unknown RAGFlow upload failure"
                )
                self.logger.error(error_msg)
                return RAGResult(success=False, error=error_msg, rag_name=self.name)

            result = upload_result[0]
            self.logger.info(
                f"Document ingested to RAGFlow: {result.document_id} "
                f"(dataset={dataset_id})"
            )

            return RAGResult(
                success=True,
                document_id=result.document_id,
                collection_id=dataset_id,
                rag_name=self.name,
            )

        except Exception as e:
            error_msg = f"RAGFlow ingestion failed: {e}"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

    def _prepare_metadata(self, metadata: dict) -> dict:
        """
        Prepare metadata for RAGFlow ingestion.

        Args:
            metadata: Raw metadata dict from DocumentMetadata

        Returns:
            RAGFlow-compatible metadata dict
        """
        # Local import to avoid circular dependency with ragflow_metadata
        from app.services.ragflow_metadata import prepare_metadata_for_ragflow

        # Use existing helper to prepare metadata
        return prepare_metadata_for_ragflow(metadata)
