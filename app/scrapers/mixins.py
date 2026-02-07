"""Scraper mixins for shared behaviors."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any, List, Dict, cast

import requests
from selenium import webdriver  # type: ignore[import]
from selenium.webdriver.chrome.options import Options  # type: ignore[import]
from selenium.webdriver.remote.webdriver import WebDriver  # type: ignore[import]

from app.config import Config
from app.utils import (
    ensure_dir,
    get_content_hash,
    sanitize_filename,
    CHUNK_SIZE,
)
from app.utils.errors import DownloadError, NetworkError, ScraperError
from app.utils.retry import retry_on_error

if TYPE_CHECKING:
    from app.scrapers.models import DocumentMetadata


class IncrementalStateMixin:
    """Mixin to track incremental scraping state.

    Notes: inheriting scrapers should provide `name: str` and `state_tracker`.
    """

    name: str = ""  # Provided by inheriting class
    state_tracker: Any = None  # Provided by inheriting class
    _newest_article_date: Optional[str] = None
    logger: Any = None

    def _get_last_scrape_date(self) -> Optional[str]:
        key = f"_{self.name}_last_scrape_date"
        state = self.state_tracker.get_state()
        return state.get(key)

    def _update_last_scrape_date(self, date_str: Optional[str] = None) -> None:
        key = f"_{self.name}_last_scrape_date"
        value = (
            date_str or self._newest_article_date or datetime.now().strftime("%Y-%m-%d")
        )
        self.state_tracker.set_value(key, value)
        self.state_tracker.save()

    def _track_article_date(self, date_str: Optional[str]) -> None:
        if not date_str:
            return
        if self._newest_article_date is None or date_str > self._newest_article_date:
            self._newest_article_date = date_str

    def _parse_iso_date(self, date_str: str) -> Optional[str]:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None


class ExclusionRulesMixin:
    # Common configuration attributes expected on scrapers that use this mixin
    excluded_tags: Optional[List[str]] = None
    required_tags: Optional[List[str]] = None
    excluded_keywords: Optional[List[str]] = None
    logger: Any = None

    def _should_exclude(self, tags: list[str]) -> bool:
        if not self.excluded_tags:
            return False

        lower_tags = {t.lower() for t in tags}
        return any(excluded.lower() in lower_tags for excluded in self.excluded_tags)

    def should_exclude_document(self, doc: "DocumentMetadata") -> Optional[str]:
        tags_lower = [t.lower() for t in doc.tags] if doc.tags else []
        has_required_tag = False
        if self.required_tags and tags_lower:
            for required in self.required_tags:
                if required.lower() in tags_lower:
                    has_required_tag = True
                    break

        if self.excluded_tags and tags_lower:
            for excluded in self.excluded_tags:
                if excluded.lower() in tags_lower:
                    if has_required_tag:
                        continue
                    return f"tag: {excluded}"

        if self.required_tags and tags_lower and not has_required_tag:
            return f"missing required tag: {self.required_tags}"

        if self.excluded_keywords and doc.title:
            title_lower = doc.title.lower()
            for keyword in self.excluded_keywords:
                if keyword.lower() in title_lower:
                    return f"keyword: {keyword}"
        return None


class MetadataIOMixin:
    # Expected attributes from the host scraper
    dry_run: bool = False
    logger: Any = None
    # Name of the scraper (used for directories)
    name: str = ""

    def _save_metadata(self, metadata: "DocumentMetadata"):
        metadata_dir = ensure_dir(Config.METADATA_DIR / self.name)
        metadata_file = metadata_dir / f"{sanitize_filename(metadata.filename)}.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

    def _save_article(
        self,
        article: "DocumentMetadata",
        content: str,
        html_content: Optional[str] = None,
    ) -> Optional[str]:
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {article.title}")
            return None

        output_dir = ensure_dir(Config.DOWNLOAD_DIR / self.name)

        # Save raw HTML for pipeline Gotenberg conversion (replaces Selenium archiver)
        temp_html_path = None
        if html_content:
            try:
                safe_fn = sanitize_filename(article.filename)
                temp_html_path = output_dir / f"{safe_fn}.html"
                temp_html_path.write_text(html_content, encoding="utf-8")
            except Exception as e:
                self.logger.error(f"Failed to save HTML for '{article.title}': {e}")
                temp_html_path = None

        temp_md_path = None
        temp_json_path = None

        try:
            safe_filename = sanitize_filename(article.filename)

            # Write to temporary files first (atomic write pattern)
            temp_md_path = output_dir / f".{safe_filename}.md.tmp"
            temp_json_path = output_dir / f".{safe_filename}.json.tmp"

            # Encode content once
            content_bytes = content.encode("utf-8")

            # Write markdown to temp file
            temp_md_path.write_bytes(content_bytes)

            # Compute metadata from content bytes
            file_size = len(content_bytes)
            file_hash = get_content_hash(content_bytes)

            # Prepare metadata with computed values (without mutating article yet)
            article_dict = article.to_dict()
            article_dict["local_path"] = str(output_dir / f"{safe_filename}.md")
            article_dict["file_size"] = file_size
            article_dict["hash"] = file_hash

            # Write JSON to temp file
            temp_json_path.write_text(
                json.dumps(article_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Both writes succeeded - now atomically move temp files to final locations
            md_path = output_dir / f"{safe_filename}.md"
            json_path = output_dir / f"{safe_filename}.json"

            try:
                # Rename JSON first (safest: if this fails, MD is not yet moved)
                temp_json_path.rename(json_path)
                temp_md_path.rename(md_path)
            except Exception:
                # Clean up JSON if MD rename failed to avoid orphaned files
                if json_path.exists():
                    json_path.unlink()
                raise

            # Only mutate article after all file operations succeed
            article.local_path = str(md_path)
            article.file_size = file_size
            article.hash = file_hash
            if temp_html_path:
                if not hasattr(article, "extra") or article.extra is None:
                    article.extra = {}
                article.extra["html_path"] = str(temp_html_path)

            self.logger.info(f"Saved: {md_path.name}")
            return str(md_path)
        except Exception as exc:
            self.logger.error(f"Failed to save article '{article.title}': {exc}")
            # Clean up temp files if they exist
            if temp_md_path and temp_md_path.exists():
                temp_md_path.unlink()
            if temp_json_path and temp_json_path.exists():
                temp_json_path.unlink()
            return None


class HttpDownloadMixin:
    # Expected attributes
    dry_run: bool = False
    download_timeout: int = 30

    def __init__(self):
        super().__init__()
        self._errors: List[str] = []

    logger: Any = None
    name: str = ""

    # Provide a metadata save hook signature so Pylance knows this exists
    def _save_metadata(
        self, metadata: "DocumentMetadata"
    ) -> None:  # pragma: no cover - overridden by MetadataIOMixin
        raise NotImplementedError()

    def _download_file(
        self,
        url: str,
        filename: str,
        metadata: Optional["DocumentMetadata"] = None,
    ) -> Optional[Path]:
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would download: {url}")
            return None

        safe_filename = sanitize_filename(filename)
        download_path = ensure_dir(Config.DOWNLOAD_DIR / self.name) / safe_filename

        @retry_on_error(exceptions=(NetworkError, DownloadError), max_attempts=None)
        def _attempt_download() -> Path:
            try:
                self.logger.info(f"Downloading: {url}")
                response = requests.get(
                    url,
                    timeout=self.download_timeout,
                    stream=True,
                    headers={"User-Agent": "Mozilla/5.0 PDF Scraper"},
                )
                response.raise_for_status()
            except requests.RequestException:
                raise NetworkError(
                    f"Failed to fetch {url}",
                    scraper=self.name,
                    context={"url": url},
                )

            try:
                hash_obj = hashlib.sha256()
                file_size = 0
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                        hash_obj.update(chunk)
                        file_size += len(chunk)
            except Exception:
                raise DownloadError(
                    f"Failed to write file for {url}",
                    scraper=self.name,
                    recoverable=False,
                    context={"url": url, "path": str(download_path)},
                )

            self.logger.info(f"Downloaded: {download_path}")

            if metadata:
                metadata.local_path = str(download_path)
                metadata.hash = hash_obj.hexdigest()
                # Update file_size if not already present or if different (trust actual download size)
                if metadata.file_size is None or metadata.file_size == 0:
                    metadata.file_size = file_size

                self._save_metadata(metadata)

            return download_path

        try:
            return _attempt_download()
        except ScraperError as exc:
            self.logger.warning(str(exc))
            self._errors.append(str(exc))
            return None


class WebDriverLifecycleMixin:
    # Expected attributes
    driver: Optional[WebDriver] = None
    logger: Any = None

    def _init_driver(self) -> WebDriver:
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

    def get_page_source(self) -> str:
        """Return page source from the Selenium driver, raising if driver missing."""
        if not self.driver:
            raise ScraperError(
                "Driver not initialized", scraper=getattr(self, "name", "unknown")
            )
        assert self.driver is not None
        return self.driver.page_source

    def _close_driver(self) -> None:
        """Close and cleanup the Selenium WebDriver if it exists."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception as exc:
                self.logger.warning(f"Error closing WebDriver: {exc}")
            finally:
                self.driver = None


