"""
AEMO (Australian Energy Market Operator) scraper for major publications.

Scrapes PDFs from: https://www.aemo.com.au/library/major-publications

Uses FlareSolverr for rendered page fetching. Hash-fragment pagination
loads each page as a fresh FlareSolverr request with the hash in the URL.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin
from app.scrapers.models import DocumentMetadata, ScraperResult, ExcludedDocument
from app.utils import sanitize_filename, parse_file_size


class AEMOScraper(FlareSolverrPageFetchMixin, BaseScraper):
    """
    Scraper for AEMO Major Publications.

    Key features:
    - Uses FlareSolverr for rendered page fetching
    - JavaScript-rendered page with hash fragment pagination
    - Each page loaded as a fresh FlareSolverr request with hash fragment
    - Documents listed in <ul class="search-result-list">
    - Tag-based filtering (excludes Gas, Annual Report, etc.)
    - Metadata extraction (title, date, size, file type)
    """

    name = "aemo"
    display_name = "Australian Energy Market Operator"
    description = "Scrapes PDFs from AEMO Major Publications"
    base_url = "https://www.aemo.com.au/library/major-publications"

    skip_webdriver = True  # Use FlareSolverr instead of Selenium

    # AEMO-specific settings
    documents_per_page = 10
    request_delay = 2.0  # Be polite

    # Uses base class exclusion defaults:
    # - excluded_tags: ["Gas", "Corporate reports"]
    # - excluded_keywords: ["Annual Report", "Budget", "Corporate"]
    # - required_tags: ["Electricity"] (smart gas-only filtering)

    def __init__(self, *args, **kwargs):
        """Initialize AEMO scraper."""
        super().__init__(*args, **kwargs)
        # Will be set dynamically when we detect total pages
        self._initial_offset: Optional[int] = None
        self._total_pages: Optional[int] = None

    def _detect_pagination_info_from_html(self, html: str) -> tuple[int, int]:
        """
        Detect the total pages from the page HTML.

        Args:
            html: HTML content to parse

        Returns:
            Tuple of (starting_offset, total_pages)
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Try to find pagination links (they may be JS-rendered)
            page_links = soup.select(".search-result-paging a, .pagination a, [class*=paging] a")
            max_page = 1

            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    page_num = int(text)
                    if page_num > max_page:
                        max_page = page_num

            if max_page > 1:
                self.logger.info(f"Detected {max_page} total pages from pagination")
                return 0, max_page

            # Pagination not found in HTML (JS-rendered) - use default
            default_pages = 22
            self.logger.info(f"Pagination not found in HTML, using default of {default_pages} pages")
            return 0, default_pages

        except Exception as e:
            self.logger.warning(f"Could not detect pagination: {e}, using defaults")
            return 0, 22

    def _get_page_offset(self, page_num: int) -> int:
        """
        Calculate the offset for a given page number.

        Args:
            page_num: Zero-based page index

        Returns:
            Offset value for the hash fragment
        """
        return page_num * self.documents_per_page

    def _get_page_url(self, page_num: int) -> str:
        """
        Build the URL for a specific page.

        Args:
            page_num: Zero-based page index

        Returns:
            Full URL including hash fragment for pagination
        """
        offset = self._get_page_offset(page_num)
        if offset == 0:
            return self.base_url
        return f"{self.base_url}#e={offset}"

    def _fetch_with_cloudflare_retry(self, url: str) -> Optional[str]:
        """Fetch a page via FlareSolverr, retrying once on Cloudflare challenge.

        Args:
            url: URL to fetch.

        Returns:
            Rendered HTML or ``None`` on failure.
        """
        page_html = self.fetch_rendered_page(url)
        if not page_html:
            return None

        if "Just a moment" in page_html:
            self.logger.warning("Cloudflare challenge detected in response, retrying...")
            self._polite_delay()
            page_html = self.fetch_rendered_page(url)
            if not page_html or "Just a moment" in page_html:
                return None

        return page_html

    def scrape(self) -> ScraperResult:
        """
        Scrape AEMO Major Publications.

        Uses FlareSolverr for all page fetching. Each page (including hash-fragment
        pagination) is a fresh FlareSolverr request.

        Returns:
            ScraperResult with statistics and document list
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        # Fetch first page via FlareSolverr
        self.logger.info(f"Fetching first page: {self.base_url}")
        page_html = self._fetch_with_cloudflare_retry(self.base_url)
        if not page_html:
            result.status = "failed"
            result.errors.append("Failed to fetch first page via FlareSolverr")
            return result

        # Detect pagination info from the loaded page
        self._initial_offset, self._total_pages = self._detect_pagination_info_from_html(page_html)

        # Determine how many pages to actually scrape
        if self.max_pages:
            pages_to_scrape = min(self.max_pages, self._total_pages)
        else:
            pages_to_scrape = self._total_pages

        self.logger.info(f"Will scrape {pages_to_scrape} of {self._total_pages} pages (initial offset: {self._initial_offset})")

        # Iterate through pages
        for page_num in range(pages_to_scrape):
            # Check for cancellation at start of each page
            if self.check_cancelled():
                self.logger.info("Scraper cancelled, stopping at page boundary")
                break

            offset = self._get_page_offset(page_num)
            self.logger.info(f"Scraping page {page_num + 1}/{pages_to_scrape} (offset={offset})")

            try:
                # First page uses already-fetched HTML, subsequent pages fetch via FlareSolverr
                if page_num > 0:
                    page_url = self._get_page_url(page_num)
                    page_html = self._fetch_with_cloudflare_retry(page_url)
                    if not page_html:
                        self.logger.warning(f"Empty response for page {page_num + 1}")
                        continue

                # Parse documents from the page
                if page_html is None:
                    self.logger.error(f"Unexpected None page_html on page {page_num + 1}")
                    continue
                documents = self.parse_page(page_html)
                result.scraped_count += len(documents)

                self.logger.info(f"Found {len(documents)} documents on page {page_num + 1}")

                # Process each document
                for doc in documents:
                    # Check for cancellation before each download
                    if self.check_cancelled():
                        self.logger.info("Scraper cancelled, stopping at document boundary")
                        break

                    # Check if should be excluded by tags or title keywords
                    exclusion_reason = self.should_exclude_document(doc)
                    if exclusion_reason:
                        self.logger.debug(f"Excluding ({exclusion_reason}): {doc.title}")
                        result.excluded_count += 1
                        result.excluded.append(ExcludedDocument(
                            title=doc.title,
                            url=doc.url,
                            reason=exclusion_reason,
                        ).to_dict())
                        continue

                    # Check if already processed
                    if self._is_processed(doc.url):
                        self.logger.debug(f"Already processed: {doc.title}")
                        result.skipped_count += 1
                        continue

                    # Download the file (or simulate in dry_run mode)
                    if self.dry_run:
                        self.logger.info(f"[DRY RUN] Would download: {doc.title}")
                        result.downloaded_count += 1
                        result.documents.append(doc.to_dict())
                    else:
                        downloaded_path = self._download_file(
                            doc.url,
                            doc.filename,
                            doc,
                        )

                        if downloaded_path:
                            result.downloaded_count += 1
                            result.documents.append(doc.to_dict())
                            self._mark_processed(doc.url, {"title": doc.title})
                        else:
                            result.failed_count += 1

                    self._polite_delay()

                # Break outer loop if cancelled
                if self.is_cancelled:
                    break

            except Exception as e:
                self.logger.error(f"Error on page {page_num + 1}: {e}")
                result.errors.append(f"Page {page_num + 1}: {str(e)}")

            # Small delay between pages
            self._polite_delay()

        return result

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse AEMO page and extract document metadata.

        Args:
            page_source: HTML source of the page

        Returns:
            List of DocumentMetadata objects
        """
        soup = BeautifulSoup(page_source, "lxml")
        documents = []

        # Find document items in the search result list
        doc_items = soup.select(".search-result-list > li")

        if not doc_items:
            # Fallback: try finding the link items directly
            doc_items = soup.select("a.search-result-list-item")
            self.logger.debug(f"Using fallback selector, found {len(doc_items)} items")

        self.logger.debug(f"Found {len(doc_items)} document items")

        for item in doc_items:
            try:
                doc = self._parse_document_item(item)
                if doc:
                    documents.append(doc)
            except Exception as e:
                self.logger.warning(f"Failed to parse document item: {e}")

        return documents

    def _parse_document_item(self, item) -> Optional[DocumentMetadata]:
        """
        Parse a single document item from the page.

        Args:
            item: BeautifulSoup element (either <li> or <a>)

        Returns:
            DocumentMetadata or None if not a valid PDF document
        """
        # Find the link element
        if item.name == "a":
            link = item
        else:
            link = item.find("a", class_="search-result-list-item")

        if not link:
            return None

        href = link.get("href", "")
        if not href:
            return None

        # Build full URL
        if href.startswith("/"):
            url = f"https://www.aemo.com.au{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = urljoin(self.base_url, href)

        # Extract title from <h3>
        title_elem = link.find("h3")
        title = title_elem.get_text(strip=True) if title_elem else ""

        if not title:
            # Fallback: get from URL
            title = url.split("/")[-1].replace(".pdf", "").replace("-", " ")

        # Extract category (first <span> in the link)
        category_elem = link.find("span")
        category = category_elem.get_text(strip=True) if category_elem else ""

        # Extract date from .is-date.field-publisheddate span
        date_elem = link.select_one(".is-date.field-publisheddate span")
        pub_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            pub_date = self._parse_date(date_text)

        # Extract file info from .search-result-list-item--content divs
        file_size_str = None
        file_type = None

        content_divs = link.select(".search-result-list-item--content")
        for div in content_divs:
            text = div.get_text(strip=True)
            # Look for size pattern like "2.46 MB" or "433.72 KB"
            size_match = re.search(r"Size\s*([\d.]+\s*(?:KB|MB|GB))", text, re.I)
            if size_match:
                file_size_str = size_match.group(1)
            # Look for file type
            type_match = re.search(r"File type\s*(\w+)", text, re.I)
            if type_match:
                file_type = type_match.group(1).lower()

        # Only process PDF files
        is_pdf = (
            file_type == "pdf" or
            url.lower().endswith(".pdf") or
            ".pdf?" in url.lower()
        )

        if not is_pdf:
            self.logger.debug(f"Skipping non-PDF: {title} (type: {file_type})")
            return None

        # Generate filename from URL
        filename = url.split("/")[-1]
        if "?" in filename:
            filename = filename.split("?")[0]
        filename = sanitize_filename(filename)

        if not filename.lower().endswith(".pdf"):
            filename = f"{sanitize_filename(title)}.pdf"

        # Build tags list
        tags = []
        if category:
            tags.append(category)

        return DocumentMetadata(
            url=url,
            title=title,
            filename=filename,
            publication_date=pub_date,
            file_size_str=file_size_str,
            file_size=parse_file_size(file_size_str) if file_size_str else None,
            tags=tags,
            source_page=self.base_url,
            organization="AEMO",
            document_type="Report",
        )

    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse date string to ISO format.

        AEMO uses DD/MM/YYYY format (e.g., "31/07/2025")

        Args:
            date_str: Date string from the page

        Returns:
            ISO format date (YYYY-MM-DD) or None if parsing fails
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Try DD/MM/YYYY format (AEMO's format)
        formats = [
            "%d/%m/%Y",  # 31/07/2025
            "%d %B %Y",  # 31 July 2025
            "%d %b %Y",  # 31 Jul 2025
            "%Y-%m-%d",  # 2025-07-31
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        self.logger.debug(f"Could not parse date: {date_str}")
        return None
