"""
Abstract base class for all scrapers.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import requests

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options

from app.config import Config
from app.utils import get_logger, sanitize_filename, ensure_dir, get_file_hash
from app.services.state_tracker import StateTracker
from app.services.flaresolverr_client import FlareSolverrClient


@dataclass
class DocumentMetadata:
    """Metadata for a scraped document."""

    url: str
    title: str
    filename: str
    file_size: Optional[int] = None
    file_size_str: Optional[str] = None
    publication_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source_page: Optional[str] = None
    organization: Optional[str] = None
    document_type: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    local_path: Optional[str] = None
    hash: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_ragflow_metadata(self) -> dict:
        """
        Extract only RAGFlow-compatible metadata fields.

        Returns standard fields that will be pushed to RAGFlow as document metadata.
        Per RAGFlow docs: "If a parameter does not exist or is None, it won't be updated"
        - Required fields always included (organization, source_url, scraped_at, document_type)
        - Optional fields (publication_date, author, abstract) only included if present
        """
        metadata = {
            "organization": self.organization or "Unknown",
            "source_url": self.url,
            "scraped_at": self.scraped_at,
            "document_type": self.document_type or "Unknown",
        }

        # Add optional fields only if they have actual values
        if self.publication_date:
            metadata["publication_date"] = self.publication_date

        if self.extra.get("author"):
            metadata["author"] = self.extra["author"]

        # Abstract with fallback chain
        abstract = self.extra.get("abstract") or self.extra.get("description")
        if abstract:
            metadata["abstract"] = abstract

        return metadata


@dataclass
class ExcludedDocument:
    """Record of an excluded document with reason."""

    title: str
    url: str
    reason: str  # e.g., "keyword: Gas", "tag: Annual Report", "already processed"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ScraperResult:
    """Result from a scraper run."""

    status: str  # "completed", "failed", "partial", "cancelled"
    scraper: str
    scraped_count: int = 0
    downloaded_count: int = 0
    uploaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    excluded_count: int = 0  # Documents filtered by keywords/tags
    duration_seconds: float = 0.0
    documents: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)  # Excluded documents with reasons
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class BaseScraper(ABC):
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
    default_parser: str = "DeepDOC"  # Document parser: DeepDOC, Naive, MinerU, Docling

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
        self.state_tracker = StateTracker(self.name)
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

    # Incremental scraping methods
    def _get_last_scrape_date(self) -> Optional[str]:
        """
        Get last scrape date from state for incremental mode.

        Returns:
            Date string in YYYY-MM-DD format, or None if not set.
        """
        key = f"_{self.name}_last_scrape_date"
        state = self.state_tracker.get_state()
        return state.get(key)

    def _update_last_scrape_date(self, date_str: Optional[str] = None) -> None:
        """
        Update last scrape date in state.

        Args:
            date_str: Date to set (YYYY-MM-DD format), or None to use
                      newest article date or current date.
        """
        key = f"_{self.name}_last_scrape_date"
        value = date_str or self._newest_article_date or datetime.now().strftime("%Y-%m-%d")
        self.state_tracker.set_value(key, value)
        self.state_tracker.save()

    def _track_article_date(self, date_str: Optional[str]) -> None:
        """
        Track newest article date for incremental scraping.

        Call this for each article processed to track the most recent date.
        At the end of the run, this becomes the new from_date for next run.

        Args:
            date_str: Date string in YYYY-MM-DD format.
        """
        if not date_str:
            return
        if self._newest_article_date is None or date_str > self._newest_article_date:
            self._newest_article_date = date_str

    def _parse_iso_date(self, date_str: str) -> Optional[str]:
        """
        Parse ISO 8601 date to YYYY-MM-DD format.

        Handles various ISO formats:
        - 2024-01-15
        - 2024-01-15T10:30:00
        - 2024-01-15T10:30:00Z
        - 2024-01-15T10:30:00+00:00

        Args:
            date_str: ISO 8601 formatted date string.

        Returns:
            Date in YYYY-MM-DD format, or None if parsing fails.
        """
        if not date_str:
            return None
        try:
            clean = date_str.split("+")[0].split("Z")[0]
            if "T" in clean:
                clean = clean.split("T")[0]
            # Validate format
            datetime.strptime(clean, "%Y-%m-%d")
            return clean
        except (ValueError, IndexError):
            return None

    # Cloudflare bypass methods (infrastructure layer)
    def _init_cloudflare_bypass(self) -> bool:
        """
        Attempt to bypass Cloudflare using FlareSolverr.

        Uses FlareSolverr to solve Cloudflare challenges and extract cookies
        that can be used for subsequent HTTP requests.

        Returns:
            True if bypass was successful and cookies are available,
            False if bypass is disabled, not configured, or failed.
        """
        if not self.cloudflare_bypass_enabled:
            self.logger.debug("Cloudflare bypass not enabled for this scraper")
            return False

        # Initialize FlareSolverr client if needed
        if self._flaresolverr is None:
            self._flaresolverr = FlareSolverrClient()

        if not self._flaresolverr.is_enabled:
            self.logger.info("FlareSolverr not enabled globally, skipping bypass")
            return False

        # Generate session ID for this scraper instance
        import time as time_module
        self._cloudflare_session_id = f"{self.name}_{int(time_module.time())}"

        self.logger.info(f"Using FlareSolverr to bypass Cloudflare for {self.base_url}...")

        # Get page through FlareSolverr to solve the challenge
        result = self._flaresolverr.get_page(
            self.base_url,
            session_id=self._cloudflare_session_id,
            max_timeout=120,
        )

        if not result.success:
            self.logger.error(f"FlareSolverr failed: {result.error}")
            return False

        # Check if we got actual content (not a challenge page)
        if "Just a moment" in result.html or len(result.html) < 1000:
            self.logger.warning("FlareSolverr may not have fully solved the challenge")
            return False

        self.logger.info(f"FlareSolverr bypassed Cloudflare, got {len(result.html)} bytes")

        # Extract cookies for subsequent requests
        self._cloudflare_cookies = {
            c["name"]: c["value"] for c in result.cookies if "name" in c
        }
        self._cloudflare_user_agent = result.user_agent

        self.logger.info(f"Extracted {len(self._cloudflare_cookies)} cookies from FlareSolverr")

        # Store the HTML for scrapers that can use it directly
        self._flaresolverr_html = result.html
        return True

    def get_flaresolverr_html(self) -> str:
        """
        Get the HTML content from the last FlareSolverr bypass.

        This allows scrapers to use the already-fetched HTML instead of
        making another request through Selenium (which may hit Cloudflare again).

        Returns:
            HTML string, or empty string if no bypass was performed.
        """
        return self._flaresolverr_html

    def fetch_page_via_flaresolverr(self, url: str) -> str:
        """
        Fetch a page via FlareSolverr.

        This is useful for pagination where you need to fetch additional pages
        through the Cloudflare bypass.

        Args:
            url: URL to fetch (can include hash fragments)

        Returns:
            HTML content, or empty string if failed.
        """
        if not self.cloudflare_bypass_enabled or not self._flaresolverr:
            return ""

        result = self._flaresolverr.get_page(
            url,
            session_id=self._cloudflare_session_id,
            max_timeout=120,
        )

        if result.success:
            self._flaresolverr_html = result.html
            return result.html

        self.logger.warning(f"FlareSolverr failed to fetch {url}: {result.error}")
        return ""

    def fetch_page(self, url: str, use_cached: bool = False) -> str:
        """
        Fetch a page using the best available method.

        This is the recommended method for scrapers to fetch pages. It automatically:
        1. Uses cached FlareSolverr HTML if available and use_cached=True
        2. Tries FlareSolverr if Cloudflare bypass is enabled
        3. Falls back to Selenium if FlareSolverr fails or is disabled

        Args:
            url: URL to fetch
            use_cached: If True and we have cached HTML from the initial bypass,
                        return that instead of fetching again (useful for first page)

        Returns:
            HTML content of the page

        Raises:
            RuntimeError: If page cannot be fetched and contains Cloudflare challenge
        """
        # Check for cached HTML first (from initial bypass)
        if use_cached and self._flaresolverr_html:
            if "Just a moment" not in self._flaresolverr_html:
                self.logger.debug("Using cached FlareSolverr HTML")
                return self._flaresolverr_html

        # Try FlareSolverr if enabled
        if self.cloudflare_bypass_enabled and self.has_cloudflare_session:
            self.logger.info(f"Fetching {url} via FlareSolverr")
            html = self.fetch_page_via_flaresolverr(url)
            if html and "Just a moment" not in html:
                return html
            self.logger.warning("FlareSolverr fetch failed, falling back to Selenium")

        # Fallback to Selenium
        self.logger.info(f"Fetching {url} via Selenium")
        self.driver.get(url)

        # Wait for page to load (subclasses can override _wait_for_content)
        if hasattr(self, '_wait_for_content'):
            self._wait_for_content()
        else:
            import time as time_module
            time_module.sleep(2)

        return self.driver.page_source

    def init_cloudflare_and_fetch_first_page(self) -> tuple[bool, str]:
        """
        Initialize Cloudflare bypass and fetch the first page.

        This is a convenience method that combines:
        1. Initializing FlareSolverr bypass (if enabled)
        2. Fetching the first page (via FlareSolverr or Selenium)
        3. Checking for Cloudflare challenges

        Returns:
            Tuple of (success, html):
            - success: True if page was fetched without Cloudflare block
            - html: The page HTML content

        Example usage in a scraper's scrape() method:
            success, page_html = self.init_cloudflare_and_fetch_first_page()
            if not success:
                result.status = "failed"
                result.errors.append("Cloudflare challenge blocked access")
                return result
        """
        page_html = ""

        # Try FlareSolverr bypass first
        if self.cloudflare_bypass_enabled:
            bypass_success = self._init_cloudflare_bypass()
            if bypass_success and self.has_cloudflare_session:
                page_html = self.get_flaresolverr_html()
                if page_html and "Just a moment" not in page_html:
                    self.logger.info("Using FlareSolverr HTML directly")
                else:
                    self.logger.warning("FlareSolverr HTML invalid, falling back to Selenium")
                    page_html = ""

        # Fall back to Selenium if needed
        if not page_html:
            self.logger.info(f"Fetching {self.base_url} via Selenium")
            self.driver.get(self.base_url)
            if hasattr(self, '_wait_for_content'):
                self._wait_for_content()
            else:
                import time as time_module
                time_module.sleep(2)
            page_html = self.driver.page_source

        # Check for Cloudflare challenge
        if "Just a moment" in page_html:
            self.logger.error("Cloudflare challenge detected. Enable FlareSolverr or try again later.")
            return False, page_html

        return True, page_html

    def get_cloudflare_cookies(self) -> dict:
        """
        Get cookies from the Cloudflare bypass session.

        Returns:
            Dict of cookie name -> value, or empty dict if no session.
        """
        return self._cloudflare_cookies.copy()

    def get_cloudflare_user_agent(self) -> str:
        """
        Get the user agent from the Cloudflare bypass session.

        Returns:
            User agent string, or empty string if no session.
        """
        return self._cloudflare_user_agent

    @property
    def has_cloudflare_session(self) -> bool:
        """Check if a valid Cloudflare bypass session exists."""
        return bool(self._cloudflare_cookies)

    def _inject_cloudflare_cookies_to_driver(self) -> bool:
        """
        Inject Cloudflare bypass cookies into the Selenium WebDriver.

        This must be called AFTER the driver has navigated to the target domain
        (even if just to a simple page), as cookies are domain-specific.

        The approach:
        1. First navigate to the base URL (may hit Cloudflare challenge)
        2. Clear any existing cookies
        3. Add the FlareSolverr cookies
        4. Refresh/navigate again - now with valid cookies

        Returns:
            True if cookies were injected successfully, False otherwise.
        """
        if not self.driver:
            self.logger.error("Cannot inject cookies - driver not initialized")
            return False

        if not self._cloudflare_cookies:
            self.logger.debug("No Cloudflare cookies to inject")
            return False

        try:
            # Navigate to domain first (required for setting cookies)
            # Use a minimal request to avoid challenge
            self.logger.info("Navigating to domain for cookie injection...")
            self.driver.get(self.base_url)

            # Small wait for page to start loading
            import time as time_module
            time_module.sleep(1)

            # Delete existing cookies and add FlareSolverr cookies
            self.driver.delete_all_cookies()

            for name, value in self._cloudflare_cookies.items():
                try:
                    # Selenium requires domain to be set for the cookie
                    from urllib.parse import urlparse
                    domain = urlparse(self.base_url).netloc
                    # Remove 'www.' prefix if present for broader cookie matching
                    if domain.startswith("www."):
                        domain = domain[4:]

                    cookie = {
                        "name": name,
                        "value": value,
                        "domain": f".{domain}",  # Leading dot for subdomain matching
                        "path": "/",
                    }
                    self.driver.add_cookie(cookie)
                    self.logger.debug(f"Injected cookie: {name}")
                except Exception as e:
                    self.logger.warning(f"Failed to inject cookie {name}: {e}")

            self.logger.info(f"Injected {len(self._cloudflare_cookies)} cookies into Selenium")
            return True

        except Exception as e:
            self.logger.error(f"Failed to inject Cloudflare cookies: {e}")
            return False

    def _init_driver(self) -> WebDriver:
        """Initialize Selenium WebDriver."""
        options = Options()
        if Config.SELENIUM_HEADLESS:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        self.logger.info(f"Connecting to Selenium at {Config.SELENIUM_REMOTE_URL}")
        driver = webdriver.Remote(
            command_executor=Config.SELENIUM_REMOTE_URL,
            options=options,
        )
        driver.implicitly_wait(10)
        return driver

    def _close_driver(self):
        """Close the Selenium WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.warning(f"Error closing driver: {e}")
            self.driver = None

    def _is_processed(self, url: str) -> bool:
        """Check if a URL has already been processed."""
        if self.force_redownload:
            return False
        return self.state_tracker.is_processed(url)

    def _mark_processed(self, url: str, metadata: Optional[dict] = None):
        """Mark a URL as processed."""
        self.state_tracker.mark_processed(url, metadata)

    def _should_exclude(self, tags: list[str]) -> bool:
        """
        Check if document should be excluded based on tags.

        DEPRECATED: Use should_exclude_document() instead for better reporting.
        """
        if not self.excluded_tags:
            return False
        return any(
            excluded.lower() in [t.lower() for t in tags]
            for excluded in self.excluded_tags
        )

    def should_exclude_document(self, doc: DocumentMetadata) -> Optional[str]:
        """
        Check if a document should be excluded based on tags or title keywords.

        This method implements smart exclusion logic:
        1. If required_tags is set, document must have at least one required tag
        2. Tags in excluded_tags only exclude if NO required_tags are present
           (e.g., "Gas" only excludes gas-only docs, not "Electricity and Gas")
        3. Keywords always exclude based on title substring match

        Args:
            doc: DocumentMetadata to check

        Returns:
            Exclusion reason string if should be excluded (e.g., "keyword: Gas"),
            or None if document should be included.
        """
        tags_lower = [t.lower() for t in doc.tags] if doc.tags else []

        # Check if document has any required tags
        has_required_tag = False
        if self.required_tags and tags_lower:
            for required in self.required_tags:
                if required.lower() in tags_lower:
                    has_required_tag = True
                    break

        # Check excluded tags - but only exclude if NO required tags present
        # This implements "gas-only" exclusion: "Electricity and Gas" is kept,
        # but "Gas" alone is excluded
        if self.excluded_tags and tags_lower:
            for excluded in self.excluded_tags:
                if excluded.lower() in tags_lower:
                    # If document has a required tag, don't exclude based on this tag
                    if has_required_tag:
                        continue
                    return f"tag: {excluded}"

        # If required_tags is set but document has none of them, exclude
        if self.required_tags and tags_lower and not has_required_tag:
            return f"missing required tag: {self.required_tags}"

        # Check title keywords (always excludes, regardless of other tags)
        if self.excluded_keywords and doc.title:
            title_lower = doc.title.lower()
            for keyword in self.excluded_keywords:
                if keyword.lower() in title_lower:
                    return f"keyword: {keyword}"

        return None

    def _download_file(
        self,
        url: str,
        filename: str,
        metadata: Optional[DocumentMetadata] = None,
    ) -> Optional[Path]:
        """
        Download a file with retry logic.

        Args:
            url: URL to download
            filename: Filename to save as
            metadata: Optional metadata to save as sidecar

        Returns:
            Path to downloaded file, or None if failed
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would download: {url}")
            return None

        safe_filename = sanitize_filename(filename)
        download_path = ensure_dir(Config.DOWNLOAD_DIR / self.name) / safe_filename

        for attempt in range(self.retry_attempts):
            try:
                self.logger.info(f"Downloading: {url}")
                response = requests.get(
                    url,
                    timeout=self.download_timeout,
                    stream=True,
                    headers={"User-Agent": "Mozilla/5.0 PDF Scraper"},
                )
                response.raise_for_status()

                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.logger.info(f"Downloaded: {download_path}")

                # Save metadata sidecar
                if metadata:
                    metadata.local_path = str(download_path)
                    self._save_metadata(metadata)

                return download_path

            except Exception as e:
                self.logger.warning(
                    f"Download attempt {attempt + 1}/{self.retry_attempts} failed: {e}"
                )
                if attempt < self.retry_attempts - 1:
                    time.sleep(2**attempt)  # Exponential backoff

        self._errors.append(f"Failed to download {url} after {self.retry_attempts} attempts")
        return None

    def _save_metadata(self, metadata: DocumentMetadata):
        """Save metadata as a JSON sidecar file."""
        metadata_dir = ensure_dir(Config.METADATA_DIR / self.name)
        metadata_file = metadata_dir / f"{sanitize_filename(metadata.filename)}.json"

        with open(metadata_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

    def _save_article(
        self,
        article: DocumentMetadata,
        content: str,
    ) -> Optional[str]:
        """
        Save article as Markdown with JSON sidecar.

        This is the standard method for feed/API scrapers to save articles.
        Creates both:
        - {filename}.md - Pure Markdown content (no frontmatter)
        - {filename}.json - Full metadata sidecar

        Args:
            article: Document metadata (must have filename, title, url, publication_date)
            content: Markdown content (will be saved as-is)

        Returns:
            Path to saved .md file, or None on failure.
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {article.title}")
            return None

        try:
            output_dir = ensure_dir(Config.DOWNLOAD_DIR / self.name)
            safe_filename = sanitize_filename(article.filename)

            # Save markdown file (pure content, no frontmatter)
            md_path = output_dir / f"{safe_filename}.md"
            md_path.write_text(content, encoding="utf-8")

            # Update article metadata with local path and hash
            article.local_path = str(md_path)
            article.file_size = len(content.encode("utf-8"))
            article.hash = get_file_hash(md_path)

            # Save JSON sidecar
            json_path = output_dir / f"{safe_filename}.json"
            json_path.write_text(
                json.dumps(article.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            self.logger.info(f"Saved: {md_path.name}")
            return str(md_path)

        except Exception as e:
            self.logger.error(f"Failed to save article '{article.title}': {e}")
            return None

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
            if self.skip_webdriver:
                # HTTP-only mode for feed/API scrapers
                self._session = requests.Session()
                self._session.headers.update({
                    "User-Agent": f"{self.display_name.replace(' ', '')}Scraper/1.0"
                })
                self.logger.debug("Using HTTP session (skip_webdriver=True)")
            else:
                # Selenium mode for HTML scrapers
                self.driver = self._init_driver()

            result = self.scrape()
        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result = ScraperResult(
                status="failed",
                scraper=self.name,
                errors=[str(e)],
            )
        finally:
            if self.skip_webdriver and self._session:
                self._session.close()
                self._session = None
            elif self.driver:
                self._close_driver()
            self.state_tracker.save()

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
