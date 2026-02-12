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

from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin
from app.scrapers.jsonld_mixin import JSONLDDateExtractionMixin
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.scrapers.pagination_guard import PaginationGuard
from app.utils import sanitize_filename, ArticleConverter


class RenewEconomyScraper(FlareSolverrPageFetchMixin, JSONLDDateExtractionMixin, BaseScraper):
    """
    Scraper for RenewEconomy news articles.

    Key features:
    - Uses FlareSolverr for rendered page fetching
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

    skip_webdriver = True  # Use FlareSolverr instead of Selenium

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

    def _get_max_pages_from_html(self, html: str) -> Optional[int]:
        """
        Extract max page number from pagination element in HTML.

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

        Args:
            category: Category path (e.g., "storage/battery")
            result: ScraperResult to update
        """
        self.logger.info(f"Scraping category: {category}")

        page_num = 1
        max_pages: Optional[int] = None
        guard = PaginationGuard()

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
                # Fetch page via FlareSolverr (full result for redirect detection)
                fs_result = self.fetch_rendered_page_full(page_url)

                if not fs_result.success or not fs_result.html:
                    self.logger.warning(f"Failed to fetch {category} page {page_num}")
                    should_stop, reason = guard.check_page([])
                    if should_stop:
                        self.logger.info(f"Stopping {category}: {reason}")
                        break
                    page_num += 1
                    self._polite_delay()
                    continue

                # Check for redirect (end of pagination)
                final_url = fs_result.url
                if page_num > 1 and final_url and (
                    f"/category/{category}" not in final_url
                    or "/page/" not in final_url
                ):
                    self.logger.info(
                        f"Category {category} pagination ended (redirected to {final_url})"
                    )
                    break

                page_html = fs_result.html

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
                article_urls = [a.url for a in articles]

                should_stop, reason = guard.check_page(article_urls)
                if should_stop:
                    self.logger.info(
                        f"Pagination guard stopped {category}: {reason}"
                    )
                    break

                if articles:
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
                # Errors count as empty pages for guard purposes
                should_stop, reason = guard.check_page([])
                if should_stop:
                    self.logger.info(
                        f"Stopping {category}: {reason}"
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
                # Fetch page via FlareSolverr (full result for redirect detection)
                fs_result = self.fetch_rendered_page_full(page_url)

                if not fs_result.success or not fs_result.html:
                    self.logger.warning(f"Failed to fetch homepage page {page_num}")
                    continue

                # Check for redirect (end of pagination)
                final_url = fs_result.url
                if page_num > 1 and final_url and final_url.rstrip("/") == self.base_url:
                    self.logger.info("Homepage pagination ended (redirected)")
                    break

                page_html = fs_result.html

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
            article_html = self.fetch_rendered_page(article.url)
            if not article_html:
                self.logger.warning(f"Empty response for article: {article.url}")
                result.failed_count += 1
                return

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
