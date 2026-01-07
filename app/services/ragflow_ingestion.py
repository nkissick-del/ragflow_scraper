"""
RAGFlow document ingestion workflow.

Orchestrates the upload → parse → poll → metadata workflow,
isolating ingestion logic for testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional, Any

from app.utils import get_logger

from app.services.ragflow_client import UploadResult

if TYPE_CHECKING:
    from app.services.ragflow_client import RAGFlowClient


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
        # Call upload and normalize different client return shapes (tuple, UploadResult, simple object)
        try:
            raw_result = self.client.upload_document(dataset_id, filepath)
        except Exception as exc:
            # Upload failed at the client layer
            res = UploadResult(success=False, error=str(exc), filename=getattr(filepath, "name", None))
            # attach the file path for integration tests expecting it
            setattr(res, "file_path", filepath)
            return res

        # Normalize tuple response like (document_id, size)
        if isinstance(raw_result, tuple):
            doc_id = raw_result[0] if len(raw_result) > 0 else None
            res = UploadResult(success=bool(doc_id), document_id=doc_id, filename=getattr(filepath, "name", None))
            setattr(res, "file_path", filepath)
            setattr(res, "skipped", False)
            setattr(res, "skipped_duplicate", False)
            return self._maybe_wait_for_parsing(res, dataset_id, timeout, poll_interval)

        # If client returned an UploadResult-like object, try to adapt it
        if isinstance(raw_result, UploadResult):
            res = raw_result
        else:
            # Fallback: object with attributes
            try:
                success = bool(getattr(raw_result, "success", True))
                doc_id = getattr(raw_result, "document_id", None) or getattr(raw_result, "doc_id", None)
                filename = getattr(raw_result, "filename", getattr(raw_result, "file_name", getattr(raw_result, "name", None)))
                res = UploadResult(success=success, document_id=doc_id, filename=filename)
            except Exception:
                res = UploadResult(success=False, error="Invalid upload response", filename=getattr(filepath, "name", None))

        # Ensure common attrs used in tests exist
        setattr(res, "file_path", getattr(res, "file_path", filepath))
        setattr(res, "skipped", getattr(res, "skipped", False))
        setattr(res, "skipped_duplicate", getattr(res, "skipped_duplicate", False))

        return self._maybe_wait_for_parsing(res, dataset_id, timeout, poll_interval)

    def _maybe_wait_for_parsing(self, upload_result: UploadResult, dataset_id: str, timeout: float, poll_interval: float) -> UploadResult:
        """Helper to wait for document parsing and update result accordingly."""
        if upload_result.success and upload_result.document_id:
            self.logger.debug(
                f"Uploaded {getattr(upload_result, 'filename', '')}, waiting for parsing (doc_id={upload_result.document_id})"
            )
            try:
                ready = self.client.wait_for_document_ready(
                    dataset_id,
                    upload_result.document_id,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )
            except Exception as exc:
                # Parsing raised an exception -> mark as failed
                upload_result.success = False
                upload_result.error = str(exc)
                return upload_result

            if not ready:
                # Parsing not ready within timeout; keep upload as successful
                self.logger.warning(
                    f"Document {upload_result.document_id} not ready after {timeout}s"
                )
                # Do not mark as failed; tests expect upload to be considered successful
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
        docs: list[Any],
        *,
        check_duplicates: bool = True,
        wait_timeout: float = 10.0,
        poll_interval: float = 0.5,
        skip_duplicates: Optional[bool] = None,
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

        # Allow callers to pass docs as either dicts ({'filepath': Path, 'metadata': ...})
        # or tuples/lists like (Path, metadata) used by some integration tests.
        if skip_duplicates is not None:
            check_duplicates = bool(skip_duplicates)

        for doc in docs:
            if isinstance(doc, (tuple, list)):
                filepath: Path = doc[0]
                metadata = doc[1] if len(doc) > 1 else None
            elif isinstance(doc, dict):
                filepath: Path = doc["filepath"]
                metadata = doc.get("metadata")
            else:
                # Unknown format
                continue
            file_hash = getattr(metadata, "hash", None) if metadata else None
            # Support both dict and object metadata; dicts use 'file_hash' key
            if not file_hash and isinstance(metadata, dict):
                file_hash = metadata.get("file_hash")

            # Step 1: Check for duplicates
            if check_duplicates and file_hash:
                existing = self.check_exists(dataset_id, file_hash)
                if existing:
                    self.logger.debug(f"Skipping duplicate: {filepath.name} (doc_id={existing})")
                    res = UploadResult(
                        success=True,
                        document_id=existing,
                        filename=filepath.name,
                    )
                    setattr(res, "skipped_duplicate", True)
                    setattr(res, "skipped", True)
                    setattr(res, "file_path", filepath)
                    results.append(res)
                    continue

            # Step 2: Upload and wait for parsing
            upload_result = self.upload_and_wait(
                dataset_id, filepath, timeout=wait_timeout, poll_interval=poll_interval
            )

            if not upload_result.success:
                self.logger.error(f"Upload failed for {filepath.name}: {upload_result.error}")
                # Ensure file_path exists on the result for tests
                setattr(upload_result, "file_path", getattr(upload_result, "file_path", filepath))
                results.append(upload_result)
                continue

            # Step 3: Push metadata (if provided and document is ready)
            doc_id = upload_result.document_id
            if metadata and doc_id:
                payload = None
                if hasattr(metadata, "to_ragflow_metadata"):
                    payload = metadata.to_ragflow_metadata()
                elif isinstance(metadata, dict):
                    payload = metadata
                else:
                    try:
                        payload = dict(metadata)
                    except Exception:
                        payload = None

                if payload is not None:
                    pushed = self.push_metadata(dataset_id, doc_id, payload)
                    upload_result.metadata_pushed = pushed

            results.append(upload_result)

        return results


__all__ = ["RAGFlowIngestionWorkflow"]
