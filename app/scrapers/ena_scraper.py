"""
Energy Networks Australia (ENA) scraper for reports, publications, and submissions.

Scrapes PDFs from:
- https://www.energynetworks.com.au/resources/reports/
- https://www.energynetworks.com.au/resources/submissions/

Simple scraper - no Cloudflare protection, traditional pagination.
Each article links to a detail page where PDFs are found, or the article URL
itself is a direct PDF download.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename
from app.utils.errors import NetworkError


# Resource sections to scrape - all follow the same page structure
ENA_RESOURCE_SECTIONS = [
    {
        "name": "reports",
        "url": "https://www.energynetworks.com.au/resources/reports/",
        "category": "Reports",
    },
    {
        "name": "submissions",
        "url": "https://www.energynetworks.com.au/resources/submissions/",
        "category": "Submissions",
    },
]


class ENAScraper(BaseScraper):
    """
    Scraper for Energy Networks Australia Reports, Publications, and Submissions.

    Key features:
    - No Cloudflare protection (simple requests)
    - Server-side rendered HTML with traditional pagination
    - Scrapes multiple resource sections (reports + submissions)
    - Two-stage scraping: listing pages -> individual article pages -> PDFs
    - Some article URLs are direct PDF downloads
    - Uses requests instead of Selenium for efficiency
    """

    name = "ena"
    display_name = "Energy Networks Australia"
    description = "Scrapes PDFs from Energy Networks Australia (Reports & Submissions)"
    base_url = "https://www.energynetworks.com.au/resources/reports/"

    # ENA-specific settings
    request_delay = 1.5  # Be polite to the server

    # Override exclusion filters - ENA covers both electricity and gas networks
    # so we don't require electricity-only documents
    required_tags: list[str] = []  # Don't require specific tags
    excluded_tags: list[str] = []  # Don't exclude by tag - ENA covers multiple sectors
    excluded_keywords: list[str] = ["Annual Report", "Budget"]  # Keep sensible keyword exclusions

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ENA scraper."""
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

    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse date string to ISO format.

        Args:
            date_str: Date in "DD MMM YYYY" format (e.g., "31 Jul 2025")

        Returns:
            Date in "YYYY-MM-DD" format, or None if parsing fails
        """
        if not date_str:
            return None

        formats = [
            "%d %b %Y",   # 31 Jul 2025
            "%d %B %Y",   # 31 July 2025
            "%d/%m/%Y",   # 31/07/2025
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _detect_total_pages(self, html: str) -> int:
        """
        Detect total number of pages from pagination.

        Args:
            html: HTML content of a listing page

        Returns:
            Total number of pages (minimum 1)
        """
        soup = BeautifulSoup(html, "lxml")

        # Find all page number links
        page_links = soup.select(".chr-pagination .page-number a")

        if not page_links:
            return 1

        # Find the highest page number
        max_page = 1
        for link in page_links:
            text = link.get_text(strip=True)
            try:
                page_num = int(text)
                if page_num > max_page:
                    max_page = page_num
            except ValueError:
                continue

        return max_page

    def _build_page_url(self, base_url: str, page_num: int) -> str:
        """
        Build URL for a specific page number.

        Args:
            base_url: Base URL of the resource section
            page_num: Page number (1-indexed)

        Returns:
            Full URL for that page
        """
        if page_num <= 1:
            return base_url
        return f"{base_url}page/{page_num}/"

    def scrape(self) -> ScraperResult:
        """
        Scrape Energy Networks Australia Reports and Submissions.

        Workflow:
        1. For each resource section (reports, submissions):
           a. Fetch first page, detect total pages
           b. Loop through pages (up to max_pages per section)
           c. Parse articles from each page
           d. Visit each article page to find PDFs
           e. Download PDFs with metadata

        Returns:
            ScraperResult with statistics and document list
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        try:
            session = self._get_session()

            # Process each resource section
            for section in ENA_RESOURCE_SECTIONS:
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    break

                section_url = section["url"]
                section_name = section["name"]
                section_category = section["category"]

                self.logger.info(f"=== Processing section: {section_name} ===")

                # Step 1: Fetch first page
                self.logger.info(f"Fetching first page: {section_url}")
                response = self._request_with_retry(session, "get", section_url, timeout=30)
                if response is None:
                    raise NetworkError(
                        f"Failed to fetch first page for section '{section_name}' after retries",
                        scraper=self.name,
                        context={"url": section_url, "operation": "fetch_first_page", "section": section_name}
                    )
                response.raise_for_status()

                # Step 2: Detect total pages
                total_pages = self._detect_total_pages(response.text)
                self.logger.info(f"Detected {total_pages} pages in {section_name}")

                # Apply max_pages limit (per section)
                pages_to_scrape = total_pages
                if self.max_pages:
                    pages_to_scrape = min(self.max_pages, total_pages)
                    self.logger.info(f"Limited to {pages_to_scrape} pages")

                # Step 3: Process each page
                for page_num in range(1, pages_to_scrape + 1):
                    if self.check_cancelled():
                        self.logger.info("Scraper cancelled")
                        break

                    # Fetch page (first page already fetched)
                    if page_num > 1:
                        page_url = self._build_page_url(section_url, page_num)
                        self.logger.info(f"Fetching page {page_num}: {page_url}")
                        self._polite_delay()
                        response = self._request_with_retry(session, "get", page_url, timeout=30)
                        if response is None:
                            raise NetworkError(
                                f"Failed to fetch page {page_num} for section '{section_name}' after retries",
                                scraper=self.name,
                                context={"url": page_url, "operation": "fetch_page", "page_num": page_num, "section": section_name}
                            )
                        response.raise_for_status()

                    # Parse articles from this page
                    articles = self._parse_articles(response.text)
                    self.logger.info(f"Found {len(articles)} articles on page {page_num}")
                    result.scraped_count += len(articles)

                    # Step 4: Process each article
                    for article in articles:
                        if self.check_cancelled():
                            break

                        # Add section category to article
                        article["section_category"] = section_category

                        self.logger.info(f"Processing article: {article['title'][:50]}...")

                        try:
                            # Visit article page to find PDFs
                            pdfs = self._find_pdfs_on_detail_page(
                                article["url"], session, article["title"]
                            )
                            self.logger.info(f"Found {len(pdfs)} PDFs on article page")

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

                                # Add article metadata to PDF
                                pdf.publication_date = self._parse_date(article.get("date", ""))
                                pdf.extra.update({
                                    "article_title": article["title"],
                                    "article_url": article["url"],
                                    "article_date": article.get("date", ""),
                                    "category": article.get("category", ""),
                                    "section": section_category,
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
                            self.logger.warning(f"Error processing article '{article['title']}': {e}")
                            result.errors.append(f"Article '{article['title'][:30]}...': {str(e)}")

                        self._polite_delay()

            # Set final status
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

    def _parse_articles(self, html: str) -> list[dict[str, str]]:
        """
        Parse articles from a listing page.

        Args:
            html: HTML content of the listing page

        Returns:
            List of dicts with article metadata (title, url, date, category)
        """
        soup = BeautifulSoup(html, "lxml")
        articles = []

        # Find all article elements
        article_elements = soup.select("article.tease.tease-post")

        for article_elem in article_elements:
            try:
                # Extract title
                title_elem = article_elem.select_one(".post-title")
                title = title_elem.get_text(strip=True) if title_elem else ""

                # Extract link
                link_elem = article_elem.select_one("a.tease-link")
                href = link_elem.get("href", "") if link_elem else ""

                if not href or not title:
                    continue

                # Build full URL
                url = urljoin(self.base_url, href)

                # Extract date
                date_elem = article_elem.select_one(".post-date")
                date = date_elem.get_text(strip=True) if date_elem else ""

                # Extract category
                cat_elem = article_elem.select_one(".post-categories")
                category = cat_elem.get_text(strip=True) if cat_elem else ""

                articles.append({
                    "title": title,
                    "url": url,
                    "date": date,
                    "category": category,
                })

            except Exception as e:
                self.logger.warning(f"Failed to parse article: {e}")

        return articles

    def _find_pdfs_on_detail_page(
        self, article_url: str, session: requests.Session, article_title: str = ""
    ) -> list[DocumentMetadata]:
        """
        Visit an article page and find all PDF documents.

        Some ENA article URLs are direct PDF downloads (Content-Type: application/pdf).
        Others are HTML pages with links to PDFs.

        Args:
            article_url: URL of the article detail page
            session: Requests session to use
            article_title: Title of the article (for direct PDF downloads)

        Returns:
            List of DocumentMetadata for PDFs found
        """
        pdfs = []

        try:
            # First, do a HEAD request to check content type
            head_response = self._request_with_retry(session, "head", article_url, timeout=10, allow_redirects=True)
            if head_response is None:
                raise NetworkError(
                    f"Failed to fetch article page '{article_title[:50]}...' after retries",
                    scraper=self.name,
                    context={"url": article_url, "operation": "head_request", "article_title": article_title}
                )
            content_type = head_response.headers.get("Content-Type", "").lower()

            # If the article URL itself is a PDF, treat it as a direct download
            if "application/pdf" in content_type:
                # Extract filename from Content-Disposition header if available
                content_disp = head_response.headers.get("Content-Disposition", "")
                filename = ""
                if "filename=" in content_disp:
                    # Parse filename from header like: inline; filename=something.pdf
                    import re as re_module
                    match = re_module.search(r'filename=([^;\s]+)', content_disp)
                    if match:
                        filename = match.group(1).strip('"\'')

                if not filename:
                    # Fall back to URL path
                    filename = article_url.rstrip("/").split("/")[-1]
                    if not filename.lower().endswith(".pdf"):
                        filename = f"{sanitize_filename(article_title)}.pdf"

                filename = sanitize_filename(filename)

                pdf = DocumentMetadata(
                    url=article_url,
                    title=article_title or filename.replace(".pdf", "").replace("-", " "),
                    filename=filename,
                    source_page=article_url,
                    tags=["ENA", "Energy Networks Australia"],
                    organization="ENA",
                    document_type="Report",
                )
                return [pdf]

            # Otherwise, fetch the page and parse for PDF links
            response = session.get(article_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Find all links ending in .pdf
            pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

            # Also look for common PDF patterns
            additional_links = soup.select(
                "a[href*='/assets/uploads/'], "
                "a[href*='/wp-content/uploads/']"
            )

            for link in additional_links:
                href = link.get("href", "")
                if href.lower().endswith(".pdf") and link not in pdf_links:
                    pdf_links.append(link)

            # Deduplicate by href
            seen_urls = set()

            for link in pdf_links:
                href = link.get("href", "")
                if not href:
                    continue

                # Build full URL
                full_url = urljoin(article_url, href)

                # Skip if not a PDF
                if not full_url.lower().endswith(".pdf"):
                    continue

                # Skip duplicates
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Extract title from link text or filename
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    # Fall back to filename
                    title = full_url.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")

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
                    source_page=article_url,
                    tags=["ENA", "Energy Networks Australia"],
                    organization="ENA",
                    document_type="Report",
                )

                pdfs.append(pdf)

        except Exception as e:
            self.logger.warning(f"Error fetching article page {article_url}: {e}")

        return pdfs

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse a page and extract document metadata.

        Required by BaseScraper abstract class.
        For ENA, this returns an empty list - actual parsing is done
        via _parse_articles and _find_pdfs_on_detail_page.

        Args:
            page_source: HTML source of the page

        Returns:
            Empty list (PDFs are found via detail pages)
        """
        # Main page doesn't directly contain PDFs
        # Return empty list - actual parsing is in _parse_articles
        return []
