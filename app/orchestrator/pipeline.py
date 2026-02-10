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
    Pipeline for executing the full scrape -> parse -> archive workflow.

    Steps:
    1. Run scraper to download documents
    2. Parse documents locally using configured parser backend
    3. Archive parsed documents to Paperless (with verification)
    4. Optionally upload/ingest parsed content to RAG backend
    5. Monitor archive status and clean up local files after verification
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
            verify_document_timeout: Timeout in seconds for archive document verification (default: 60)
            container: Optional service container (uses default if not provided)
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
            # Pre-flight reconciliation (self-healing state from Paperless)
            if self.upload_to_paperless:
                try:
                    from app.services.reconciliation import ReconciliationService

                    recon = ReconciliationService(container=self.container)
                    added = recon.preflight_sync(self.scraper_name)
                    if added > 0:
                        self.logger.info(
                            f"Pre-flight: added {added} URLs to state from Paperless"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Pre-flight reconciliation failed (non-fatal): {e}"
                    )

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

                    # Get file path (may be PDF, markdown, or other format)
                    file_path_str = doc_dict.get("pdf_path") or doc_dict.get("local_path")
                    if not file_path_str:
                        self.logger.warning(
                            f"Skipping document (no file path): {doc_dict.get('title')}"
                        )
                        result.failed_count += 1
                        continue

                    file_path = Path(file_path_str)
                    if not file_path.exists():
                        self.logger.warning(
                            f"Skipping document (file not found): {file_path}"
                        )
                        result.failed_count += 1
                        continue

                    # Process document through modular pipeline
                    process_result = self._process_document(
                        doc_metadata, file_path, doc_dict
                    )

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

    # Format classification constants
    _MARKDOWN_FORMATS = {".md", ".markdown"}
    _OFFICE_FORMATS = {
        ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".odt", ".ods", ".odp", ".rtf", ".csv",
    }

    def _detect_document_type(self, file_path: Path) -> str:
        """
        Detect document type for routing.

        Returns:
            'markdown', 'pdf', or 'office'
        """
        suffix = file_path.suffix.lower()
        if suffix in self._MARKDOWN_FORMATS:
            return "markdown"
        if suffix == ".pdf":
            return "pdf"
        return "office"

    def _process_document(
        self,
        doc_metadata: DocumentMetadata,
        file_path: Path,
        doc_dict: dict | None = None,
    ) -> dict:
        """
        Process a single document through the modular pipeline.

        Supports three document flows:
        - 'pdf': Parse with configured parser backend → archive original PDF
        - 'markdown': Skip parsing (already markdown) → Gotenberg MD→PDF for archive
        - 'office': Parse with Tika → Gotenberg for PDF archive

        Args:
            doc_metadata: Document metadata from scraper
            file_path: Path to document file (PDF, markdown, or office)
            doc_dict: Original document dict (for extra paths like html_path)

        Returns:
            Dict with keys: parsed, archived, verified, rag_indexed, error

        Raises:
            ParserBackendError: If parsing fails (FAIL FAST)
            ArchiveError: If archiving fails (FAIL FAST)
        """
        doc_dict = doc_dict or {}
        result = {
            "parsed": False,
            "archived": False,
            "verified": False,
            "rag_indexed": False,
            "error": None,
        }

        if not file_path.exists():
            raise ParserBackendError(f"File not found: {file_path}")

        doc_type = self._detect_document_type(file_path)
        self.logger.info(f"Processing document ({doc_type}): {file_path.name}")

        # Step 1: Parse → Markdown
        md_path, parse_metadata = self._parse_document(file_path, doc_metadata, doc_type)
        result["parsed"] = True

        # Step 2: Merge metadata
        merge_strategy = Config.METADATA_MERGE_STRATEGY
        override = self.container.settings.get("pipeline.metadata_merge_strategy", "")
        if override:
            merge_strategy = override
        merged_metadata = doc_metadata.merge_parser_metadata(
            parse_metadata, strategy=merge_strategy,  # type: ignore[arg-type]
        )
        self.logger.debug(f"Metadata merged using '{merge_strategy}' strategy")

        # Step 3: Generate canonical filename
        canonical_name = generate_filename_from_template(merged_metadata)
        self.logger.debug(f"Canonical filename: {canonical_name}")

        # Step 4: Prepare archive PDF (Gotenberg conversion for non-PDF)
        archive_file_path, archive_pdf_path = self._prepare_archive_file(
            file_path, md_path, doc_type, merged_metadata)

        # Step 5: Archive (if enabled)
        if self.upload_to_paperless:
            document_id = self._archive_document(archive_file_path, merged_metadata)

            if document_id:
                result["archived"] = True
                result["verified"] = self._verify_document(document_id)
            else:
                error_msg = (
                    "Archive backend returned success but no document_id. "
                    "This indicates an anomalous backend state."
                )
                self.logger.error(error_msg)
                result["error"] = error_msg

        # Step 6: RAG ingestion (if enabled)
        if self.upload_to_ragflow and self.dataset_id:
            result["rag_indexed"] = self._ingest_to_rag(md_path, merged_metadata)

        # Step 7: Cleanup
        self._cleanup_local_files(file_path, md_path, archive_pdf_path, doc_dict, result)

        return result

    def _parse_document(
        self,
        file_path: Path,
        doc_metadata: DocumentMetadata,
        doc_type: str,
    ) -> tuple[Path, dict]:
        """
        Parse document to markdown based on type.

        Returns:
            (md_path, parse_metadata) — path to markdown file and extracted metadata dict

        Raises:
            ParserBackendError: If parsing fails (FAIL FAST)
        """
        md_path: Path
        parse_metadata: dict = {}

        if doc_type == "markdown":
            # Markdown already exists — skip parsing
            md_path = file_path
            self.logger.info(
                f"Markdown file detected, skipping parse: {file_path.name}"
            )

        elif doc_type == "office":
            # Use Tika for office formats (regardless of PARSER_BACKEND setting)
            self.logger.info(
                f"Office file detected, parsing with Tika: {file_path.name}"
            )
            if not Config.TIKA_SERVER_URL:
                raise ParserBackendError(
                    f"Tika not configured (TIKA_SERVER_URL required) "
                    f"for office format: {file_path.name}"
                )
            tika = self.container.tika_client
            text = tika.extract_text(file_path)

            if not text or not text.strip():
                raise ParserBackendError(
                    f"Tika returned empty text for {file_path.name}"
                )

            tika_meta = tika.extract_metadata(file_path)
            parse_metadata = tika_meta

            # Convert to markdown
            title = (
                tika_meta.get("title")
                or doc_metadata.title
                or file_path.stem
            )
            md_content = self._text_to_markdown(text, title=title)
            md_path = file_path.with_suffix(".md")
            md_path.write_text(md_content, encoding="utf-8")

            self.logger.info(f"Tika parse successful: {md_path.name}")

        else:
            # PDF path — use configured parser backend
            self.logger.info(f"Parsing document: {file_path.name}")
            parser = self.container.parser_backend
            parse_result = parser.parse_document(file_path, doc_metadata)

            if not parse_result.success:
                raise ParserBackendError(
                    parse_result.error or "Parser failed without error message"
                )

            if not parse_result.markdown_path:
                error_msg = (
                    f"Parser '{parse_result.parser_name}' succeeded "
                    f"but returned no markdown_path"
                )
                if parse_result.error:
                    error_msg += f": {parse_result.error}"
                raise ParserBackendError(error_msg)

            md_path = parse_result.markdown_path
            parse_metadata = parse_result.metadata or {}
            self.logger.info(
                f"Parse successful: {md_path.name} ({parse_result.parser_name})"
            )

        # Tika enrichment (optional, after parse, before archive)
        self._run_tika_enrichment(file_path, parse_metadata, doc_type)

        # LLM enrichment (optional, after parse, before archive)
        self._run_llm_enrichment(md_path, parse_metadata)

        return md_path, parse_metadata

    def _prepare_archive_file(
        self,
        file_path: Path,
        md_path: Path,
        doc_type: str,
        merged_metadata: DocumentMetadata,
    ) -> tuple[Path, Path | None]:
        """
        Prepare file for archive upload (Gotenberg PDF conversion if needed).

        Returns:
            (archive_file_path, archive_pdf_path) — archive_pdf_path is None if no
            conversion was done (tracks generated file for cleanup)
        """
        archive_pdf_path: Path | None = None

        if doc_type == "pdf":
            return file_path, None
        elif self.upload_to_paperless and Config.GOTENBERG_URL:
            try:
                gotenberg = self.container.gotenberg_client
                if doc_type == "markdown":
                    pdf_bytes = gotenberg.convert_markdown_to_pdf(
                        md_path.read_text(encoding="utf-8"),
                        title=merged_metadata.title or "",
                    )
                else:  # office
                    pdf_bytes = gotenberg.convert_to_pdf(file_path)

                archive_pdf_path = file_path.with_suffix(".archive.pdf")
                archive_pdf_path.write_bytes(pdf_bytes)
                self.logger.info(
                    f"Gotenberg PDF generated: {archive_pdf_path.name}"
                )
                return archive_pdf_path, archive_pdf_path
            except Exception as e:
                self.logger.error(f"Gotenberg PDF conversion failed: {e}")
                return file_path, None  # Fall back to original
        else:
            return file_path, None

    def _archive_document(
        self,
        archive_file_path: Path,
        merged_metadata: DocumentMetadata,
    ) -> str | None:
        """
        Archive document to backend.

        Returns:
            document_id (str or None if backend returned success but no ID)

        Raises:
            ArchiveError: If archive backend returns failure (FAIL FAST)
        """
        self.logger.info(f"Archiving to Paperless: {archive_file_path.name}")
        archive = self.container.archive_backend

        # Inject scraper_name into metadata for Paperless custom field
        metadata_dict = merged_metadata.to_dict()
        metadata_dict["scraper_name"] = self.scraper_name

        archive_result = archive.archive_document(
            file_path=archive_file_path,
            title=merged_metadata.title,
            created=merged_metadata.publication_date,
            correspondent=merged_metadata.organization,
            tags=merged_metadata.tags,
            metadata=metadata_dict,
        )

        if not archive_result.success:
            raise ArchiveError(
                archive_result.error or "Archive failed without error message"
            )

        self.logger.info(
            f"Archive successful: document_id={archive_result.document_id}"
        )
        return archive_result.document_id

    def _verify_document(
        self,
        document_id: str,
    ) -> bool:
        """
        Verify document exists in archive (polling with timeout).

        Returns:
            True if verified, False if timed out
        """
        self.logger.info("Verifying document in archive...")
        archive = self.container.archive_backend
        verified = archive.verify_document(
            document_id,
            timeout=self.verify_document_timeout,
        )

        if verified:
            self.logger.info(f"Document verified: {document_id}")
        else:
            self.logger.warning(
                f"Document verification timed out: {document_id}"
            )

        return verified

    def _ingest_to_rag(
        self,
        md_path: Path,
        merged_metadata: DocumentMetadata,
    ) -> bool:
        """
        Ingest markdown to RAG backend (non-fatal).

        Returns:
            True if ingestion succeeded, False otherwise
        """
        self.logger.info(f"Ingesting to RAG: {md_path.name}")
        rag = self.container.rag_backend

        rag_result = rag.ingest_document(
            markdown_path=md_path,
            metadata=merged_metadata.to_dict(),
            collection_id=self.dataset_id,
        )

        if rag_result.success:
            self.logger.info(
                f"RAG ingestion successful: {rag_result.document_id}"
            )
            return True
        else:
            self.logger.error(f"RAG ingestion failed: {rag_result.error}")
            return False

    def _cleanup_local_files(
        self,
        file_path: Path,
        md_path: Path,
        archive_pdf_path: Path | None,
        doc_dict: dict,
        result: dict,
    ) -> None:
        """
        Delete local files if document was successfully archived/verified or RAG-indexed.
        Non-fatal — logs warnings on failure.
        """
        should_delete = False
        if self.upload_to_paperless and result["verified"]:
            should_delete = True
        elif not self.upload_to_paperless and result["rag_indexed"]:
            should_delete = True

        if not should_delete:
            if (
                self.upload_to_paperless
                and not result["verified"]
                and result.get("rag_indexed")
            ):
                self.logger.warning(
                    "RAG ingestion succeeded but Paperless verification "
                    "did not — skipping local file cleanup"
                )
            return

        self.logger.info("Deleting local files (archived/verified)")
        try:
            if file_path.exists():
                file_path.unlink()
            if md_path and md_path.exists() and md_path != file_path:
                md_path.unlink()
            # Delete metadata JSON if exists
            metadata_path = file_path.with_suffix(".json")
            if metadata_path.exists():
                metadata_path.unlink()
            # Clean up Gotenberg-generated archive PDF
            if archive_pdf_path and archive_pdf_path.exists():
                archive_pdf_path.unlink()
            # Clean up HTML file saved by scraper
            extra = doc_dict.get("extra", {}) or {}
            html_path_str = extra.get("html_path")
            if html_path_str:
                html_path = Path(html_path_str)
                if html_path.exists():
                    html_path.unlink()
            self.logger.debug("Local files deleted")
        except Exception as e:
            self.logger.warning(f"Failed to delete local files: {e}")

    def _run_tika_enrichment(self, file_path: Path, parse_metadata: dict, doc_type: str):
        """Run optional Tika metadata enrichment (fill-gaps strategy)."""
        enrichment_enabled = Config.TIKA_ENRICHMENT_ENABLED
        override = self.container.settings.get("pipeline.tika_enrichment_enabled", "")
        if override != "":
            enrichment_enabled = override == "true"

        if enrichment_enabled and Config.TIKA_SERVER_URL:
            if doc_type != "office":
                try:
                    tika_meta = self.container.tika_client.extract_metadata(
                        file_path
                    )
                    for key, value in tika_meta.items():
                        if key not in parse_metadata:
                            parse_metadata[key] = value
                    self.logger.debug("Tika enrichment applied")
                except Exception as e:
                    self.logger.warning(
                        f"Tika enrichment failed (non-fatal): {e}"
                    )

    def _run_llm_enrichment(self, md_path: Path, parse_metadata: dict):
        """Run optional LLM metadata enrichment (fill-gaps strategy)."""
        enrichment_enabled = Config.LLM_ENRICHMENT_ENABLED
        override = self.container.settings.get("pipeline.llm_enrichment_enabled", "")
        if override != "":
            enrichment_enabled = override.lower() == "true"

        if not enrichment_enabled:
            return

        try:
            llm_client = self.container.llm_client
            if not llm_client.is_configured():
                self.logger.debug("LLM client not configured, skipping enrichment")
                return

            from app.services.document_enrichment import DocumentEnrichmentService

            max_tokens = Config.LLM_ENRICHMENT_MAX_TOKENS
            service = DocumentEnrichmentService(llm_client, max_tokens=max_tokens)
            enriched = service.enrich_metadata(md_path)

            if not enriched:
                return

            # Fill-gaps merge for direct fields
            for key in ("title", "document_type"):
                if key in enriched and key not in parse_metadata:
                    parse_metadata[key] = enriched[key]

            # Store LLM-specific fields in extra dict
            if "extra" not in parse_metadata:
                parse_metadata["extra"] = {}

            for src_key, dest_key in [
                ("summary", "llm_summary"),
                ("keywords", "llm_keywords"),
                ("entities", "llm_entities"),
                ("key_topics", "llm_topics"),
            ]:
                if src_key in enriched:
                    value = enriched[src_key]
                    # Convert lists to comma-separated strings for Paperless custom fields
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    parse_metadata["extra"][dest_key] = value

            # Merge suggested_tags into tags list (deduped)
            suggested_tags = enriched.get("suggested_tags", [])
            if suggested_tags and isinstance(suggested_tags, list):
                existing_tags = parse_metadata.get("tags", [])
                if not isinstance(existing_tags, list):
                    self.logger.debug(
                        "Existing tags not a list (type: %s), resetting to empty list",
                        type(existing_tags).__name__,
                    )
                    existing_tags = []
                existing_lower = {t.lower() for t in existing_tags}
                for tag in suggested_tags:
                    if isinstance(tag, str) and tag.lower() not in existing_lower:
                        existing_tags.append(tag)
                        existing_lower.add(tag.lower())
                parse_metadata["tags"] = existing_tags

            self.logger.info("LLM enrichment applied")
        except Exception as e:
            self.logger.warning(f"LLM enrichment failed (non-fatal): {e}")

    @staticmethod
    def _text_to_markdown(text: str, title: str | None = None) -> str:
        """Convert plain text to minimal markdown with title heading."""
        lines: list[str] = []
        if title:
            lines.append(f"# {title}")
            lines.append("")
        paragraphs = text.split("\n\n")
        for para in paragraphs:
            cleaned = para.strip()
            if cleaned:
                lines.append(cleaned)
                lines.append("")
        return "\n".join(lines)

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