class CloudflareBypassMixin:
    # Expected attributes provided by host scraper
    cloudflare_bypass_enabled: bool = False
    _flaresolverr: Any = None
    _cloudflare_session_id: Optional[str] = None
    _cloudflare_user_agent: str = ""
    _flaresolverr_html: str = ""
    logger: Any = None
    driver: Optional[WebDriver] = None
    base_url: str = ""
    settings_mgr: Any = None
    _wait_for_content: Optional[Any] = None

    def __init__(self) -> None:
        """Initialize instance attributes to prevent cross-instance sharing."""
        super().__init__()
        self._cloudflare_cookies: Dict[str, str] = {}

    if TYPE_CHECKING:  # provide stub for type checker without affecting runtime MRO

        def get_page_source(self) -> str: ...

    def _init_cloudflare_bypass(self) -> bool:
        if not self.cloudflare_bypass_enabled:
            self.logger.debug("Cloudflare bypass not enabled")
            return False

        if not Config.FLARESOLVERR_URL:
            self.logger.error("FlareSolverr URL is not configured")
            return False

        try:
            self.logger.info("Initializing Cloudflare bypass via FlareSolverr...")
            self._flaresolverr = cast(
                Any, self._flaresolverr or self._build_flaresolverr()
            )

            # Create a session id and request FlareSolverr to create it. The
            # FlareSolverr client returns a boolean for session creation, and
            # subsequent get_page() calls return a FlareSolverResult with the
            # cookies/html/user_agent we need.
            session_id = f"scraper_session_{int(time.time())}"
            try:
                created = bool(self._flaresolverr.create_session(session_id))
            except Exception:
                created = False

            if not created:
                self.logger.error("FlareSolverr session creation failed")
                return False

            # Store session id and attempt to fetch an initial page to extract cookies
            self._cloudflare_session_id = session_id

            result = self._flaresolverr.get_page(self.base_url, session_id=session_id)
            if not getattr(result, "success", False):
                self.logger.error(
                    f"FlareSolverr failed to fetch initial page: {getattr(result, 'error', '')}"
                )
                return False

            # Extract session artifacts
            self._cloudflare_cookies = {
                c["name"]: c["value"]
                for c in getattr(result, "cookies", [])
                if "name" in c
            }
            self._cloudflare_user_agent = getattr(result, "user_agent", "")
            self.logger.info(
                f"Extracted {len(self._cloudflare_cookies)} cookies from FlareSolverr"
            )
            self._flaresolverr_html = getattr(result, "html", "")
            return True
        except Exception as exc:
            self.logger.error(f"Cloudflare bypass failed: {exc}")
            return False

    def get_flaresolverr_html(self) -> str:
        return self._flaresolverr_html

    def fetch_page_via_flaresolverr(self, url: str) -> str:
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
        if use_cached and self._flaresolverr_html:
            if "Just a moment" not in self._flaresolverr_html:
                self.logger.debug("Using cached FlareSolverr HTML")
                return self._flaresolverr_html

        if self.cloudflare_bypass_enabled and self.has_cloudflare_session:
            self.logger.info(f"Fetching {url} via FlareSolverr")
            html = self.fetch_page_via_flaresolverr(url)
            if html and "Just a moment" not in html:
                return html
            self.logger.warning("FlareSolverr fetch failed, falling back to Selenium")

        if not self.driver:
            raise ScraperError(
                "Driver not initialized", scraper=getattr(self, "name", "unknown")
            )

        # Narrow type for static checker
        assert self.driver is not None

        self.logger.info(f"Fetching {url} via Selenium")
        self.driver.get(url)

        _wait = getattr(self, "_wait_for_content", None)
        if callable(_wait):
            _wait()
        else:
            time.sleep(2)

        return self.get_page_source()

    def init_cloudflare_and_fetch_first_page(self) -> tuple[bool, str]:
        page_html = ""

        if self.cloudflare_bypass_enabled:
            bypass_success = self._init_cloudflare_bypass()
            if bypass_success and self.has_cloudflare_session:
                page_html = self.get_flaresolverr_html()
                if page_html and "Just a moment" not in page_html:
                    self.logger.info("Using FlareSolverr HTML directly")
                else:
                    self.logger.warning(
                        "FlareSolverr HTML invalid, falling back to Selenium"
                    )
                    page_html = ""

        if not page_html:
            self.logger.info(f"Fetching {self.base_url} via Selenium")
            if not self.driver:
                raise ScraperError(
                    "Driver not initialized", scraper=getattr(self, "name", "unknown")
                )
            assert self.driver is not None
            self.driver.get(self.base_url)
            _wait = getattr(self, "_wait_for_content", None)
            if callable(_wait):
                _wait()
            else:
                time.sleep(2)
            page_html = self.get_page_source()

        if "Just a moment" in page_html:
            self.logger.error(
                "Cloudflare challenge detected. Enable FlareSolverr or try again later."
            )
            return False, page_html

        return True, page_html

    def get_cloudflare_cookies(self) -> dict:
        return self._cloudflare_cookies.copy()

    def get_cloudflare_user_agent(self) -> str:
        return self._cloudflare_user_agent

    @property
    def has_cloudflare_session(self) -> bool:
        return bool(self._cloudflare_cookies)

    def _inject_cloudflare_cookies_to_driver(self) -> bool:
        if not self.driver:
            self.logger.error("Cannot inject cookies - driver not initialized")
            return False

        # Help type checker understand driver is present beyond this point
        assert self.driver is not None

        if not self._cloudflare_cookies:
            self.logger.debug("No Cloudflare cookies to inject")
            return False

        try:
            self.logger.info("Navigating to domain for cookie injection...")
            self.driver.get(self.base_url)
            time.sleep(1)
            self.driver.delete_all_cookies()

            from urllib.parse import urlparse

            domain = urlparse(self.base_url).netloc
            if domain.startswith("www."):
                domain = domain[4:]

            for name, value in self._cloudflare_cookies.items():
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": f".{domain}",
                    "path": "/",
                }
                self.driver.add_cookie(cookie)
                self.logger.debug(f"Injected cookie: {name}")

            self.logger.info(
                f"Injected {len(self._cloudflare_cookies)} cookies into Selenium"
            )
            return True
        except Exception as exc:
            self.logger.error(f"Failed to inject Cloudflare cookies: {exc}")
            return False

    def _build_flaresolverr(self):
        if getattr(self, "_flaresolverr", None):
            return self._flaresolverr
        from app.services.flaresolverr_client import FlareSolverrClient

        settings = getattr(self, "settings_mgr", None)
        timeout = (
            settings.flaresolverr_timeout if settings else Config.FLARESOLVERR_TIMEOUT
        )
        max_timeout = (
            settings.flaresolverr_max_timeout
            if settings
            else Config.FLARESOLVERR_MAX_TIMEOUT
        )
        return FlareSolverrClient(
            url=Config.FLARESOLVERR_URL, timeout=timeout, max_timeout=max_timeout
        )


class ExclusionAndMetadataMixin(
    ExclusionRulesMixin, MetadataIOMixin, HttpDownloadMixin
):
    """Convenience mixin grouping exclusion + IO."""

    pass


__all__ = [
    "IncrementalStateMixin",
    "ExclusionRulesMixin",
    "MetadataIOMixin",
    "HttpDownloadMixin",
    "WebDriverLifecycleMixin",
    "CloudflareBypassMixin",
    "ExclusionAndMetadataMixin",
]
