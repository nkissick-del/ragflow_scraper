"""
Abstract base class for all scrapers.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import requests

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver  # type: ignore[import-not-found]

from app.config import Config
from app.scrapers.mixins import (
    CloudflareBypassMixin,
    ExclusionAndMetadataMixin,
    IncrementalStateMixin,
    WebDriverLifecycleMixin,
)
from app.utils import get_logger
from app.utils.errors import NetworkError, ScraperError
from app.utils.retry import retry_on_error
from app.services.state_tracker import StateTracker
from app.services.flaresolverr_client import FlareSolverrClient
from app.scrapers.models import DocumentMetadata, ScraperResult


class BaseScraper(
    ExclusionAndMetadataMixin,
    IncrementalStateMixin,
    CloudflareBypassMixin,
    WebDriverLifecycleMixin,
    ABC,
):
    """
    Abstract base class that all scrapers must inherit from.

    Provides common functionality:
    - Selenium WebDriver management
    - State tracking (skip already processed URLs)
    - File downloading with retry logic
    - Metadata sidecar generation
    - Progress reporting
    - Error handling
    """

    # Subclasses must define these
    name: str = "base"
    display_name: str = "Base Scraper"  # Human-readable name for RAGFlow datasets
    description: str = "Base scraper - do not use directly"
    base_url: str = ""

    # Default settings (can be overridden)
    request_delay: float = 1.0  # Seconds between requests
    download_timeout: int = 60
    retry_attempts: int = 3

    # RAGFlow settings (can be overridden per scraper)
    default_chunk_method: str = "paper"  # PDF scrapers use "paper", article scrapers use "naive"
    default_parser: str = "Docling"  # Document parser: DeepDOC, Naive, MinerU, Docling

    # Feed/API scraper mode - skip Selenium, use HTTP session instead
    skip_webdriver: bool = False  # Set True for feed/API scrapers

    # Exclusion filters (subclasses can override)
    # Note: "Gas" exclusion is smart - only excludes gas-only docs, not "Electricity and Gas"
    excluded_tags: list[str] = ["Gas", "Corporate reports"]
    excluded_keywords: list[str] = ["Annual Report", "Budget", "Corporate"]

    # Required tags - if set, documents must have at least one of these tags to be included
    # Used with excluded_tags to implement "gas-only" exclusion logic
    required_tags: list[str] = ["Electricity"]

    def __init__(
        self,
        max_pages: Optional[int] = None,
        dry_run: bool = False,
        force_redownload: bool = False,
        cloudflare_bypass_enabled: bool = False,
    ):
        """
        Initialize the scraper.

        Args:
            max_pages: Maximum number of pages to scrape (None for all)
            dry_run: If True, don't download files, just log what would be done
            force_redownload: If True, redownload even if URL was already processed
            cloudflare_bypass_enabled: If True, use FlareSolverr to bypass Cloudflare
        """
        self.max_pages = max_pages
        self.dry_run = dry_run
        self.force_redownload = force_redownload
        self.cloudflare_bypass_enabled = cloudflare_bypass_enabled

        self.logger = get_logger(self.name)
        from app.container import get_container
        self.state_tracker: StateTracker = get_container().state_tracker(self.name)
        self.driver: Optional[WebDriver] = None

        # Cloudflare bypass state
        self._flaresolverr: Optional[FlareSolverrClient] = None
        self._cloudflare_cookies: dict = {}
        self._cloudflare_user_agent: str = ""
        self._cloudflare_session_id: Optional[str] = None
        self._flaresolverr_html: str = ""  # HTML from FlareSolverr bypass

        # Runtime state
        self._start_time: Optional[float] = None
        self._documents: list[DocumentMetadata] = []
        self._errors: list[str] = []
        self._cancelled: bool = False

        # HTTP session (for skip_webdriver scrapers)
        self._session: Optional[requests.Session] = None

        # Cross-page/category URL deduplication (within a single scrape run)
        self._session_processed_urls: set[str] = set()

        # Incremental scraping support
        self._newest_article_date: Optional[str] = None
        self._from_date: Optional[str] = None

    def cancel(self):
        """Request cancellation of the scraper run."""
        self._cancelled = True
        self.logger.info(f"Cancellation requested for scraper: {self.name}")

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled

    def check_cancelled(self) -> bool:
        """
        Check if cancelled and log if so.

        Scrapers should call this periodically in their scrape() method
        and exit gracefully if it returns True.
        """
        if self._cancelled:
            self.logger.info("Scraper cancelled by user")
            return True
        return False

    @retry_on_error(exceptions=(NetworkError,), max_attempts=3)
    def _request_with_retry(
        self,
        session: requests.Session,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """Perform an HTTP request with standardized retry semantics."""
        timeout = kwargs.pop("timeout", Config.REQUEST_TIMEOUT)
        try:
            response = session.request(method=method, url=url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise NetworkError(
                f"{method.upper()} request failed for {url}",
                scraper=self.name,
                context={"url": url},
            ) from exc
    def _is_processed(self, url: str) -> bool:
        """Check if a URL has already been processed."""
        if self.force_redownload:
            return False
        return self.state_tracker.is_processed(url)

    def _mark_processed(self, url: str, metadata: Optional[dict] = None):
        """Mark a URL as processed."""
        self.state_tracker.mark_processed(url, metadata)

    def _finalize_result(self, result: ScraperResult) -> None:
        """
        Set final status based on error/success counts.

        Call this at the end of scrape() to set appropriate status.

        Args:
            result: ScraperResult to finalize.
        """
        if result.errors and result.downloaded_count == 0:
            result.status = "failed"
        elif result.errors:
            result.status = "partial"
        else:
            result.status = "completed"

    def _polite_delay(self):
        """Wait between requests to be polite to the server."""
        time.sleep(self.request_delay)

    @abstractmethod
    def scrape(self) -> ScraperResult:
        """
        Main entry point - scrape documents and return results.

        Subclasses must implement this method.

        Returns:
            ScraperResult with scraping statistics and document list
        """
        pass

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse a page and extract document metadata.

        Override in HTML-based scrapers. Feed/API scrapers can use the default
        empty implementation since they don't parse HTML pages.

        Args:
            page_source: HTML source of the page

        Returns:
            List of DocumentMetadata objects
        """
        return []

    def run(self) -> ScraperResult:
        """
        Run the scraper with proper setup and teardown.

        Automatically handles:
        - Selenium WebDriver for HTML scrapers (skip_webdriver=False)
        - HTTP Session for feed/API scrapers (skip_webdriver=True)

        Returns:
            ScraperResult with final statistics
        """
        self._start_time = time.time()
        self.logger.info(f"Starting scraper: {self.name}")

        try:
            self.setup()
            result = self.scrape()
        except ScraperError as exc:
            self.logger.error(f"Scraper failed: {exc}", exc_info=True)
            result = ScraperResult(
                status="failed",
                scraper=self.name,
                errors=[str(exc)],
            )
        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result = ScraperResult(
                status="failed",
                scraper=self.name,
                errors=[str(e)],
            )
        finally:
            self.teardown()

        # Finalize result
        result.duration_seconds = time.time() - self._start_time
        result.completed_at = datetime.now().isoformat()
        result.errors.extend(self._errors)

        # Set final status
        if self._cancelled:
            result.status = "cancelled"
        elif result.failed_count > 0 and result.downloaded_count > 0:
            result.status = "partial"
        elif result.failed_count > 0:
            result.status = "failed"
        else:
            result.status = "completed"

        self.logger.info(
            f"Scraper completed: {result.downloaded_count} downloaded, "
            f"{result.skipped_count} skipped, {result.failed_count} failed"
        )

        return result

    def setup(self) -> None:
        """Prepare resources before scrape begins."""
        # Always initialize session for efficient connection reuse
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": f"{self.display_name.replace(' ', '')}Scraper/1.0"}
        )

        if self.skip_webdriver:
            self.logger.debug("Using HTTP session (skip_webdriver=True)")
            # Initialize FlareSolverr page fetch if mixin is present
            init_fs = getattr(self, "_init_flaresolverr_page_fetch", None)
            if callable(init_fs):
                self.logger.info("Initializing FlareSolverr page fetch")
                init_fs()
            return

        self.driver = self._init_driver()

    def teardown(self) -> None:
        """Release resources after scrape ends."""
        try:
            if self._session:
                self._session.close()
                self._session = None

            # Cleanup FlareSolverr page fetch if mixin is present
            cleanup_fs = getattr(self, "_cleanup_flaresolverr_page_fetch", None)
            if callable(cleanup_fs):
                cleanup_fs()

            if self.driver:
                self._close_driver()  # type: ignore
        except Exception as exc:
            # Log driver cleanup errors but don't let them prevent state save
            self.logger.error(f"Error during driver cleanup: {exc}", exc_info=True)
        finally:
            # Always save state, even if cleanup failed
            self.state_tracker.save()

    @classmethod
    def get_metadata(cls) -> dict:
        """Get scraper metadata for registry."""
        return {
            "name": cls.name,
            "display_name": cls.display_name,
            "description": cls.description,
            "base_url": cls.base_url,
            "excluded_tags": cls.excluded_tags,
            "excluded_keywords": cls.excluded_keywords,
            "required_tags": cls.required_tags,
            "default_chunk_method": cls.default_chunk_method,
            "default_parser": cls.default_parser,
        }
