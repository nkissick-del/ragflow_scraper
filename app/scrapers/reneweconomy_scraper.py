"""
RenewEconomy (reneweconomy.com.au) scraper for Australian energy news articles.

Scrapes articles from: https://reneweconomy.com.au/

Server-side rendered site (no Cloudflare protection).
Category-first strategy with homepage fallback.
Pagination pattern: /category/{cat}/page/{n}/ or /page/{n}/
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

from app.scrapers.base_scraper import (
    BaseScraper,
    DocumentMetadata,
    ExcludedDocument,
    ScraperResult,
)
from app.utils import sanitize_filename, ArticleConverter


class RenewEconomyScraper(BaseScraper):
    """
    Scraper for RenewEconomy news articles.

    Key features:
    - Server-side rendered (no JS challenge, no Cloudflare)
    - Category-first scraping strategy with homepage fallback
    - Path-based pagination: /category/{cat}/page/{n}/
    - Two-stage scraping for full ISO 8601 dates from JSON-LD
    - Extracts article content as Markdown
    - Categories: Renewables, Solar, Storage, Policy, Hydrogen, EVs, etc.
    """

    name = "reneweconomy"
    display_name = "RenewEconomy"
    description = "Scrapes articles from RenewEconomy (reneweconomy.com.au)"
    base_url = "https://reneweconomy.com.au"

    # RenewEconomy-specific settings
    request_delay = 1.5  # Polite crawling
    homepage_fallback_pages = 5  # Pages to check after categories
    default_chunk_method = "naive"  # Markdown articles need naive chunking
    default_parser = "Naive"  # No OCR needed for markdown

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    # Categories to scrape (excludes multimedia)
    CATEGORIES = [
        # Renewables
        "renewables",
        "renewables/wind",
        "renewables/wave",
        "renewables/biomass",
        "renewables/geothermal",
        # Solar
        "solar",
        "solar/rooftop-pv",
        "solar/utility-pv",
        "solar/solar-thermal",
        # Storage
        "storage",
        "storage/battery",
        "storage/pumpedhydro",
        # Other categories
        "policyandplanning",
        "hydrogen",
        "electric-vehicles",
        "electric-vehicles/electric-cars",
        "electric-vehicles/hydrogen-fuel-cell",
        # Content types
        "chart-of-the-day",
        "explainers",
        "markets",
        "utilities",
        "press-releases",
        "news-and-commentary",
    ]

    # Note: Article extraction now handled by trafilatura
    # No need for manual CSS selectors - trafilatura automatically removes:
    # - WordPress embeds and separators
    # - Navigation, ads, sidebars
    # - Social sharing buttons
    # - Author bios
    # - Newsletter CTAs

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize scraper with article converter."""
        super().__init__(*args, **kwargs)

        # Use article converter
        self._markdown = ArticleConverter()

        # Track processed URLs across categories to avoid duplicates
        self._session_processed_urls: set[str] = set()

    def _build_category_url(self, category: str, page: int) -> str:
        """
        Build URL for a category page.

        Args:
            category: Category path (e.g., "storage/battery")
            page: 1-indexed page number

        Returns:
            Full URL for the category page
        """
        if page == 1:
            return f"{self.base_url}/category/{category}/"
        return f"{self.base_url}/category/{category}/page/{page}/"

    def _build_homepage_url(self, page: int) -> str:
        """
        Build URL for a homepage page.

        Args:
            page: 1-indexed page number

        Returns:
            Full URL for the homepage page
        """
        if page == 1:
            return f"{self.base_url}/"
        return f"{self.base_url}/page/{page}/"

    def _wait_for_content(self, timeout: int = 10) -> None:
        """Wait for article content to load."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".post, article"))
            )
            time.sleep(0.5)  # Small buffer for render
        except TimeoutException:
            self.logger.warning("Timeout waiting for content")

    def _get_max_pages_from_html(self, html: str) -> Optional[int]:
        """
        Extract max page number from pagination element in HTML.

        RenewEconomy pages show pagination with the last page number:
        <div class="wp-block-query-pagination-numbers">
            ...
            <a class="page-numbers" href=".../page/214/">214</a>
        </div>

        Args:
            html: HTML content of the page

        Returns:
            Maximum page number or None if not found
        """
        soup = BeautifulSoup(html, "lxml")

        # Find pagination container
        pagination = soup.select_one(".wp-block-query-pagination-numbers")
        if not pagination:
            return None

        # Find all page number links
        page_links = pagination.select("a.page-numbers")
        if not page_links:
            return None

        # Last link contains the maximum page number
        last_link = page_links[-1]
        try:
            return int(last_link.get_text(strip=True))
        except ValueError:
            return None

    def _extract_jsonld_dates(self, html: str) -> dict[str, Optional[str]]:
        """
        Extract dates from JSON-LD structured data on an article page.

        RenewEconomy articles contain JSON-LD with schema.org Article type
        in a @graph array:
        {
            "@graph": [
                {
                    "@type": "Article",
                    "datePublished": "2025-12-23T01:59:09+00:00",
                    "dateModified": "2025-12-23T01:59:15+00:00"
                }
            ]
        }

        Args:
            html: HTML content of the article page

        Returns:
            Dict with keys: date_published, date_modified
            Values are ISO date strings (YYYY-MM-DD) or None
        """
        result: dict[str, Optional[str]] = {
            "date_published": None,
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
                        if "datePublished" in item and item["datePublished"]:
                            result["date_published"] = self._parse_iso_date(
                                item["datePublished"]
                            )
                        if "dateModified" in item and item["dateModified"]:
                            result["date_modified"] = self._parse_iso_date(
                                item["dateModified"]
                            )

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
            date_str: ISO date like "2025-12-23T01:59:09+00:00"

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
        Scrape RenewEconomy articles.

        Workflow:
        1. Iterate through all categories
        2. For each category, get max pages and scrape all pages
        3. Track URLs to avoid duplicates across categories
        4. Fall back to homepage for any uncategorized articles
        5. For each article: fetch page, extract JSON-LD dates and content
        6. Save article as Markdown with metadata sidecar

        Returns:
            ScraperResult with statistics and article metadata
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        try:
            # Phase 1: Scrape all categories
            for category in self.CATEGORIES:
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    result.status = "cancelled"
                    break

                self._scrape_category(category, result)

            # Phase 2: Homepage fallback (if not cancelled)
            if result.status != "cancelled":
                self._scrape_homepage_fallback(result)

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

    def _scrape_category(self, category: str, result: ScraperResult) -> None:
        """
        Scrape all pages of a single category.

        Strategy:
        1. Try to get max pages from pagination element on first page
        2. If pagination found, scrape up to max_pages
        3. If no pagination, continue scraping until 2 consecutive empty pages

        Args:
            category: Category path (e.g., "storage/battery")
            result: ScraperResult to update
        """
        self.logger.info(f"Scraping category: {category}")

        page_num = 1
        max_pages: Optional[int] = None
        consecutive_empty_pages = 0

        while True:
            if self.check_cancelled():
                break

            # Apply user's max_pages limit if set
            if self.max_pages and page_num > self.max_pages:
                self.logger.info(f"Reached max pages limit ({self.max_pages})")
                break

            # If we know max_pages and we've exceeded it, stop
            if max_pages and page_num > max_pages:
                break

            page_url = self._build_category_url(category, page_num)

            if max_pages:
                self.logger.info(f"Scraping {category} page {page_num}/{max_pages}")
            else:
                self.logger.info(f"Scraping {category} page {page_num}")

            try:
                self.driver.get(page_url)

                # Check for redirect (end of pagination)
                current_url = self.driver.current_url
                if page_num > 1 and (
                    f"/category/{category}" not in current_url
                    or "/page/" not in current_url
                ):
                    self.logger.info(
                        f"Category {category} pagination ended (redirected to {current_url})"
                    )
                    break

                self._wait_for_content()
                page_html = self.driver.page_source

                # On first page, try to get max pages from pagination
                if page_num == 1:
                    max_pages = self._get_max_pages_from_html(page_html)
                    if max_pages:
                        self.logger.info(f"Category '{category}' has {max_pages} pages")
                    else:
                        self.logger.info(
                            f"No pagination found for {category}, will continue until empty"
                        )

                # Parse articles from listing page
                articles = self.parse_page(page_html)

                if not articles:
                    consecutive_empty_pages += 1
                    self.logger.debug(
                        f"No articles on {category} page {page_num} "
                        f"({consecutive_empty_pages} consecutive empty)"
                    )
                    # Stop after 2 consecutive empty pages
                    if consecutive_empty_pages >= 2:
                        self.logger.info(
                            f"Stopping {category}: {consecutive_empty_pages} "
                            "consecutive empty pages"
                        )
                        break
                else:
                    consecutive_empty_pages = 0
                    result.scraped_count += len(articles)
                    self.logger.info(
                        f"Found {len(articles)} articles on {category} page {page_num}"
                    )

                    # Process each article
                    for article in articles:
                        if self.check_cancelled():
                            break

                        # Skip if already processed in this session
                        if article.url in self._session_processed_urls:
                            self.logger.debug(f"Already seen in session: {article.title}")
                            continue

                        self._session_processed_urls.add(article.url)

                        # Add category to tags
                        article.tags.append(category.split("/")[-1])
                        article.extra["category"] = category

                        self._process_article(article, result)
                        self._polite_delay()

            except Exception as e:
                self.logger.error(f"Error on {category} page {page_num}: {e}")
                result.errors.append(f"{category} page {page_num}: {str(e)}")
                # Don't stop on error, try next page
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 2:
                    self.logger.info(
                        f"Stopping {category}: too many consecutive failures"
                    )
                    break

            page_num += 1
            self._polite_delay()

    def _scrape_homepage_fallback(self, result: ScraperResult) -> None:
        """
        Scrape homepage pages to catch any uncategorized articles.

        Args:
            result: ScraperResult to update
        """
        self.logger.info(
            f"Homepage fallback: checking {self.homepage_fallback_pages} pages"
        )

        for page_num in range(1, self.homepage_fallback_pages + 1):
            if self.check_cancelled():
                break

            # Apply max_pages limit if set
            if self.max_pages and page_num > self.max_pages:
                break

            page_url = self._build_homepage_url(page_num)
            self.logger.info(f"Scraping homepage page {page_num}")

            try:
                self.driver.get(page_url)

                # Check for redirect (end of pagination)
                current_url = self.driver.current_url
                if page_num > 1 and current_url == f"{self.base_url}/":
                    self.logger.info("Homepage pagination ended (redirected)")
                    break

                self._wait_for_content()
                page_html = self.driver.page_source

                # Parse articles from listing page
                articles = self.parse_page(page_html)

                if not articles:
                    self.logger.debug(f"No articles on homepage page {page_num}")
                    continue

                # Count new articles (not seen in categories)
                new_articles = [
                    a for a in articles if a.url not in self._session_processed_urls
                ]
                self.logger.info(
                    f"Found {len(new_articles)} new articles on homepage page {page_num}"
                )

                result.scraped_count += len(new_articles)

                # Process each new article
                for article in new_articles:
                    if self.check_cancelled():
                        break

                    self._session_processed_urls.add(article.url)
                    article.extra["category"] = "homepage"

                    self._process_article(article, result)
                    self._polite_delay()

            except Exception as e:
                self.logger.error(f"Error on homepage page {page_num}: {e}")
                result.errors.append(f"Homepage page {page_num}: {str(e)}")

            self._polite_delay()

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """
        Parse listing page and extract article metadata.

        CSS Selectors:
        - Articles: .post
        - Title: h1, h2, h3, h4, h5, h6
        - Link: a[href] (filtered to exclude category/author/tag)
        - Category: .post-primary-category

        Args:
            page_source: HTML source of the listing page

        Returns:
            List of DocumentMetadata for articles found
        """
        soup = BeautifulSoup(page_source, "lxml")
        articles: list[DocumentMetadata] = []

        # Find all post elements
        post_elements = soup.select(".post")
        self.logger.debug(f"Found {len(post_elements)} post elements")

        for post_el in post_elements:
            try:
                doc = self._parse_post_item(post_el)
                if doc:
                    articles.append(doc)
            except Exception as e:
                self.logger.warning(f"Failed to parse post: {e}")

        return articles

    def _parse_post_item(self, post_el: Any) -> Optional[DocumentMetadata]:
        """
        Parse a single post element from the listing page.

        Args:
            post_el: BeautifulSoup post element

        Returns:
            DocumentMetadata or None if parsing fails
        """
        # Find article link (exclude category/author/tag links)
        article_url = self._extract_article_url(post_el)
        if not article_url:
            return None

        # Title from heading
        title_el = post_el.select_one("h1, h2, h3, h4, h5, h6")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            self.logger.debug(f"No title found for article: {article_url}")
            return None

        # Category
        category_el = post_el.select_one(".post-primary-category")
        category = category_el.get_text(strip=True) if category_el else ""

        # Build tags
        tags = ["RenewEconomy"]
        if category:
            tags.append(category)

        # Create filename from title
        safe_title = sanitize_filename(title)
        filename = f"{safe_title[:100]}.md"

        return DocumentMetadata(
            url=article_url,
            title=title,
            filename=filename,
            publication_date=None,  # Will be filled from JSON-LD
            tags=tags,
            source_page=self.base_url,
            organization="RenewEconomy",
            document_type="Article",
            extra={
                "category": category,
                "content_type": "article",
            },
        )

    def _extract_article_url(self, post_el: Any) -> Optional[str]:
        """
        Extract article URL from a post element.

        Filters out category, author, and tag links.

        Args:
            post_el: BeautifulSoup post element

        Returns:
            Article URL or None
        """
        # Find all links in the post
        links = post_el.select("a[href]")

        for link in links:
            href = link.get("href", "")
            if not href:
                continue

            # Skip non-article links
            skip_patterns = ["/category/", "/author/", "/tag/", "#"]
            if any(pattern in href for pattern in skip_patterns):
                continue

            # Must be a RenewEconomy URL
            if "reneweconomy.com.au" in href:
                return href

            # Handle relative URLs
            if href.startswith("/") and not any(
                href.startswith(p) for p in ["/category", "/author", "/tag"]
            ):
                return urljoin(self.base_url, href)

        return None

    def _process_article(
        self, article: DocumentMetadata, result: ScraperResult
    ) -> None:
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

        # Check if already processed (persistent state)
        if self._is_processed(article.url):
            self.logger.debug(f"Already processed: {article.title}")
            result.skipped_count += 1
            return

        # Stage 2: Fetch article page for JSON-LD dates and content
        try:
            self.logger.debug(f"Fetching article: {article.url}")
            self.driver.get(article.url)
            self._wait_for_content(timeout=10)
            article_html = self.driver.page_source

            # Extract JSON-LD dates
            dates = self._extract_jsonld_dates(article_html)

            # Update article metadata with full dates
            if dates["date_published"]:
                article.publication_date = dates["date_published"]
                article.extra["date_published_iso"] = dates["date_published"]
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
