"""
State reconciliation and disaster recovery service.

Provides three-way reconciliation between:
- Local state files (which URLs a scraper has processed)
- Paperless-ngx archive (source of truth for stored documents)
- RAG backend (vector index for search/retrieval)
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import Config
from app.scrapers.models import DocumentMetadata
from app.utils import get_logger

if TYPE_CHECKING:
    from app.services.container import ServiceContainer


@dataclass
class ReconciliationReport:
    """Report from a three-way reconciliation check."""

    scraper_name: str
    state_url_count: int = 0
    paperless_url_count: int = 0
    rag_document_count: int = 0
    urls_only_in_state: list[str] = field(default_factory=list)
    urls_only_in_paperless: list[str] = field(default_factory=list)
    urls_in_paperless_not_rag: list[str] = field(default_factory=list)
    urls_added_to_state: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "scraper_name": self.scraper_name,
            "state_url_count": self.state_url_count,
            "paperless_url_count": self.paperless_url_count,
            "rag_document_count": self.rag_document_count,
            "urls_only_in_state": self.urls_only_in_state,
            "urls_only_in_paperless": self.urls_only_in_paperless,
            "urls_in_paperless_not_rag": self.urls_in_paperless_not_rag,
            "urls_added_to_state": self.urls_added_to_state,
            "errors": self.errors,
        }


class ReconciliationService:
    """
    Service for reconciling scraper state with Paperless and RAG backends.

    Supports:
    - Pre-flight sync: add missing URLs to state from Paperless before scraping
    - Full state rebuild: rebuild state from Paperless (disaster recovery)
    - Three-way report: compare state, Paperless, and RAG
    - RAG gap sync: re-ingest documents missing from RAG
    """

    def __init__(self, container: ServiceContainer):
        self.container = container
        self.logger = get_logger("reconciliation")

    def _get_paperless_client(self):
        """Get the Paperless client, raising if not configured."""
        try:
            archive = self.container.archive_backend
            # The Paperless adapter exposes its client
            client = getattr(archive, "client", None)
            if client is None:
                raise RuntimeError("Archive backend has no Paperless client")
            if not client.is_configured:
                raise RuntimeError("Paperless client is not configured")
            return client
        except Exception as e:
            raise RuntimeError(f"Cannot access Paperless client: {e}") from e

    def preflight_sync(self, scraper_name: str) -> int:
        """
        Pre-flight reconciliation: sync state from Paperless.

        Called before every scraper run. Adds URLs known to Paperless
        but missing from local state, preventing re-downloads.

        Args:
            scraper_name: Scraper to sync

        Returns:
            Number of URLs added to state (0 if nothing to add or Paperless unavailable)
        """
        try:
            client = self._get_paperless_client()
        except RuntimeError:
            return 0

        if not client.check_alive():
            self.logger.debug("Paperless not reachable, skipping pre-flight sync")
            return 0

        paperless_urls = client.get_scraper_document_urls(scraper_name)
        tracker = self.container.state_tracker(scraper_name)
        state_urls = set(tracker.get_processed_urls())

        # Fast path: if all Paperless URLs are already in state, skip
        if set(paperless_urls.keys()) <= state_urls:
            return 0

        added = 0
        for url in paperless_urls:
            if url not in state_urls:
                tracker.mark_processed(url, status="reconciled")
                added += 1

        if added > 0:
            tracker.save()
            self.logger.info(
                f"Pre-flight sync for '{scraper_name}': added {added} URLs to state"
            )

        return added

    def rebuild_state(self, scraper_name: str) -> int:
        """
        Full state rebuild from Paperless (disaster recovery).

        Unlike preflight_sync, always runs full comparison (no fast path).

        Args:
            scraper_name: Scraper to rebuild state for

        Returns:
            Number of URLs added to state
        """
        client = self._get_paperless_client()

        paperless_urls = client.get_scraper_document_urls(scraper_name)
        tracker = self.container.state_tracker(scraper_name)
        state_urls = set(tracker.get_processed_urls())

        added = 0
        for url in paperless_urls:
            if url not in state_urls:
                tracker.mark_processed(url, status="reconciled")
                added += 1

        if added > 0:
            tracker.save()

        self.logger.info(
            f"State rebuild for '{scraper_name}': "
            f"{added} URLs added, {len(state_urls)} already in state"
        )
        return added

    def get_report(self, scraper_name: str) -> ReconciliationReport:
        """
        Generate a three-way reconciliation report.

        Compares state, Paperless, and RAG to find discrepancies.

        Args:
            scraper_name: Scraper to report on

        Returns:
            ReconciliationReport with all discrepancy details
        """
        report = ReconciliationReport(scraper_name=scraper_name)

        # Get state URLs
        tracker = self.container.state_tracker(scraper_name)
        state_urls = set(tracker.get_processed_urls())
        report.state_url_count = len(state_urls)

        # Get Paperless URLs
        paperless_urls: dict[str, int] = {}
        try:
            client = self._get_paperless_client()
            paperless_urls = client.get_scraper_document_urls(scraper_name)
            report.paperless_url_count = len(paperless_urls)
        except RuntimeError as e:
            report.errors.append(f"Paperless unavailable: {e}")

        # Get RAG documents
        rag_urls: set[str] = set()
        try:
            rag = self.container.rag_backend
            dataset_id = Config.RAGFLOW_DATASET_ID
            if dataset_id:
                rag_docs = rag.list_documents(collection_id=dataset_id)
                report.rag_document_count = len(rag_docs)
                for doc in rag_docs:
                    # Try to extract source URL from metadata
                    meta = doc.get("metadata", {}) or {}
                    source_url = meta.get("source_url") or meta.get("url")
                    if source_url:
                        rag_urls.add(source_url)
                    # Also try document name as fallback
                    doc_name = doc.get("name", "")
                    if doc_name:
                        rag_urls.add(doc_name)
        except Exception as e:
            report.errors.append(f"RAG listing failed: {e}")

        # Compute set differences
        paperless_url_set = set(paperless_urls.keys())

        report.urls_only_in_state = sorted(state_urls - paperless_url_set)
        report.urls_only_in_paperless = sorted(paperless_url_set - state_urls)

        # URLs in Paperless but not in RAG
        if rag_urls:
            report.urls_in_paperless_not_rag = sorted(paperless_url_set - rag_urls)
        elif paperless_urls and report.rag_document_count == 0:
            # RAG is empty but Paperless has docs — all are missing
            report.urls_in_paperless_not_rag = sorted(paperless_url_set)

        return report

    def sync_rag_gaps(
        self, scraper_name: str, dry_run: bool = True
    ) -> list[str]:
        """
        Re-ingest documents from Paperless that are missing from RAG.

        Downloads PDFs from Paperless, parses them, and ingests the
        markdown into the RAG backend.

        Args:
            scraper_name: Scraper to sync
            dry_run: If True, only return the list of URLs that would be synced

        Returns:
            List of URLs that were (or would be) re-ingested
        """
        report = self.get_report(scraper_name)
        gap_urls = report.urls_in_paperless_not_rag

        if not gap_urls:
            self.logger.info(f"No RAG gaps found for '{scraper_name}'")
            return []

        if dry_run:
            self.logger.info(
                f"Dry run: {len(gap_urls)} documents would be re-ingested for '{scraper_name}'"
            )
            return gap_urls

        client = self._get_paperless_client()
        paperless_urls = client.get_scraper_document_urls(scraper_name)

        from app.config import Config
        dataset_id = Config.RAGFLOW_DATASET_ID

        re_ingested: list[str] = []
        parser = self.container.parser_backend
        rag = self.container.rag_backend

        for url in gap_urls:
            doc_id = paperless_urls.get(url)
            if doc_id is None:
                self.logger.warning(f"No Paperless doc ID for URL: {url}")
                continue

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Download from Paperless
                    pdf_bytes = client.download_document(doc_id)
                    if not pdf_bytes:
                        self.logger.error(f"Failed to download document {doc_id}")
                        continue

                    temp_path = Path(tmpdir) / f"doc_{doc_id}.pdf"
                    temp_path.write_bytes(pdf_bytes)

                    # Parse (provide minimal context metadata)
                    context = DocumentMetadata(
                        url=url,
                        title=temp_path.stem,
                        filename=temp_path.name,
                    )
                    parse_result = parser.parse_document(temp_path, context)
                    if not parse_result.success or not parse_result.markdown_path:
                        self.logger.error(
                            f"Parse failed for document {doc_id}: {parse_result.error}"
                        )
                        continue

                    # Ingest to RAG
                    metadata = {"url": url, "source": "reconciliation"}
                    rag_result = rag.ingest_document(
                        content_path=parse_result.markdown_path,
                        metadata=metadata,
                        collection_id=dataset_id,
                    )

                    if rag_result.success:
                        re_ingested.append(url)
                        self.logger.info(f"Re-ingested: {url}")
                    else:
                        self.logger.error(
                            f"RAG ingest failed for {url}: {rag_result.error}"
                        )

            except Exception as e:
                self.logger.error(f"Failed to re-ingest {url}: {e}")

        self.logger.info(
            f"RAG sync for '{scraper_name}': "
            f"{len(re_ingested)}/{len(gap_urls)} documents re-ingested"
        )
        return re_ingested
