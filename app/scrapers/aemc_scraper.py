"""
AEMC (Australian Energy Market Commission) scraper for market reviews and advice.

Scrapes PDFs from: https://www.aemc.gov.au/our-work/market-reviews-and-advice

Simple scraper - no Cloudflare protection, all reviews in single page load.
Each review links to a detail page where PDFs are found.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename
from app.utils.errors import NetworkError


class AEMCScraper(BaseScraper):
    """
    Scraper for AEMC Market Reviews and Advice.

    Key features:
    - No Cloudflare protection (simple requests)
    - All 195 reviews in single HTML page (DataTables client-side pagination)
    - Two-stage scraping: main table -> individual review pages -> PDFs
    - Uses requests instead of Selenium for efficiency
    """

    name = "aemc"
    display_name = "Australian Energy Market Commission"
    description = "Scrapes PDFs from AEMC Market Reviews and Advice"
    base_url = "https://www.aemc.gov.au/our-work/market-reviews-and-advice"

    # AEMC-specific settings
    request_delay = 1.5  # Be polite to the server

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize AEMC scraper."""
        super().__init__(*args, **kwargs)
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        """Get or create a requests session with appropriate headers."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
        return self._session

    def _clean_text(self, text: str) -> str:
        """
        Clean text by stripping zero-width characters, HTML entities, and whitespace.

        AEMC pages contain zero-width spaces (\u200b) that need removal.
        """
        if not text:
            return ""
        # Remove zero-width characters
        text = text.replace("\u200b", "")
        # Remove other invisible characters
        text = re.sub(r"[\u200b-\u200f\u2028-\u202f\u205f-\u206f]", "", text)
        # Replace HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def scrape(self) -> ScraperResult:
        """
        Scrape AEMC Market Reviews and Advice.

        Workflow:
        1. Fetch main page (single request gets all 195 reviews)
        2. Parse table to get review page URLs
        3. Visit each review page to find PDFs
        4. Download PDFs with metadata

        Returns:
            ScraperResult with statistics and document list
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        try:
            session = self._get_session()

            # Step 1: Fetch main page
            self.logger.info(f"Fetching main page: {self.base_url}")
            response = self._request_with_retry(session, "get", self.base_url, timeout=30)

            # Step 2: Parse review entries from table
            reviews = self._parse_reviews_table(response.text)
            self.logger.info(f"Found {len(reviews)} reviews in table")
            result.scraped_count = len(reviews)

            # Apply max_pages limit (treat each review as a "page")
            if self.max_pages:
                reviews = reviews[: self.max_pages]
                self.logger.info(f"Limited to {self.max_pages} reviews")

            # Step 3: Process each review
            for i, review in enumerate(reviews):
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    break

                self.logger.info(
                    f"Processing review {i + 1}/{len(reviews)}: {review['title'][:50]}..."
                )

                # Visit review page to find PDFs
                try:
                    pdfs = self._find_pdfs_on_review_page(review["url"], session)
                    self.logger.info(f"Found {len(pdfs)} PDFs on review page")

                    for pdf in pdfs:
                        if self.check_cancelled():
                            break

                        # Check exclusion (tags/keywords)
                        exclusion_reason = self.should_exclude_document(pdf)
                        if exclusion_reason:
                            self.logger.debug(f"Excluded: {pdf.title} ({exclusion_reason})")
                            result.excluded_count += 1
                            result.excluded.append(
                                ExcludedDocument(
                                    title=pdf.title,
                                    url=pdf.url,
                                    reason=exclusion_reason,
                                ).to_dict()
                            )
                            continue

                        # Check if already processed
                        if self._is_processed(pdf.url):
                            self.logger.debug(f"Already processed: {pdf.title}")
                            result.skipped_count += 1
                            continue

                        # Add review metadata to PDF
                        pdf.extra.update({
                            "review_title": review["title"],
                            "review_url": review["url"],
                            "date_initiated": review.get("date_initiated", ""),
                            "stage": review.get("stage", ""),
                            "reference": review.get("reference", ""),
                        })

                        # Download or simulate
                        if self.dry_run:
                            self.logger.info(f"[DRY RUN] Would download: {pdf.title}")
                            result.downloaded_count += 1
                            result.documents.append(pdf.to_dict())
                        else:
                            downloaded_path = self._download_file(
                                pdf.url,
                                pdf.filename,
                                pdf,
                            )

                            if downloaded_path:
                                result.downloaded_count += 1
                                result.documents.append(pdf.to_dict())
                                self._mark_processed(pdf.url, {"title": pdf.title})
                            else:
                                result.failed_count += 1

                        self._polite_delay()

                except Exception as e:
                    self.logger.warning(f"Error processing review '{review['title']}': {e}")
                    result.errors.append(f"Review '{review['title'][:30]}...': {str(e)}")

                self._polite_delay()

        except NetworkError as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"
        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _parse_reviews_table(self, html: str) -> list[dict[str, str]]:
        """
        Parse the main page table and extract review entries.

        Args:
            html: HTML content of the main page

        Returns:
            List of dicts with review metadata (title, url, dates, etc.)
        """
        soup = BeautifulSoup(html, "lxml")
        reviews = []

        # Find the table and get all rows
        # Note: AEMC table doesn't have proper <tbody>, rows are direct children
        table = soup.select_one("table.list-table")
        if not table:
            self.logger.warning("Could not find list-table on page")
            return reviews

        # Get all tr elements, skip the header row
        all_rows = table.find_all("tr")
        rows = [r for r in all_rows if r.find("td")]  # Only rows with <td> (not header)
        self.logger.debug(f"Found {len(rows)} table rows")

        for row in rows:
            try:
                review = self._parse_review_row(row)
                if review:
                    reviews.append(review)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")

        return reviews

    def _parse_review_row(self, row: Any) -> Optional[dict[str, str]]:
        """
        Parse a single table row into review metadata.

        Table columns:
        1. (checkbox/hidden)
        2. Title (with link)
        3. Date initiated
        4. Stage
        5. Completion date
        6. Submission date
        7. Reference code
        8. Status (hidden)
        9. Reviewed by (hidden)

        Args:
            row: BeautifulSoup element for table row

        Returns:
            Dict with review metadata, or None if invalid
        """
        # Extract title and URL from column 2
        title_elem = row.select_one("td:nth-child(2) a")
        if not title_elem:
            return None

        title = self._clean_text(title_elem.get_text())
        href = title_elem.get("href", "")

        if not href:
            return None

        # Build full URL
        url = urljoin("https://www.aemc.gov.au", href)

        # Extract other fields
        date_initiated = self._extract_cell_text(row, 3)
        stage = self._extract_cell_text(row, 4)
        completion_date = self._extract_cell_text(row, 5)
        submission_date = self._extract_cell_text(row, 6)
        reference = self._extract_cell_text(row, 7)
        status = self._extract_cell_text(row, 8)  # "Open" or "Completed"

        return {
            "title": title,
            "url": url,
            "date_initiated": date_initiated,
            "stage": stage,
            "completion_date": completion_date,
            "submission_date": submission_date,
            "reference": reference,
            "status": status,
        }

    def _extract_cell_text(self, row: Any, column: int) -> str:
        """Extract and clean text from a table cell by column number."""
        cell = row.select_one(f"td:nth-child({column})")
        if cell:
            return self._clean_text(cell.get_text())
        return ""

    def _find_pdfs_on_review_page(
        self, review_url: str, session: requests.Session
    ) -> list[DocumentMetadata]:
        """
        Visit a review page and find all PDF documents.

        AEMC review pages typically have documents in sections like:
        - "Related documents" or "Documents"
        - Links with .pdf extension or download icons

        Args:
            review_url: URL of the review detail page
            session: Requests session to use

        Returns:
            List of DocumentMetadata for PDFs found
        """
        pdfs = []

        try:
            response = self._request_with_retry(session, "get", review_url, timeout=30)

            soup = BeautifulSoup(response.text, "lxml")

            # Strategy 1: Find all links ending in .pdf
            pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

            # Strategy 2: Look in document sections
            doc_sections = soup.select(
                ".field--name-field-documents a, "
                ".document-list a, "
                ".related-documents a, "
                ".field--type-file a, "
                "a[href*='/sites/default/files/']"
            )
            pdf_links.extend(doc_sections)

            # Deduplicate by href
            seen_urls = set()

            for link in pdf_links:
                href = link.get("href", "")
                if not href:
                    continue

                # Build full URL
                full_url = urljoin(review_url, href)

                # Skip if not a PDF
                if not full_url.lower().endswith(".pdf"):
                    continue

                # Skip duplicates
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Extract title from link text or filename
                title = self._clean_text(link.get_text())
                if not title or len(title) < 3:
                    # Fall back to filename
                    title = full_url.split("/")[-1].replace(".pdf", "").replace("-", " ")

                # Generate safe filename
                filename = full_url.split("/")[-1]
                if "?" in filename:
                    filename = filename.split("?")[0]
                filename = sanitize_filename(filename)

                if not filename.lower().endswith(".pdf"):
                    filename = f"{sanitize_filename(title)}.pdf"

                # Create metadata
                pdf = DocumentMetadata(
                    url=full_url,
                    title=title,
                    filename=filename,
                    source_page=review_url,
                    tags=["AEMC", "Market Review"],
                    organization="AEMC",
                    document_type="Report",
                )

                pdfs.append(pdf)

        except Exception as e:
            self.logger.warning(f"Error fetching review page {review_url}: {e}")

        return pdfs

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse a page and extract document metadata.

        Required by BaseScraper abstract class.
        For AEMC, this parses the main table - actual PDFs are found
        by visiting individual review pages.

        Args:
            page_source: HTML source of the page

        Returns:
            Empty list (PDFs are found via _find_pdfs_on_review_page)
        """
        # Main page doesn't directly contain PDFs
        # Return empty list - actual parsing is in _parse_reviews_table
        return []
