"""Scraper mixins for shared behaviors."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

from app.config import Config
from app.utils import ensure_dir, get_file_hash, sanitize_filename
from app.utils.errors import DownloadError, NetworkError, ScraperError
from app.utils.retry import retry_on_error

if TYPE_CHECKING:
    from app.scrapers.models import DocumentMetadata


class IncrementalStateMixin:
    def _get_last_scrape_date(self) -> Optional[str]:
        key = f"_{self.name}_last_scrape_date"
        state = self.state_tracker.get_state()
        return state.get(key)

    def _update_last_scrape_date(self, date_str: Optional[str] = None) -> None:
        key = f"_{self.name}_last_scrape_date"
        value = date_str or self._newest_article_date or datetime.now().strftime("%Y-%m-%d")
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
    def _should_exclude(self, tags: list[str]) -> bool:
        if not self.excluded_tags:
            return False
        return any(excluded.lower() in [t.lower() for t in tags] for excluded in self.excluded_tags)

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
    def _save_metadata(self, metadata: "DocumentMetadata"):
        metadata_dir = ensure_dir(Config.METADATA_DIR / self.name)
        metadata_file = metadata_dir / f"{sanitize_filename(metadata.filename)}.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

    def _save_article(self, article: "DocumentMetadata", content: str) -> Optional[str]:
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {article.title}")
            return None

        try:
            output_dir = ensure_dir(Config.DOWNLOAD_DIR / self.name)
            safe_filename = sanitize_filename(article.filename)

            md_path = output_dir / f"{safe_filename}.md"
            md_path.write_text(content, encoding="utf-8")

            article.local_path = str(md_path)
            article.file_size = len(content.encode("utf-8"))
            article.hash = get_file_hash(md_path)

            json_path = output_dir / f"{safe_filename}.json"
            json_path.write_text(
                json.dumps(article.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            self.logger.info(f"Saved: {md_path.name}")
            return str(md_path)
        except Exception as exc:
            self.logger.error(f"Failed to save article '{article.title}': {exc}")
            return None


class HttpDownloadMixin:
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
            except requests.RequestException as exc:
                raise NetworkError(
                    f"Failed to fetch {url}",
                    scraper=self.name,
                    context={"url": url},
                ) from exc

            try:
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            except Exception as exc:
                raise DownloadError(
                    f"Failed to write file for {url}",
                    scraper=self.name,
                    recoverable=False,
                    context={"url": url, "path": str(download_path)},
                ) from exc

            self.logger.info(f"Downloaded: {download_path}")

            if metadata:
                metadata.local_path = str(download_path)
                self._save_metadata(metadata)

            return download_path

        try:
            return _attempt_download()
        except ScraperError as exc:
            self.logger.warning(str(exc))
            self._errors.append(str(exc))
            return None


class WebDriverLifecycleMixin:
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

    def _close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as exc:
                self.logger.warning(f"Error closing driver: {exc}")
            self.driver = None


class CloudflareBypassMixin:
    def _init_cloudflare_bypass(self) -> bool:
        if not self.cloudflare_bypass_enabled:
            self.logger.debug("Cloudflare bypass not enabled")
            return False

        if not Config.FLARESOLVERR_URL:
            self.logger.error("FlareSolverr URL is not configured")
            return False

        try:
            self.logger.info("Initializing Cloudflare bypass via FlareSolverr...")
            self._flaresolverr = self._flaresolverr or self._build_flaresolverr()
            result = self._flaresolverr.create_session(self.base_url)

            if not result.success:
                self.logger.error(f"FlareSolverr session creation failed: {result.error}")
                return False

            self._cloudflare_session_id = result.session

            if not self._inject_cloudflare_cookies_to_driver():
                self.logger.warning("Failed to inject Cloudflare cookies; continuing without them")

            self._cloudflare_cookies = {c["name"]: c["value"] for c in result.cookies if "name" in c}
            self._cloudflare_user_agent = result.user_agent
            self.logger.info(f"Extracted {len(self._cloudflare_cookies)} cookies from FlareSolverr")
            self._flaresolverr_html = result.html
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

        self.logger.info(f"Fetching {url} via Selenium")
        self.driver.get(url)

        if hasattr(self, "_wait_for_content"):
            self._wait_for_content()
        else:
            time.sleep(2)

        return self.driver.page_source

    def init_cloudflare_and_fetch_first_page(self) -> tuple[bool, str]:
        page_html = ""

        if self.cloudflare_bypass_enabled:
            bypass_success = self._init_cloudflare_bypass()
            if bypass_success and self.has_cloudflare_session:
                page_html = self.get_flaresolverr_html()
                if page_html and "Just a moment" not in page_html:
                    self.logger.info("Using FlareSolverr HTML directly")
                else:
                    self.logger.warning("FlareSolverr HTML invalid, falling back to Selenium")
                    page_html = ""

        if not page_html:
            self.logger.info(f"Fetching {self.base_url} via Selenium")
            self.driver.get(self.base_url)
            if hasattr(self, "_wait_for_content"):
                self._wait_for_content()
            else:
                time.sleep(2)
            page_html = self.driver.page_source

        if "Just a moment" in page_html:
            self.logger.error("Cloudflare challenge detected. Enable FlareSolverr or try again later.")
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

        if not self._cloudflare_cookies:
            self.logger.debug("No Cloudflare cookies to inject")
            return False

        try:
            self.logger.info("Navigating to domain for cookie injection...")
            self.driver.get(self.base_url)
            time.sleep(1)
            self.driver.delete_all_cookies()

            for name, value in self._cloudflare_cookies.items():
                from urllib.parse import urlparse

                domain = urlparse(self.base_url).netloc
                if domain.startswith("www."):
                    domain = domain[4:]

                cookie = {
                    "name": name,
                    "value": value,
                    "domain": f".{domain}",
                    "path": "/",
                }
                self.driver.add_cookie(cookie)
                self.logger.debug(f"Injected cookie: {name}")

            self.logger.info(f"Injected {len(self._cloudflare_cookies)} cookies into Selenium")
            return True
        except Exception as exc:
            self.logger.error(f"Failed to inject Cloudflare cookies: {exc}")
            return False

    def _build_flaresolverr(self):
        if getattr(self, "_flaresolverr", None):
            return self._flaresolverr
        from app.services.flaresolverr_client import FlareSolverrClient

        settings = getattr(self, "settings_mgr", None)
        timeout = settings.flaresolverr_timeout if settings else Config.FLARESOLVERR_TIMEOUT
        max_timeout = settings.flaresolverr_max_timeout if settings else Config.FLARESOLVERR_MAX_TIMEOUT
        return FlareSolverrClient(url=Config.FLARESOLVERR_URL, timeout=timeout, max_timeout=max_timeout)


class ExclusionAndMetadataMixin(ExclusionRulesMixin, MetadataIOMixin, HttpDownloadMixin):
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
