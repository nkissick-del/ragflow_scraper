"""
Pipeline execution for scrape -> upload -> parse workflows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import Config
from app.scrapers import ScraperRegistry
from app.services import RAGFlowClient, StateTracker
from app.utils import get_logger


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""

    status: str  # "completed", "partial", "failed"
    scraper_name: str
    scraped_count: int = 0
    downloaded_count: int = 0
    uploaded_count: int = 0
    parsed_count: int = 0
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
            "uploaded_count": self.uploaded_count,
            "parsed_count": self.parsed_count,
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
        wait_for_parsing: bool = True,
    ):
        """
        Initialize the pipeline.

        Args:
            scraper_name: Name of the scraper to run
            dataset_id: RAGFlow dataset ID (uses config if not provided)
            max_pages: Maximum pages to scrape
            upload_to_ragflow: Whether to upload to RAGFlow
            wait_for_parsing: Whether to wait for parsing to complete
        """
        self.scraper_name = scraper_name
        self.dataset_id = dataset_id or Config.RAGFLOW_DATASET_ID
        self.max_pages = max_pages
        self.upload_to_ragflow = upload_to_ragflow
        self.wait_for_parsing = wait_for_parsing

        self.logger = get_logger(f"pipeline.{scraper_name}")
        self.ragflow = RAGFlowClient() if upload_to_ragflow else None

    def run(self) -> PipelineResult:
        """
        Execute the full pipeline.

        Returns:
            PipelineResult with statistics
        """
        import time
        start_time = time.time()

        result = PipelineResult(
            status="running",
            scraper_name=self.scraper_name,
        )

        try:
            # Step 1: Run scraper
            self.logger.info("Step 1: Running scraper...")
            scraper_result = self._run_scraper()

            result.scraped_count = scraper_result.scraped_count
            result.downloaded_count = scraper_result.downloaded_count
            result.errors.extend(scraper_result.errors)

            if scraper_result.status == "failed":
                result.status = "failed"
                result.errors.append("Scraper failed")
                return self._finalize_result(result, start_time)

            if result.downloaded_count == 0:
                self.logger.info("No new documents downloaded, skipping upload")
                result.status = "completed"
                return self._finalize_result(result, start_time)

            # Step 2: Upload to RAGFlow
            if self.upload_to_ragflow and self.dataset_id:
                self.logger.info("Step 2: Uploading to RAGFlow...")
                upload_result = self._upload_to_ragflow()
                result.uploaded_count = upload_result["uploaded"]
                result.failed_count += upload_result["failed"]

                if upload_result["failed"] > 0:
                    result.errors.append(
                        f"{upload_result['failed']} documents failed to upload"
                    )

                # Step 3: Trigger parsing
                if result.uploaded_count > 0:
                    self.logger.info("Step 3: Triggering parsing...")
                    if self._trigger_parsing():
                        # Step 4: Wait for parsing
                        if self.wait_for_parsing:
                            self.logger.info("Step 4: Waiting for parsing...")
                            if self._wait_for_parsing():
                                result.parsed_count = result.uploaded_count
                            else:
                                result.errors.append("Parsing did not complete")
                    else:
                        result.errors.append("Failed to trigger parsing")

            # Determine final status
            if result.failed_count > 0:
                result.status = "partial"
            else:
                result.status = "completed"

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
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

    def _upload_to_ragflow(self) -> dict[str, int]:
        """Upload downloaded documents to RAGFlow."""
        if not self.ragflow or not self.dataset_id:
            return {"uploaded": 0, "failed": 0}

        # Get list of downloaded files
        download_dir = Config.DOWNLOAD_DIR / self.scraper_name
        if not download_dir.exists():
            return {"uploaded": 0, "failed": 0}

        files = list(download_dir.glob("*.pdf"))
        if not files:
            return {"uploaded": 0, "failed": 0}

        # Upload files
        results = self.ragflow.upload_documents(self.dataset_id, files)

        uploaded = sum(1 for r in results if r.success)
        failed = len(results) - uploaded

        return {"uploaded": uploaded, "failed": failed}

    def _trigger_parsing(self) -> bool:
        """Trigger parsing in RAGFlow."""
        if not self.ragflow or not self.dataset_id:
            return False

        return self.ragflow.trigger_parsing(self.dataset_id)

    def _wait_for_parsing(self) -> bool:
        """Wait for parsing to complete."""
        if not self.ragflow or not self.dataset_id:
            return False

        return self.ragflow.wait_for_parsing(self.dataset_id)

    def _finalize_result(
        self,
        result: PipelineResult,
        start_time: float,
    ) -> PipelineResult:
        """Finalize the result with timing information."""
        import time
        result.duration_seconds = time.time() - start_time
        result.completed_at = datetime.now().isoformat()

        self.logger.info(
            f"Pipeline completed: {result.status} - "
            f"{result.downloaded_count} downloaded, "
            f"{result.uploaded_count} uploaded, "
            f"{result.parsed_count} parsed, "
            f"{result.failed_count} failed"
        )

        return result


def run_pipeline(
    scraper_name: str,
    dataset_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    upload_to_ragflow: bool = True,
    wait_for_parsing: bool = True,
) -> PipelineResult:
    """
    Convenience function to run a pipeline.

    Args:
        scraper_name: Name of the scraper
        dataset_id: RAGFlow dataset ID
        max_pages: Maximum pages to scrape
        upload_to_ragflow: Whether to upload to RAGFlow
        wait_for_parsing: Whether to wait for parsing

    Returns:
        PipelineResult with statistics
    """
    pipeline = Pipeline(
        scraper_name=scraper_name,
        dataset_id=dataset_id,
        max_pages=max_pages,
        upload_to_ragflow=upload_to_ragflow,
        wait_for_parsing=wait_for_parsing,
    )
    return pipeline.run()
