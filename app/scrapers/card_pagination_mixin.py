"""Mixin for card-list sites with detail-page document discovery."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.utils.errors import ScraperError


class CardListPaginationMixin:
    """Shared logic for scrapers that list cards and follow detail pages for documents.

    Provides:
    - ``_parse_date_dmy``: parse "DD Month YYYY" dates
    - ``_find_documents_on_detail_page``: visit detail page via Selenium and find
      downloadable document URLs matching given extensions and path patterns
    """

    logger: Any = None
    driver: Any = None

    def _parse_date_dmy(self, date_str: str) -> Optional[str]:
        """Parse 'DD Month YYYY' to 'YYYY-MM-DD'.

        Args:
            date_str: e.g. ``"24 December 2025"``

        Returns:
            ISO date string or ``None`` on failure.
        """
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str.strip(), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            if self.logger:
                self.logger.debug(f"Could not parse date: {date_str}")
            return None

    def _find_documents_on_detail_page(
        self,
        detail_url: str,
        extensions: tuple[str, ...] = (".pdf",),
        link_selectors: list[str] | None = None,
        path_patterns: list[str] | None = None,
    ) -> list[str]:
        """Visit a detail page via Selenium and find downloadable document URLs.

        Args:
            detail_url: URL of the detail page to visit.
            extensions: File extensions to match (e.g. ``(".pdf",)`` or
                ``(".pdf", ".docx", ".doc", ".xlsx", ".xls")``).
            link_selectors: Additional CSS selectors for document links (e.g.
                ``[".field--name-field-document a"]``).
            path_patterns: URL path patterns for document links (e.g.
                ``["/sites/default/files/", "/documents/"]``).

        Returns:
            List of absolute document URLs found (deduplicated, order preserved).
        """
        try:
            if self.logger:
                self.logger.debug(f"Fetching detail page: {detail_url}")
            if not self.driver:
                raise ScraperError(
                    "Driver not initialized",
                    scraper=getattr(self, "name", "unknown"),
                )
            assert self.driver is not None
            self.driver.get(detail_url)

            _wait = getattr(self, "_wait_for_content", None)
            if callable(_wait):
                _wait(timeout=15)

            soup = BeautifulSoup(self.get_page_source(), "lxml")
            document_urls: list[str] = []

            # Strategy 1: Find links by extension
            for ext in extensions:
                ext_pattern = re.compile(rf"\.{re.escape(ext[1:])}$", re.I)
                links = soup.find_all("a", href=ext_pattern)
                for link in links:
                    href = link.get("href", "")
                    if href:
                        full_url = urljoin(detail_url, href)
                        if full_url not in document_urls:
                            document_urls.append(full_url)

            # Strategy 2: Custom CSS selectors
            if link_selectors:
                selector_str = ", ".join(link_selectors)
                for link in soup.select(selector_str):
                    href = link.get("href", "")
                    if not href:
                        continue
                    full_url = urljoin(detail_url, href)
                    if full_url.lower().endswith(extensions) and full_url not in document_urls:
                        document_urls.append(full_url)

            # Strategy 3: Path pattern matching
            if path_patterns:
                selector_parts = [f'a[href*="{p}"]' for p in path_patterns]
                for link in soup.select(", ".join(selector_parts)):
                    href = link.get("href", "")
                    if not href:
                        continue
                    href_lower = href.lower()
                    if any(href_lower.endswith(ext) for ext in extensions):
                        full_url = urljoin(detail_url, href)
                        if full_url not in document_urls:
                            document_urls.append(full_url)

            if self.logger:
                if document_urls:
                    self.logger.debug(
                        f"Found {len(document_urls)} documents on detail page"
                    )
                else:
                    self.logger.debug(
                        f"No documents found on detail page: {detail_url}"
                    )

            return document_urls

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error fetching detail page {detail_url}: {e}")
            return []

    if not hasattr(object, "get_page_source"):  # pragma: no cover
        def get_page_source(self) -> str:
            """Stub for type checker — provided by WebDriverLifecycleMixin at runtime."""
            raise NotImplementedError
