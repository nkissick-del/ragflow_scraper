"""
Pipeline execution for scrape -> upload -> parse workflows.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import Config
from app.container import get_container
from app.scrapers import ScraperRegistry
from app.scrapers.models import DocumentMetadata
from app.utils import get_logger
from app.utils.errors import ParserBackendError, ArchiveError
from app.utils.file_utils import generate_filename_from_template
from app.utils.logging_config import log_exception, log_event


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""

    status: str  # "completed", "partial", "failed"
    scraper_name: str
    scraped_count: int = 0
    downloaded_count: int = 0
    parsed_count: int = 0
    archived_count: int = 0
    verified_count: int = 0
    rag_indexed_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "scraper_name": self.scraper_name,
            "scraped_count": self.scraped_count,
            "downloaded_count": self.downloaded_count,
            "parsed_count": self.parsed_count,
            "archived_count": self.archived_count,
            "verified_count": self.verified_count,
            "rag_indexed_count": self.rag_indexed_count,
            "failed_count": self.failed_count,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "errors": self.errors,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class Pipeline:
    """
    Pipeline for executing the full scrape -> upload -> parse workflow.

    Steps:
    1. Run scraper to download documents
    2. Upload downloaded documents to RAGFlow
    3. Trigger parsing in RAGFlow
    4. Monitor parsing status
    """

    def __init__(
        self,
        scraper_name: str,
        dataset_id: Optional[str] = None,
        max_pages: Optional[int] = None,
        upload_to_ragflow: bool = True,
        upload_to_paperless: bool = True,
        verify_document_timeout: int = 60,
        container=None,
    ):
        """
        Initialize the pipeline.

        Args:
            scraper_name: Name of the scraper to run
            dataset_id: RAGFlow dataset ID (uses config if not provided)
            max_pages: Maximum pages to scrape
            upload_to_ragflow: Whether to upload to RAGFlow
            upload_to_paperless: Whether to upload to Paperless
            wait_for_parsing: Whether to wait for parsing to complete
        """
        self.scraper_name = scraper_name
        self.dataset_id = dataset_id or Config.RAGFLOW_DATASET_ID
        self.max_pages = max_pages
        self.upload_to_ragflow = upload_to_ragflow
        self.upload_to_paperless = upload_to_paperless
        self.verify_document_timeout = verify_document_timeout
        self.container = container or get_container()

        self.logger = get_logger(f"pipeline.{scraper_name}")
        self.ragflow = self.container.ragflow_client if upload_to_ragflow else None
        self._step_times: dict[str, float] = {}

    def run(self) -> PipelineResult:
        """
        Execute the full pipeline.

        Returns:
            PipelineResult with statistics
        """
        start_time = time.perf_counter()
        step_times: dict[str, float] = {}

        result = PipelineResult(
            status="running",
            scraper_name=self.scraper_name,
        )

        try:
            # Step 1: Run scraper
            log_event(
                self.logger, "info", "pipeline.scrape.start", scraper=self.scraper_name
            )
            step_start = time.perf_counter()
            scraper_result = self._run_scraper()
            step_times["scrape"] = time.perf_counter() - step_start
            self._step_times = step_times

            result.scraped_count = scraper_result.scraped_count
            result.downloaded_count = scraper_result.downloaded_count
            result.errors.extend(scraper_result.errors)

            if scraper_result.status == "failed":
                result.status = "failed"
                result.errors.append("Scraper failed")
                return self._finalize_result(result, start_time)

            if result.downloaded_count == 0:
                self.logger.info("No new documents downloaded, skipping processing")
                result.status = "completed"
                return self._finalize_result(result, start_time)

            # Step 2: Process documents through modular pipeline
            process_start = time.perf_counter()
            log_event(
                self.logger,
                "info",
                "pipeline.process.start",
                scraper=self.scraper_name,
                document_count=len(scraper_result.documents),
            )

            known_fields = {f.name for f in dataclass_fields(DocumentMetadata)}

            for doc_dict in scraper_result.documents:
                try:
                    # Reconstruct DocumentMetadata from dict
                    doc_keys = set(doc_dict.keys())
                    dropped_fields = (
                        doc_keys - known_fields - {"pdf_path", "local_path"}
                    )
                    if dropped_fields:
                        self.logger.debug(
                            f"Dropped fields from DocumentMetadata for {doc_dict.get('title', 'unknown')}: "
                            f"{', '.join(sorted(dropped_fields))}"
                        )

                    filtered_dict = {
                        k: v for k, v in doc_dict.items() if k in known_fields
                    }

                    try:
                        doc_metadata = DocumentMetadata(**filtered_dict)
                    except TypeError as e:
                        self.logger.error(f"Failed to construct DocumentMetadata: {e}")
                        result.failed_count += 1
                        continue

                    # Get PDF path
                    pdf_path = doc_dict.get("pdf_path") or doc_dict.get("local_path")
                    if not pdf_path:
                        self.logger.warning(
                            f"Skipping document (no PDF path): {doc_dict.get('title')}"
                        )
                        result.failed_count += 1
                        continue

                    pdf_path = Path(pdf_path)
                    if not pdf_path.exists():
                        self.logger.warning(
                            f"Skipping document (PDF not found): {pdf_path}"
                        )
                        result.failed_count += 1
                        continue

                    # Process document through modular pipeline
                    process_result = self._process_document(doc_metadata, pdf_path)

                    # Update counters
                    if process_result["parsed"]:
                        result.parsed_count += 1
                    if process_result["archived"]:
                        result.archived_count += 1
                    if process_result["verified"]:
                        result.verified_count += 1
                    if process_result["rag_indexed"]:
                        result.rag_indexed_count += 1

                except (ParserBackendError, ArchiveError) as e:
                    # document-level fatal errors
                    self.logger.error(
                        f"Document processing failed: {doc_dict.get('title')} - {e}"
                    )
                    result.failed_count += 1
                    result.errors.append(
                        f"{doc_dict.get('title', 'Unknown')}: {str(e)}"
                    )
                    # Continue processing other documents instead of stopping pipeline

                except Exception as e:
                    # Unexpected errors
                    self.logger.error(
                        f"Unexpected error processing document: {doc_dict.get('title')} - {e}"
                    )
                    result.failed_count += 1
                    result.errors.append(
                        f"{doc_dict.get('title', 'Unknown')}: {str(e)}"
                    )

            step_times["process"] = time.perf_counter() - process_start
            self._step_times = step_times
            self.logger.info(
                f"Document processing completed in {step_times['process']:.2f}s: "
                f"{result.parsed_count} parsed, {result.archived_count} archived, "
                f"{result.verified_count} verified, {result.rag_indexed_count} indexed"
            )

            # Determine final status
            if result.failed_count > 0:
                result.status = "partial"
            else:
                result.status = "completed"

        except Exception as e:
            log_exception(
                self.logger,
                e,
                "pipeline.failed",
                scraper=self.scraper_name,
            )
            result.status = "failed"
            result.errors.append(str(e))

        return self._finalize_result(result, start_time)

    def _run_scraper(self):
        """Run the scraper."""
        scraper = ScraperRegistry.get_scraper(
            self.scraper_name,
            max_pages=self.max_pages,
        )

        if not scraper:
            raise ValueError(f"Scraper not found: {self.scraper_name}")

        return scraper.run()

    def _process_document(
        self, doc_metadata: DocumentMetadata, file_path: Path
    ) -> dict:
        """
        Process a single document through the modular pipeline.

        Flow:
        1. Parse PDF → Markdown (using parser backend)
        2. Merge metadata (smart strategy)
        3. Generate canonical filename
        4. Archive to Paperless (using archive backend)
        5. Verify document archived (Sonarr-style)
        6. Ingest Markdown to RAG (using RAG backend)
        7. Delete local files (if verified)

        Args:
            doc_metadata: Document metadata from scraper
            file_path: Path to PDF file

        Returns:
            Dict with keys: parsed, archived, verified, rag_indexed, error

        Raises:
            ParserBackendError: If parsing fails (FAIL FAST)
            ArchiveError: If archiving fails (FAIL FAST)
        """
        result = {
            "parsed": False,
            "archived": False,
            "verified": False,
            "rag_indexed": False,
            "error": None,
        }

        # Step 1: Parse PDF → Markdown
        if not file_path.exists():
            raise ParserBackendError(f"PDF file not found: {file_path}")

        self.logger.info(f"Parsing document: {file_path.name}")
        parser = self.container.parser_backend
        parse_result = parser.parse_document(file_path, doc_metadata)

        if not parse_result.success:
            raise ParserBackendError(
                parse_result.error or "Parser failed without error message"
            )

        result["parsed"] = True
        self.logger.info(
            f"Parse successful: {parse_result.markdown_path.name} "
            f"({parse_result.parser_name})"
        )

        # Step 2: Merge metadata
        merged_metadata = doc_metadata.merge_parser_metadata(
            parse_result.metadata or {},
            strategy=Config.METADATA_MERGE_STRATEGY,
        )
        self.logger.debug(
            f"Metadata merged using '{Config.METADATA_MERGE_STRATEGY}' strategy"
        )

        # Step 3: Generate canonical filename (for archive title)
        canonical_name = generate_filename_from_template(merged_metadata)
        self.logger.debug(f"Canonical filename: {canonical_name}")

        # Step 4: Archive to Paperless (if enabled)
        if self.upload_to_paperless:
            self.logger.info(f"Archiving to Paperless: {canonical_name}")
            archive = self.container.archive_backend

            archive_result = archive.archive_document(
                file_path=file_path,
                title=merged_metadata.title,
                created=merged_metadata.publication_date,
                correspondent=merged_metadata.organization,
                tags=merged_metadata.tags,
                metadata=merged_metadata.to_dict(),
            )

            if not archive_result.success:
                raise ArchiveError(
                    archive_result.error or "Archive failed without error message"
                )

            result["archived"] = True
            self.logger.info(
                f"Archive successful: document_id={archive_result.document_id}"
            )

            # Step 5: Verify document (Sonarr-style)
            self.logger.info("Verifying document in archive...")
            verified = archive.verify_document(
                archive_result.document_id, timeout=self.verify_document_timeout
            )
            result["verified"] = verified

            if verified:
                self.logger.info(f"Document verified: {archive_result.document_id}")
            else:
                self.logger.warning(
                    f"Document verification timed out: {archive_result.document_id}"
                )

        # Step 6: Ingest to RAG (if enabled)
        if self.upload_to_ragflow and self.dataset_id:
            self.logger.info(f"Ingesting to RAG: {parse_result.markdown_path.name}")
            rag = self.container.rag_backend

            rag_result = rag.ingest_document(
                markdown_path=parse_result.markdown_path,
                metadata=merged_metadata.to_dict(),
                collection_id=self.dataset_id,
            )

            # RAG failure is non-fatal (log and continue)
            if rag_result.success:
                result["rag_indexed"] = True
                self.logger.info(f"RAG ingestion successful: {rag_result.document_id}")
            else:
                self.logger.error(f"RAG ingestion failed: {rag_result.error}")
                # Don't raise - RAG failure is non-fatal

        # Step 7: Delete local files (if verified or RAG-only mode)
        should_delete = False
        if self.upload_to_paperless and result["verified"]:
            should_delete = True
        elif not self.upload_to_paperless and result["rag_indexed"]:
            should_delete = True

        if should_delete:
            self.logger.info("Deleting local files (archived/verified)")
            try:
                file_path.unlink()
                if parse_result.markdown_path and parse_result.markdown_path.exists():
                    parse_result.markdown_path.unlink()
                # Delete metadata JSON if exists
                metadata_path = file_path.with_suffix(".json")
                if metadata_path.exists():
                    metadata_path.unlink()
                self.logger.debug("Local files deleted")
            except Exception as e:
                self.logger.warning(f"Failed to delete local files: {e}")

        return result

    def _finalize_result(
        self,
        result: PipelineResult,
        start_time: float,
    ) -> PipelineResult:
        """Finalize the result with timing information."""
        result.duration_seconds = time.perf_counter() - start_time
        result.completed_at = datetime.now().isoformat()

        self.logger.info(
            f"Pipeline completed: {result.status} - "
            f"{result.downloaded_count} downloaded, "
            f"{result.parsed_count} parsed, "
            f"{result.archived_count} archived, "
            f"{result.verified_count} verified, "
            f"{result.rag_indexed_count} indexed, "
            f"{result.failed_count} failed"
        )

        log_event(
            self.logger,
            "info",
            "pipeline.completed",
            scraper=self.scraper_name,
            status=result.status,
            downloaded=result.downloaded_count,
            parsed=result.parsed_count,
            archived=result.archived_count,
            verified=result.verified_count,
            rag_indexed=result.rag_indexed_count,
            failed=result.failed_count,
            duration_s=result.duration_seconds,
            step_times=self._step_times,
        )

        return result


def run_pipeline(
    scraper_name: str,
    dataset_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    upload_to_ragflow: bool = True,
    upload_to_paperless: bool = True,
    verify_document_timeout: int = 60,
) -> PipelineResult:
    """
    Convenience function to run a pipeline.

    Args:
        scraper_name: Name of the scraper
        dataset_id: RAGFlow dataset ID
        max_pages: Maximum pages to scrape
        upload_to_ragflow: Whether to upload to RAGFlow
        upload_to_paperless: Whether to upload to Paperless
        verify_document_timeout: Timeout for archive verification

    Returns:
        PipelineResult with statistics
    """
    pipeline = Pipeline(
        scraper_name=scraper_name,
        dataset_id=dataset_id,
        max_pages=max_pages,
        upload_to_ragflow=upload_to_ragflow,
        upload_to_paperless=upload_to_paperless,
        verify_document_timeout=verify_document_timeout,
    )
    return pipeline.run()
