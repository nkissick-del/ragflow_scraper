"""
RAGFlow document ingestion workflow.

Orchestrates the upload → parse → poll → metadata workflow,
isolating ingestion logic for testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

from app.utils import get_logger

if TYPE_CHECKING:
    from app.services.ragflow_client import RAGFlowClient, UploadResult


class RAGFlowIngestionWorkflow:
    """
    Manages the complete document ingestion workflow.

    Responsibilities:
    - Check for duplicate documents by hash
    - Upload documents and poll until ready
    - Push metadata after parsing completes
    - Handle batch uploads with partial failure tolerance
    """

    def __init__(self, client: RAGFlowClient):
        """
        Initialize workflow with RAGFlow client.

        Args:
            client: RAGFlowClient instance for API calls
        """
        self.client = client
        self.logger = get_logger("ragflow.ingestion")

    def check_exists(self, dataset_id: str, file_hash: str) -> Optional[str]:
        """
        Check if document already exists in dataset by hash.

        Args:
            dataset_id: RAGFlow dataset ID
            file_hash: File content hash

        Returns:
            Document ID if exists, None otherwise
        """
        return self.client.check_document_exists(dataset_id, file_hash)

    def upload_and_wait(
        self,
        dataset_id: str,
        filepath: Path,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> UploadResult:
        """
        Upload document and poll until parsing is ready.

        Args:
            dataset_id: RAGFlow dataset ID
            filepath: Path to file to upload
            timeout: Maximum seconds to wait for parsing
            poll_interval: Seconds between status checks

        Returns:
            UploadResult with success status and document ID
        """
        upload_result = self.client.upload_document(dataset_id, filepath)

        if upload_result.success and upload_result.document_id:
            self.logger.debug(
                f"Uploaded {filepath.name}, waiting for parsing (doc_id={upload_result.document_id})"
            )
            ready = self.client.wait_for_document_ready(
                dataset_id,
                upload_result.document_id,
                timeout=timeout,
                poll_interval=poll_interval,
            )
            if not ready:
                self.logger.warning(
                    f"Document {upload_result.document_id} not ready after {timeout}s"
                )

        return upload_result

    def push_metadata(self, dataset_id: str, document_id: str, metadata: dict) -> bool:
        """
        Set document metadata after parsing completes.

        Args:
            dataset_id: RAGFlow dataset ID
            document_id: Document ID
            metadata: Metadata dictionary (should be pre-formatted for RAGFlow)

        Returns:
            True if metadata was successfully set
        """
        success = self.client.set_document_metadata(dataset_id, document_id, metadata)
        if success:
            self.logger.debug(f"Pushed metadata for document {document_id}")
        else:
            self.logger.warning(f"Failed to push metadata for document {document_id}")
        return success

    def ingest_with_metadata(
        self,
        dataset_id: str,
        docs: list[dict],
        *,
        check_duplicates: bool = True,
        wait_timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> list[UploadResult]:
        """
        Full ingestion workflow: dedup → upload → parse → metadata.

        Args:
            dataset_id: RAGFlow dataset ID
            docs: List of dicts with 'filepath' (Path) and optional 'metadata' (DocumentMetadata)
            check_duplicates: If True, skip files that already exist (by hash)
            wait_timeout: Max seconds to wait for each document to parse
            poll_interval: Seconds between status checks

        Returns:
            List of UploadResult, one per document
        """
        from app.services.ragflow_client import UploadResult

        results: list[UploadResult] = []

        for doc in docs:
            filepath: Path = doc["filepath"]
            metadata = doc.get("metadata")
            file_hash = getattr(metadata, "hash", None) if metadata else None

            # Step 1: Check for duplicates
            if check_duplicates and file_hash:
                existing = self.check_exists(dataset_id, file_hash)
                if existing:
                    self.logger.debug(f"Skipping duplicate: {filepath.name} (doc_id={existing})")
                    results.append(
                        UploadResult(
                            success=True,
                            document_id=existing,
                            filename=filepath.name,
                            skipped_duplicate=True,
                        )
                    )
                    continue

            # Step 2: Upload and wait for parsing
            upload_result = self.upload_and_wait(
                dataset_id, filepath, timeout=wait_timeout, poll_interval=poll_interval
            )

            if not upload_result.success:
                self.logger.error(f"Upload failed for {filepath.name}: {upload_result.error}")
                results.append(upload_result)
                continue

            # Step 3: Push metadata (if provided and document is ready)
            doc_id = upload_result.document_id
            if metadata and doc_id:
                pushed = self.push_metadata(
                    dataset_id, doc_id, metadata.to_ragflow_metadata()
                )
                upload_result.metadata_pushed = pushed

            results.append(upload_result)

        return results


__all__ = ["RAGFlowIngestionWorkflow"]
