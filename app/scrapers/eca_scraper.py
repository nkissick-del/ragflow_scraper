"""
ECA (Energy Consumers Australia) scraper for research and submissions.

Scrapes documents from:
- https://energyconsumersaustralia.com.au/our-work/research
- https://energyconsumersaustralia.com.au/our-work/submissions

Server-side rendered Drupal site (no Cloudflare protection).
Traditional query parameter pagination (?page=N, 0-indexed).
Two-stage scraping: listing page -> detail pages -> documents.
Supports multiple document types: PDF, Word, Excel.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename
from app.utils.errors import ScraperError


# Resource sections to scrape - both follow the same page structure
ECA_RESOURCE_SECTIONS = [
    {
        "name": "research",
        "url": "https://energyconsumersaustralia.com.au/our-work/research",
        "category": "Research",
    },
    {
        "name": "submissions",
        "url": "https://energyconsumersaustralia.com.au/our-work/submissions",
        "category": "Submissions",
    },
]


class ECAScraper(BaseScraper):
    """
    Scraper for Energy Consumers Australia Research and Submissions.

    Key features:
    - Uses Selenium for page fetching (consistent with other scrapers)
    - Server-side rendered Drupal CMS (no JS challenge)
    - Scrapes multiple resource sections (research + submissions)
    - Traditional pagination with ?page=N (0-indexed)
    - Two-stage scraping: listing page -> detail pages -> documents
    - Downloads all document types (PDF, Word, Excel)
    - No sector filtering (ECA is cross-sector consumer advocacy)
    - Excludes corporate/administrative documents by keyword
    """

    name = "eca"
    display_name = "Energy Consumers Australia"
    description = "Scrapes documents from Energy Consumers Australia (Research & Submissions)"
    base_url = "https://energyconsumersaustralia.com.au/our-work/research"

    # ECA is a consumer advocacy org covering all energy sectors
    # Disable sector-based filtering (no Electricity/Gas tags on documents)
    # Keep keyword exclusions for corporate/administrative documents
    required_tags: list[str] = []  # Don't require sector tags
    excluded_tags: list[str] = []  # Don't exclude by sector tag
    excluded_keywords: list[str] = ["Annual Report", "Budget"]  # Exclude corporate docs

    request_delay = 1.5  # Be polite to the server

    # Supported document extensions
    DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls")

    def _build_page_url(self, section_url: str, page_num: int) -> str:
        """Build URL for a specific page within a section."""
        if page_num == 0:
            return section_url
        return f"{section_url}?page={page_num}"

    def _wait_for_content(self, timeout: int = 15):
        """Wait for the research cards to load."""
        try:
            if not self.driver:
                raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
            assert self.driver is not None
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".image-card, .main-content")
                )
            )
            # Small additional wait for content to fully render
            time.sleep(1)
        except TimeoutException:
            self.logger.warning("Timeout waiting for content to load")

    def _detect_total_pages(self, html: str) -> int:
        """
        Detect total number of pages from pagination.

        Looks for "Showing X - Y of Z results" text or pagination links.

        Args:
            html: HTML content of a page

        Returns:
            Total number of pages (minimum 1)
        """
        soup = BeautifulSoup(html, "lxml")

        # Strategy 1: Parse "Showing X - Y of Z results" text
        results_text = soup.find(string=re.compile(r"Showing\s+\d+\s*-\s*\d+\s+of\s+\d+"))
        if results_text:
            match = re.search(r"Showing\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)", results_text)
            if match:
                per_page = int(match.group(2)) - int(match.group(1)) + 1
                total = int(match.group(3))
                if per_page > 0:
                    total_pages = (total + per_page - 1) // per_page
                    self.logger.debug(
                        f"Detected {total} results, {per_page} per page = {total_pages} pages"
                    )
                    return total_pages

        # Strategy 2: Find pagination links and get max page number
        page_links = soup.select(".pagination a[href*='page='], .pager a[href*='page=']")
        if page_links:
            max_page = 0
            for link in page_links:
                href = link.get("href", "")
                match = re.search(r"page=(\d+)", href)
                if match:
                    max_page = max(max_page, int(match.group(1)))
            if max_page > 0:
                # page is 0-indexed, so add 1 for total count
                return max_page + 1

        return 1  # Default to single page

    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse date from 'DD Month YYYY' to ISO format.

        Args:
            date_str: Date string like "24 July 2025"

        Returns:
            ISO format date string "YYYY-MM-DD" or None if parsing fails
        """
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str.strip(), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            self.logger.debug(f"Could not parse date: {date_str}")
            return None

    def scrape(self) -> ScraperResult:
        """
        Scrape ECA Research and Submissions.

        Workflow:
        1. For each resource section (research, submissions):
           a. Fetch first page, detect total pages
           b. Loop through pages (up to max_pages per section)
           c. Parse items from each page
           d. Visit each detail page to find documents
           e. Download documents with metadata

        Returns:
            ScraperResult with statistics and document list
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        try:
            # Process each resource section
            for section in ECA_RESOURCE_SECTIONS:
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    result.status = "cancelled"
                    break

                section_url = section["url"]
                section_name = section["name"]
                section_category = section["category"]

                self.logger.info(f"=== Processing section: {section_name} ===")

                # Step 1: Fetch first page
                self.logger.info(f"Fetching first page: {section_url}")
                if not self.driver:
                    raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
                assert self.driver is not None
                self.driver.get(section_url)
                self._wait_for_content()
                page_html = self.get_page_source()

                # Step 2: Detect total pages
                total_pages = self._detect_total_pages(page_html)
                self.logger.info(f"Detected {total_pages} pages in {section_name}")

                # Apply max_pages limit (per section)
                pages_to_scrape = total_pages
                if self.max_pages:
                    pages_to_scrape = min(total_pages, self.max_pages)
                    self.logger.info(f"Limited to {pages_to_scrape} pages")

                # Step 3: Process first page
                self._process_page(page_html, result, section_category)

                # Step 4: Process remaining pages
                for page_num in range(1, pages_to_scrape):
                    if self.check_cancelled():
                        self.logger.info("Scraper cancelled")
                        result.status = "cancelled"
                        break

                    self._polite_delay()

                    page_url = self._build_page_url(section_url, page_num)
                    self.logger.info(f"Fetching page {page_num + 1}/{pages_to_scrape}")

                    try:
                        if not self.driver:
                            raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
                        assert self.driver is not None
                        self.driver.get(page_url)
                        self._wait_for_content()
                        page_html = self.get_page_source()
                        self._process_page(page_html, result, section_category)
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch page {page_num}: {e}")
                        result.errors.append(f"Page {page_num}: {str(e)}")

            # Set final status
            if result.status != "cancelled":
                if result.errors and result.downloaded_count == 0:
                    result.status = "failed"
                elif result.errors:
                    result.status = "partial"
                else:
                    result.status = "completed"

        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _process_page(self, html: str, result: ScraperResult, section_category: str) -> None:
        """
        Process a single listing page.

        Args:
            html: HTML content of the page
            result: ScraperResult to update
            section_category: Category name for this section (Research/Submissions)
        """
        documents = self.parse_page(html, section_category)
        result.scraped_count += len(documents)
        self.logger.info(f"Found {len(documents)} items on page")

        for doc in documents:
            if self.check_cancelled():
                break

            # Check exclusion (tags/keywords)
            exclusion_reason = self.should_exclude_document(doc)
            if exclusion_reason:
                self.logger.debug(f"Excluded: {doc.title} ({exclusion_reason})")
                result.excluded_count += 1
                result.excluded.append(
                    ExcludedDocument(
                        title=doc.title,
                        url=doc.url,
                        reason=exclusion_reason,
                    ).to_dict()
                )
                continue

            # Find documents on detail page
            self._polite_delay()
            doc_urls = self._find_documents_on_detail_page(doc.url)

            if not doc_urls:
                self.logger.debug(f"No documents found for: {doc.title}")
                continue

            # Process each document found on the detail page
            for doc_url in doc_urls:
                # Check if already processed
                if self._is_processed(doc_url):
                    self.logger.debug(f"Already processed: {doc_url}")
                    result.skipped_count += 1
                    continue

                # Create metadata for this specific document
                doc_filename = doc_url.split("/")[-1]
                if "?" in doc_filename:
                    doc_filename = doc_filename.split("?")[0]
                doc_filename = sanitize_filename(doc_filename)

                # If filename doesn't have a valid extension, use title
                if not doc_filename.lower().endswith(self.DOCUMENT_EXTENSIONS):
                    ext = self._get_extension_from_url(doc_url)
                    doc_filename = sanitize_filename(f"{doc.title}{ext}")

                doc_metadata = DocumentMetadata(
                    url=doc_url,
                    title=doc.title,
                    filename=doc_filename,
                    publication_date=doc.publication_date,
                    tags=doc.tags,
                    source_page=doc.extra.get("detail_page", self.base_url),
                    extra=doc.extra.copy(),
                )

                # Download or simulate
                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would download: {doc.title} - {doc_filename}")
                    result.downloaded_count += 1
                    result.documents.append(doc_metadata.to_dict())
                else:
                    downloaded_path = self._download_file(
                        doc_url,
                        doc_filename,
                        doc_metadata,
                    )

                    if downloaded_path:
                        result.downloaded_count += 1
                        result.documents.append(doc_metadata.to_dict())
                        self._mark_processed(doc_url, {"title": doc.title})
                    else:
                        result.failed_count += 1

    def _get_extension_from_url(self, url: str) -> str:
        """Extract file extension from URL, defaulting to .pdf."""
        url_lower = url.lower()
        for ext in self.DOCUMENT_EXTENSIONS:
            if ext in url_lower:
                return ext
        return ".pdf"

    def parse_page(self, page_source: str, section_category: str = "Research") -> list[DocumentMetadata]:
        """
        Parse a listing page and extract item metadata.

        Args:
            page_source: HTML source of the page
            section_category: Category for tagging (Research/Submissions)

        Returns:
            List of DocumentMetadata for items found
        """
        soup = BeautifulSoup(page_source, "lxml")
        documents = []

        # Find all cards
        cards = soup.select(".image-card")
        self.logger.debug(f"Found {len(cards)} image-cards on page")

        for card in cards:
            doc = self._parse_card(card, section_category)
            if doc:
                documents.append(doc)

        return documents

    def _parse_card(self, card: Any, section_category: str = "Research") -> Optional[DocumentMetadata]:
        """
        Parse a single card into metadata.

        Args:
            card: BeautifulSoup element for the card
            section_category: Category for tagging (Research/Submissions)

        Returns:
            DocumentMetadata or None if parsing fails
        """
        # Title
        title_elem = card.select_one(".image-card__heading")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        # URL (first anchor in the card)
        link_elem = card.select_one("a")
        if not link_elem:
            return None

        detail_url = link_elem.get("href", "")
        if not detail_url:
            return None

        # Build full URL
        if not detail_url.startswith("http"):
            detail_url = urljoin("https://energyconsumersaustralia.com.au", detail_url)

        # Publication date
        date_elem = card.select_one(".image-card__date")
        pub_date = None
        if date_elem:
            pub_date = self._parse_date(date_elem.get_text(strip=True))

        # Description
        desc_elem = card.select_one(".image-card__teaser")
        description = desc_elem.get_text(strip=True) if desc_elem else None

        # Read time
        read_time_elem = card.select_one(".image-card__read-time")
        read_time = read_time_elem.get_text(strip=True) if read_time_elem else None

        # Featured badge
        badge_elem = card.select_one(".badge")
        is_featured = bool(badge_elem)

        # Build tags
        tags = ["ECA", section_category]
        if is_featured:
            tags.append("Featured")

        # Create preliminary filename (will be updated with actual document name)
        filename = sanitize_filename(f"{title}.pdf")

        return DocumentMetadata(
            url=detail_url,  # This is the detail page URL; will be updated to document URL
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.base_url,
            organization="ECA",
            document_type="Report",
            extra={
                "description": description,
                "read_time": read_time,
                "featured": is_featured,
                "detail_page": detail_url,
                "section": section_category,
            },
        )

    def _find_documents_on_detail_page(self, detail_url: str) -> list[str]:
        """
        Visit a detail page and find all downloadable documents.

        Args:
            detail_url: URL of the detail page

        Returns:
            List of document URLs (PDF, Word, Excel)
        """
        try:
            self.logger.debug(f"Fetching detail page: {detail_url}")
            if not self.driver:
                raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
            assert self.driver is not None
            self.driver.get(detail_url)
            self._wait_for_content(timeout=10)

            soup = BeautifulSoup(self.get_page_source(), "lxml")
            document_urls = []

            # Find all document links by extension
            for ext in self.DOCUMENT_EXTENSIONS:
                # Case-insensitive search for links ending with extension
                links = soup.find_all("a", href=re.compile(rf"\.{ext[1:]}$", re.I))
                for link in links:
                    href = link.get("href", "")
                    if href:
                        full_url = urljoin(detail_url, href)
                        if full_url not in document_urls:
                            document_urls.append(full_url)

            # Also check for links containing common document paths
            doc_path_links = soup.select(
                "a[href*='/sites/default/files/'], "
                "a[href*='/documents/'], "
                "a[href*='/files/']"
            )
            for link in doc_path_links:
                href = link.get("href", "")
                if href:
                    # Check if it's a document type we support
                    href_lower = href.lower()
                    if any(href_lower.endswith(ext) for ext in self.DOCUMENT_EXTENSIONS):
                        full_url = urljoin(detail_url, href)
                        if full_url not in document_urls:
                            document_urls.append(full_url)

            if document_urls:
                self.logger.debug(f"Found {len(document_urls)} documents on detail page")
            else:
                self.logger.debug(f"No documents found on detail page: {detail_url}")

            return document_urls

        except Exception as e:
            self.logger.warning(f"Error fetching detail page {detail_url}: {e}")
            return []
