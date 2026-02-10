"""
AER (Australian Energy Regulator) scraper for reports and publications.

Scrapes PDFs from: https://www.aer.gov.au/publications/reports

Uses base class exclusion filters (smart gas-only filtering).
Uses FlareSolverr for rendered page fetching (handles Akamai bot protection).
Traditional query parameter pagination (?page=N, 0-indexed).
Each report links to a detail page where PDFs are found.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.card_pagination_mixin import CardListPaginationMixin
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename


class AERScraper(FlareSolverrPageFetchMixin, CardListPaginationMixin, BaseScraper):
    """
    Scraper for AER Reports and Publications.

    Key features:
    - Uses FlareSolverr to bypass Akamai bot protection
    - Server-side rendered after JS challenge passes
    - Traditional pagination with ?page=N (0-indexed)
    - Local filtering:
      - Excludes documents with "Gas" sector (Electricity only)
      - Excludes "Corporate reports" report type
    - Two-stage scraping: listing page -> detail pages -> PDFs
    """

    name = "aer"
    display_name = "Australian Energy Regulator"
    description = "Scrapes PDFs from AER Reports (Electricity sector, excluding Corporate)"
    base_url = "https://www.aer.gov.au/publications/reports"

    skip_webdriver = True  # Use FlareSolverr instead of Selenium

    # AER-specific settings
    request_delay = 1.5  # Be polite to the server

    # Uses base class exclusion defaults:
    # - excluded_tags: ["Gas", "Corporate reports"]
    # - excluded_keywords: ["Annual Report", "Budget", "Corporate"]
    # - required_tags: ["Electricity"] (smart gas-only filtering)

    def _build_page_url(self, page_num: int) -> str:
        """Build URL for a specific page."""
        if page_num == 0:
            return self.base_url
        return f"{self.base_url}?page={page_num}"

    def _detect_total_pages(self, html: str) -> int:
        """
        Detect total number of pages from pagination links.

        Args:
            html: HTML content of a page

        Returns:
            Total number of pages (minimum 1)
        """
        soup = BeautifulSoup(html, "lxml")

        # Look for "Last" pagination link
        # Format: <a title="Go to last page" href="?...&page=261">
        last_link = soup.select_one('a[title="Go to last page"]')
        if last_link:
            href = str(last_link.get("href", ""))
            match = re.search(r"page=(\d+)", href)
            if match:
                # page is 0-indexed, so add 1 for total count
                return int(match.group(1)) + 1

        # Fallback: count pagination links
        page_links = soup.select("ul.pager__items li.pager__item a")
        if page_links:
            max_page = 0
            for link in page_links:
                href = str(link.get("href", ""))
                match = re.search(r"page=(\d+)", href)
                if match:
                    max_page = max(max_page, int(match.group(1)))
            if max_page > 0:
                return max_page + 1

        return 1  # Default to single page

    def scrape(self) -> ScraperResult:
        """
        Scrape AER Reports and Publications.

        Uses FlareSolverr to bypass Akamai bot protection, then parses
        the rendered HTML for document listings.

        Returns:
            ScraperResult with statistics and document list
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        try:
            # Fetch first page via FlareSolverr
            self.logger.info(f"Fetching first page: {self.base_url}")
            page_html = self.fetch_rendered_page(self.base_url)
            if not page_html:
                result.status = "failed"
                result.errors.append("Failed to fetch first page via FlareSolverr")
                return result

            # Check for Akamai challenge in response
            if "bm-verify" in page_html:
                self.logger.warning("Akamai challenge detected in response, retrying...")
                time.sleep(5)
                page_html = self.fetch_rendered_page(self.base_url)
                if not page_html or "bm-verify" in page_html:
                    result.status = "failed"
                    result.errors.append("Akamai bot protection blocked access")
                    return result

            # Detect pagination
            total_pages = self._detect_total_pages(page_html)
            self.logger.info(f"Detected {total_pages} pages of results")

            # Apply max_pages limit
            pages_to_scrape = total_pages
            if self.max_pages:
                pages_to_scrape = min(total_pages, self.max_pages)
                self.logger.info(f"Limited to {pages_to_scrape} pages")

            # Process first page
            self._process_page(page_html, result)

            # Process remaining pages
            for page_num in range(1, pages_to_scrape):
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    result.status = "cancelled"
                    break

                self._polite_delay()

                page_url = self._build_page_url(page_num)
                self.logger.info(f"Fetching page {page_num + 1}/{pages_to_scrape}")

                try:
                    page_html = self.fetch_rendered_page(page_url)
                    if not page_html:
                        self.logger.warning(f"Empty response for page {page_num}")
                        continue
                    self._process_page(page_html, result)
                except Exception as e:
                    self.logger.warning(f"Failed to fetch page {page_num}: {e}")
                    result.errors.append(f"Page {page_num}: {str(e)}")

            if result.status != "cancelled":
                result.status = "completed"

        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _process_page(self, html: str, result: ScraperResult) -> None:
        """
        Process a single listing page.

        Args:
            html: HTML content of the page
            result: ScraperResult to update
        """
        documents = self.parse_page(html)
        result.scraped_count += len(documents)
        self.logger.info(f"Found {len(documents)} documents on page")

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

            # Find PDF on detail page (uses CardListPaginationMixin which
            # now supports FlareSolverr via fetch_rendered_page)
            self._polite_delay()
            pdf_url = self._find_pdf_on_detail_page(doc.url)

            if not pdf_url:
                self.logger.debug(f"No PDF found for: {doc.title}")
                continue

            # Update document with actual PDF URL
            doc.url = pdf_url
            # Update filename to match PDF
            pdf_filename = pdf_url.split("/")[-1]
            if "?" in pdf_filename:
                pdf_filename = pdf_filename.split("?")[0]
            doc.filename = sanitize_filename(pdf_filename)
            if not doc.filename.lower().endswith(".pdf"):
                doc.filename = sanitize_filename(f"{doc.title}.pdf")

            # Check if already processed
            if self._is_processed(pdf_url):
                self.logger.debug(f"Already processed: {doc.title}")
                result.skipped_count += 1
                continue

            # Download or simulate
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would download: {doc.title}")
                result.downloaded_count += 1
                result.documents.append(doc.to_dict())
            else:
                downloaded_path = self._download_file(
                    pdf_url,
                    doc.filename,
                    doc,
                )

                if downloaded_path:
                    result.downloaded_count += 1
                    result.documents.append(doc.to_dict())
                    self._mark_processed(pdf_url, {"title": doc.title})
                else:
                    result.failed_count += 1

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse a listing page and extract document metadata.

        Args:
            page_source: HTML source of the page

        Returns:
            List of DocumentMetadata for documents found
        """
        soup = BeautifulSoup(page_source, "lxml")
        documents = []

        # Find all document cards
        cards = soup.select(".card__inner")
        self.logger.debug(f"Found {len(cards)} cards on page")

        for card in cards:
            doc = self._parse_card(card)
            if doc:
                documents.append(doc)

        return documents

    def _parse_card(self, card: Any) -> Optional[DocumentMetadata]:
        """
        Parse a single document card into metadata.

        Args:
            card: BeautifulSoup element for the card

        Returns:
            DocumentMetadata or None if parsing fails
        """
        # Title and URL
        title_elem = card.select_one("h3.card__title a")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        detail_url = title_elem.get("href", "")
        if not detail_url:
            return None

        # Build full URL
        if not detail_url.startswith("http"):
            detail_url = urljoin("https://www.aer.gov.au", detail_url)

        # Publication date (look for "Release date" label)
        pub_date = None
        for field in card.select(".field--label-inline"):
            label = field.select_one(".field__label")
            if label and "Release date" in label.get_text():
                date_item = field.select_one(".field__item")
                if date_item:
                    pub_date = self._parse_date_dmy(date_item.get_text(strip=True))
                break

        # Report type
        type_elem = card.select_one(".field--name-field-report-type .field__item")
        report_type = type_elem.get_text(strip=True) if type_elem else None

        # Description
        desc_elem = card.select_one(".field--name-field-summary")
        description = desc_elem.get_text(strip=True) if desc_elem else None

        # Sectors (should all be "Electricity" due to filtering)
        sectors = [
            s.get_text(strip=True)
            for s in card.select(".field--name-field-sectors .field__item")
        ]

        # Segments (Retail, Wholesale, Distribution, etc.)
        segments = [
            s.get_text(strip=True)
            for s in card.select(".field--name-field-segments .field__item")
        ]

        # Build tags from type, sectors, segments
        tags = ["AER"]
        if report_type:
            tags.append(report_type)
        tags.extend(sectors)
        tags.extend(segments)

        # Create preliminary filename from title (will be updated with actual PDF name)
        filename = sanitize_filename(f"{title}.pdf")

        return DocumentMetadata(
            url=detail_url,  # This is the detail page URL; will be updated to PDF URL
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.base_url,
            organization="AER",
            document_type="Report",
            extra={
                "report_type": report_type,
                "description": description,
                "sectors": sectors,
                "segments": segments,
                "detail_page": detail_url,
            },
        )

    def _find_pdf_on_detail_page(self, detail_url: str) -> Optional[str]:
        """Visit a detail page and find the first PDF download link."""
        urls = self._find_documents_on_detail_page(
            detail_url,
            extensions=(".pdf",),
            link_selectors=[
                ".field--name-field-document a",
                ".field--name-field-documents a",
                ".field--type-file a",
            ],
            path_patterns=["/sites/default/files/"],
        )
        return urls[0] if urls else None
