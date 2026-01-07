"""
TheEnergy (theenergy.co) scraper for Australian energy news articles.

Scrapes articles from: https://theenergy.co/articles

Server-side rendered site (no Cloudflare protection).
Pagination pattern: /articles/pN (N = 2 to 34+)
Two-stage scraping: listing page -> article page for JSON-LD dates and content.
Saves article content as Markdown for RAGFlow indexing.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename, ArticleConverter
from app.utils.errors import ScraperError


class TheEnergyScraper(BaseScraper):
    """
    Scraper for TheEnergy news articles.

    Key features:
    - Server-side rendered (no JS challenge, no Cloudflare)
    - Path-based pagination: /articles/pN
    - Two-stage scraping for full ISO 8601 dates from JSON-LD
    - Extracts article content as Markdown
    - Article types: news, feature, explainer, context
    - Categories: Policy, Projects, Regulation, Energy Systems, etc.
    """

    name = "theenergy"
    display_name = "The Energy"
    description = "Scrapes articles from The Energy (theenergy.co)"
    base_url = "https://theenergy.co/articles"

    # TheEnergy-specific settings
    articles_per_page = 10
    request_delay = 1.0  # Polite crawling
    default_chunk_method = "naive"  # Markdown articles need naive chunking
    default_parser = "Naive"  # No OCR needed for markdown

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    # Valid article categories and types
    VALID_CATEGORIES = [
        "Policy", "Projects", "Regulation", "Energy Systems",
        "Technology", "Capital", "Climate", "Workforce"
    ]
    VALID_TYPES = ["news", "feature", "explainer", "context"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize scraper with GFM markdown converter."""
        super().__init__(*args, **kwargs)

        # Use shared GFM converter
        self._markdown = ArticleConverter()

    def _build_page_url(self, page_num: int) -> str:
        """
        Build URL for a specific page.

        TheEnergy uses path-based pagination:
        - Page 1: /articles (no suffix)
        - Page 2+: /articles/pN

        Args:
            page_num: 1-indexed page number

        Returns:
            Full URL for the page
        """
        if page_num == 1:
            return self.base_url
        return f"{self.base_url}/p{page_num}"

    def _wait_for_content(self, timeout: int = 10) -> None:
        """Wait for article content to load."""
        try:
            if not self.driver:
                raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
            assert self.driver is not None
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "main article, article")
                )
            )
            time.sleep(0.5)  # Small buffer for render
        except TimeoutException:
            self.logger.warning("Timeout waiting for article content")

    def _extract_jsonld_dates(self, html: str) -> dict[str, Optional[str]]:
        """
        Extract dates from JSON-LD structured data on an article page.

        TheEnergy articles contain JSON-LD with schema.org Article type:
        {
            "@type": "Article",
            "datePublished": "2025-12-24T07:30:00+11:00",
            "dateCreated": "2025-12-24T12:04:37+11:00",
            "dateModified": "2025-12-24T12:39:08+11:00"
        }

        Args:
            html: HTML content of the article page

        Returns:
            Dict with keys: date_published, date_created, date_modified
            Values are ISO date strings (YYYY-MM-DD) or None
        """
        result: dict[str, Optional[str]] = {
            "date_published": None,
            "date_created": None,
            "date_modified": None,
        }

        soup = BeautifulSoup(html, "lxml")

        # Find JSON-LD script tags
        jsonld_scripts = soup.find_all("script", type="application/ld+json")

        for script in jsonld_scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)

                # Handle both single object and @graph array
                items: list[Any] = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if "@graph" in data:
                        items = data["@graph"]
                    else:
                        items = [data]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") == "Article":
                        # Extract and parse dates
                        for key, field in [
                            ("date_published", "datePublished"),
                            ("date_created", "dateCreated"),
                            ("date_modified", "dateModified"),
                        ]:
                            if field in item and item[field]:
                                result[key] = self._parse_iso_date(item[field])

                        # Found Article, return if we have data
                        if any(result.values()):
                            return result

            except (json.JSONDecodeError, TypeError, KeyError) as e:
                self.logger.debug(f"Failed to parse JSON-LD: {e}")
                continue

        return result

    def _parse_iso_date(self, date_str: str) -> Optional[str]:
        """
        Parse ISO 8601 date string to YYYY-MM-DD format.

        Args:
            date_str: ISO date like "2025-12-24T07:30:00+11:00"

        Returns:
            Date in YYYY-MM-DD format or None
        """
        if not date_str:
            return None

        try:
            # Handle various ISO formats
            # Remove timezone info for simple parsing
            clean = date_str.split("+")[0].split("Z")[0]
            if "T" in clean:
                clean = clean.split("T")[0]
            # Validate it's a proper date
            dt = datetime.strptime(clean, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            self.logger.debug(f"Could not parse ISO date: {date_str}")
            return None

    def _extract_article_content(self, html: str) -> str:
        """
        Extract article body content and convert to GFM-compliant Markdown.

        Args:
            html: HTML content of the article page

        Returns:
            Article content as GFM Markdown string
        """
        # ArticleConverter automatically finds main content
        return self._markdown.convert(html)

    def scrape(self) -> ScraperResult:
        """
        Scrape TheEnergy articles.

        Workflow:
        1. Iterate through paginated listing pages
        2. Parse article items from each page
        3. Visit each article page to extract JSON-LD dates and content
        4. Save article as Markdown with metadata sidecar

        Returns:
            ScraperResult with statistics and article metadata
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        page_num = 1
        consecutive_empty_pages = 0

        try:
            while True:
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    result.status = "cancelled"
                    break

                # Check max_pages limit
                if self.max_pages and page_num > self.max_pages:
                    self.logger.info(f"Reached max pages limit ({self.max_pages})")
                    break

                page_url = self._build_page_url(page_num)
                self.logger.info(f"Scraping page {page_num}: {page_url}")

                try:
                    if not self.driver:
                        raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
                    assert self.driver is not None
                    self.driver.get(page_url)
                    self._wait_for_content()
                    page_html = self.get_page_source()

                    # Parse articles from listing page
                    articles = self.parse_page(page_html)

                    if not articles:
                        consecutive_empty_pages += 1
                        self.logger.info(f"No articles on page {page_num}")
                        # Stop after 2 consecutive empty pages
                        if consecutive_empty_pages >= 2:
                            self.logger.info("No more articles found, stopping")
                            break
                    else:
                        consecutive_empty_pages = 0
                        result.scraped_count += len(articles)
                        self.logger.info(f"Found {len(articles)} articles on page {page_num}")

                        # Process each article
                        for article in articles:
                            if self.check_cancelled():
                                break

                            self._process_article(article, result)
                            self._polite_delay()

                except Exception as e:
                    self.logger.error(f"Error on page {page_num}: {e}")
                    result.errors.append(f"Page {page_num}: {str(e)}")

                page_num += 1
                self._polite_delay()

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

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse listing page and extract article metadata.

        CSS Selectors:
        - Container: main
        - Articles: article
        - Link: article > a
        - Title: article h3
        - Category: article .metadata span:first-child
        - Type: article .metadata span:nth-child(2)
        - Date (display): article .metadata .date
        - Abstract: article .abstract

        Args:
            page_source: HTML source of the listing page

        Returns:
            List of DocumentMetadata for articles found
        """
        soup = BeautifulSoup(page_source, "lxml")
        articles: list[DocumentMetadata] = []

        # Find all article elements within main
        main = soup.find("main")
        if not main:
            self.logger.warning("Could not find main element")
            return articles

        article_elements = main.find_all("article")
        self.logger.debug(f"Found {len(article_elements)} article elements")

        for article_el in article_elements:
            try:
                doc = self._parse_article_item(article_el)
                if doc:
                    articles.append(doc)
            except Exception as e:
                self.logger.warning(f"Failed to parse article: {e}")

        return articles

    def _parse_article_item(self, article_el: Any) -> Optional[DocumentMetadata]:
        """
        Parse a single article element from the listing page.

        Args:
            article_el: BeautifulSoup article element

        Returns:
            DocumentMetadata or None if parsing fails
        """
        # Find link - use direct child anchor
        link = article_el.select_one("a")
        if not link:
            return None

        href = link.get("href", "")
        if not href:
            return None

        # Build full URL
        if not href.startswith("http"):
            article_url = urljoin("https://theenergy.co", href)
        else:
            article_url = href

        # Title from h3
        title_el = article_el.find("h3")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            self.logger.debug(f"No title found for article: {href}")
            return None

        # Metadata spans
        metadata_container = article_el.select_one(".metadata")
        category = ""
        article_type = ""
        display_date = ""

        if metadata_container:
            spans = metadata_container.find_all("span", recursive=False)
            if len(spans) >= 1:
                category = spans[0].get_text(strip=True)
            if len(spans) >= 2:
                article_type = spans[1].get_text(strip=True).lower()

            date_el = metadata_container.select_one(".date")
            if date_el:
                display_date = date_el.get_text(strip=True)

        # Abstract
        abstract_el = article_el.select_one(".abstract")
        abstract = abstract_el.get_text(strip=True) if abstract_el else ""

        # Build tags
        tags = ["TheEnergy"]
        if category:
            tags.append(category)
        if article_type:
            tags.append(article_type)

        # Create filename from title (for metadata file)
        safe_title = sanitize_filename(title)
        filename = f"{safe_title[:100]}.md"

        return DocumentMetadata(
            url=article_url,
            title=title,
            filename=filename,
            publication_date=None,  # Will be filled from JSON-LD
            tags=tags,
            source_page=self.base_url,
            organization="The Energy",
            document_type="Article",
            extra={
                "category": category,
                "article_type": article_type,
                "display_date": display_date,
                "abstract": abstract,
                "content_type": "article",
            },
        )

    def _process_article(self, article: DocumentMetadata, result: ScraperResult) -> None:
        """
        Process a single article: fetch full dates and content, save as Markdown.

        Args:
            article: DocumentMetadata from listing page
            result: ScraperResult to update
        """
        # Check exclusion
        exclusion_reason = self.should_exclude_document(article)
        if exclusion_reason:
            self.logger.debug(f"Excluded: {article.title} ({exclusion_reason})")
            result.excluded_count += 1
            result.excluded.append(
                ExcludedDocument(
                    title=article.title,
                    url=article.url,
                    reason=exclusion_reason,
                ).to_dict()
            )
            return

        # Check if already processed
        if self._is_processed(article.url):
            self.logger.debug(f"Already processed: {article.title}")
            result.skipped_count += 1
            return

        # Stage 2: Fetch article page for JSON-LD dates and content
        try:
            self.logger.debug(f"Fetching article: {article.url}")
            if not self.driver:
                raise ScraperError("Driver not initialized", scraper=getattr(self, 'name', 'unknown'))
            assert self.driver is not None
            self.driver.get(article.url)
            self._wait_for_content(timeout=10)
            article_html = self.get_page_source()

            # Extract JSON-LD dates
            dates = self._extract_jsonld_dates(article_html)

            # Update article metadata with full dates
            if dates["date_published"]:
                article.publication_date = dates["date_published"]
                article.extra["date_published_iso"] = dates["date_published"]
            if dates["date_created"]:
                article.extra["date_created"] = dates["date_created"]
            if dates["date_modified"]:
                article.extra["date_modified"] = dates["date_modified"]

            self.logger.debug(
                f"Extracted dates for '{article.title}': "
                f"published={dates['date_published']}"
            )

            # Extract article content as Markdown
            content = self._extract_article_content(article_html)

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would save: {article.title}")
                result.downloaded_count += 1
                result.documents.append(article.to_dict())
            else:
                # Set filename before calling base method
                article.filename = sanitize_filename(article.title)[:100]

                # Save article as Markdown with metadata (uses base class method)
                saved_path = self._save_article(article, content)

                if saved_path:
                    result.downloaded_count += 1
                    result.documents.append(article.to_dict())
                    self._mark_processed(article.url, {"title": article.title})
                else:
                    result.failed_count += 1

        except Exception as e:
            self.logger.warning(f"Failed to process article {article.url}: {e}")
            result.failed_count += 1
