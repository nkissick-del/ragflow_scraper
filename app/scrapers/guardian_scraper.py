"""
The Guardian Australia scraper using the Guardian Open Platform API.

Fetches articles from: https://content.guardianapis.com
Filtered by Australian energy-related subject tags.

API-based scraper (no Selenium/browser required).
Single-stage scraping: API returns all data including full article body.
Saves article content as Markdown for RAGFlow indexing.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

import requests

from app.config import Config
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename, ArticleConverter
from app.utils.retry import retry_on_error
from app.utils.errors import NetworkError, ParsingError


class GuardianScraper(BaseScraper):
    """
    API-based scraper for The Guardian Australia energy news articles.

    Key features:
    - Uses Guardian Open Platform API (no browser required)
    - Multi-tag scraping strategy with cross-tag deduplication
    - Single-stage: API returns headline, byline, dates, and full body
    - Extracts article content as Markdown
    - Subject tags: energy, renewables, coal, nuclear, climate, EVs, etc.
    """

    name = "guardian"
    display_name = "The Guardian Australia"
    description = "Scrapes energy articles from The Guardian Australia via API"
    base_url = "https://www.theguardian.com"

    # API configuration
    API_BASE_URL = "https://content.guardianapis.com"
    API_PAGE_SIZE = 50  # Max is 200, but 50 is reasonable for rate limiting

    # Guardian-specific settings
    request_delay = 1.0  # Polite API usage (limit is 12/sec)
    default_chunk_method = "naive"  # Markdown articles need naive chunking
    default_parser = "Naive"  # No OCR needed for markdown

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    # Subject tags to scrape (Australian energy sector coverage)
    SUBJECT_TAGS = [
        # Tier 1 - Primary energy tags
        "australia-news/energy-australia",
        "environment/renewableenergy",
        "environment/energy-storage",
        "australia-news/nuclear-power",
        # Tier 2 - Fossil fuels
        "environment/coal",
        "environment/gas",
        "environment/coal-seam-gas",
        # Tier 3 - Renewables detail
        "environment/solarpower",
        "environment/windpower",
        "environment/hydropower",
        "environment/hydrogen-power",
        # Tier 4 - Policy/Climate
        "environment/climate-crisis",
        "environment/carbon-emissions",
        "environment/carbon-capture-and-storage",
        # Tier 5 - Grid impacts
        "environment/electric-vehicles-australia",
        "environment/electric-cars",
    ]

    # Note: Article extraction now handled by trafilatura
    # No need for manual CSS selectors - trafilatura automatically removes:
    # - Navigation, ads, sidebars
    # - Social sharing buttons
    # - Author bios
    # - Newsletter CTAs

    # Use base class HTTP session instead of Selenium
    skip_webdriver = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize API-based scraper."""
        super().__init__(*args, **kwargs)

        # API configuration
        self._api_key = Config.GUARDIAN_API_KEY
        if not self._api_key:
            self.logger.warning(
                "GUARDIAN_API_KEY not configured - scraper will fail"
            )

        # Article converter for body HTML
        self._markdown = ArticleConverter()

    @retry_on_error(exceptions=(NetworkError,), max_attempts=5)
    def _api_request(
        self,
        endpoint: str = "/search",
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make authenticated Guardian API request with standardized retry."""
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        url = f"{self.API_BASE_URL}{endpoint}"
        request_params: dict[str, Any] = {"api-key": self._api_key}
        if params:
            request_params.update(params)

        response = self._request_with_retry(
            self._session,
            "get",
            url,
            params=request_params,
            timeout=30,
        )
        
        if response is None:
            raise NetworkError(
                f"Failed to fetch Guardian API response",
                scraper=self.name,
                context={"url": url, "endpoint": endpoint, "params": request_params},
            )
        
        try:
            return response.json()
        except ValueError as exc:
            raise ParsingError(
                f"Failed to parse Guardian API response for {url}",
                scraper=self.name,
                context={"url": url},
            ) from exc

    def _build_search_params(
        self,
        tag: str,
        page: int = 1,
        from_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build API search parameters for a tag.

        Args:
            tag: Guardian tag path (e.g., "environment/renewableenergy")
            page: Page number (1-indexed)
            from_date: Optional date filter (YYYY-MM-DD) for incremental scraping

        Returns:
            Dictionary of API parameters
        """
        params: dict[str, Any] = {
            "tag": tag,
            "page": page,
            "page-size": self.API_PAGE_SIZE,
            "order-by": "newest",
            "show-fields": "body,headline,byline,trailText,thumbnail",
            "show-tags": "keyword",
        }

        # Add from-date filter for incremental scraping
        if from_date:
            params["from-date"] = from_date

        return params

    def scrape(self) -> ScraperResult:
        """
        Scrape The Guardian Australia energy articles via API.

        Workflow:
        1. Check for last scrape date (incremental mode)
        2. Iterate through all subject tags
        3. For each tag, paginate through results (with from-date filter if set)
        4. Track URLs to avoid duplicates across tags
        5. Convert body HTML to Markdown
        6. Save article as Markdown with metadata sidecar
        7. Update last scrape date on success

        Returns:
            ScraperResult with statistics and article metadata
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        # Get last scrape date for incremental mode
        # First run: None = fetch all historical articles
        # Subsequent runs: use from-date to only fetch new articles
        self._from_date = self._get_last_scrape_date()

        # Reset newest article tracker for this scrape
        self._newest_article_date = None

        try:
            # Scrape all subject tags
            for tag in self.SUBJECT_TAGS:
                if self.check_cancelled():
                    self.logger.info("Scraper cancelled")
                    result.status = "cancelled"
                    break

                self._scrape_tag(tag, result)

            # Set final status
            if result.status != "cancelled":
                if result.errors and result.downloaded_count == 0:
                    result.status = "failed"
                elif result.errors:
                    result.status = "partial"
                else:
                    result.status = "completed"

            # Update last scrape date on success (or partial success)
            if result.status in ("completed", "partial") and not self.dry_run:
                if self._newest_article_date:
                    self._update_last_scrape_date(self._newest_article_date)
                else:
                    # No new articles found, use today's date
                    today = datetime.now().strftime("%Y-%m-%d")
                    self._update_last_scrape_date(today)

        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _scrape_tag(self, tag: str, result: ScraperResult) -> None:
        """
        Scrape all pages of a single subject tag via API.

        Args:
            tag: Subject tag path (e.g., "australia-news/energy-australia")
            result: ScraperResult to update
        """
        from_date_str = f" (from {self._from_date})" if self._from_date else ""
        self.logger.info(f"Scraping tag via API: {tag}{from_date_str}")

        page = 1
        total_pages: Optional[int] = None

        while True:
            if self.check_cancelled():
                break

            # Apply user's max_pages limit
            if self.max_pages and page > self.max_pages:
                self.logger.info(f"Reached max pages limit ({self.max_pages})")
                break

            # Stop if we've exceeded known pages
            if total_pages and page > total_pages:
                break

            try:
                params = self._build_search_params(tag, page, self._from_date)
                response = self._api_request(params=params)

                if response is None:
                    raise NetworkError(
                        f"Failed to fetch results for tag {tag}",
                        scraper=self.name,
                        context={"tag": tag, "page": page},
                    )

                api_data = response.get("response", {})

                # Get pagination info on first page
                if page == 1:
                    total_pages = api_data.get("pages", 1)
                    total_results = api_data.get("total", 0)
                    self.logger.info(
                        f"Tag '{tag}' has {total_results} results "
                        f"across {total_pages} pages"
                    )

                # Process results
                results = api_data.get("results", [])
                if not results:
                    self.logger.debug(f"No results on {tag} page {page}")
                    break

                self.logger.info(
                    f"Processing {len(results)} articles from {tag} page {page}"
                )

                for item in results:
                    if self.check_cancelled():
                        break
                    self._process_api_result(item, tag, result)

                page += 1
                self._polite_delay()

            except requests.RequestException as e:
                self.logger.error(f"API error for tag {tag} page {page}: {e}")
                result.errors.append(f"{tag} page {page}: {str(e)}")
                break

    def _process_api_result(
        self,
        item: dict[str, Any],
        source_tag: str,
        result: ScraperResult,
    ) -> None:
        """
        Process a single API result item.

        Args:
            item: API result dictionary
            source_tag: The tag this result came from
            result: ScraperResult to update
        """
        url = item.get("webUrl", "")

        # Skip if already processed in this session (cross-tag dedup)
        if url in self._session_processed_urls:
            self.logger.debug(f"Already seen in session: {url}")
            return

        self._session_processed_urls.add(url)
        result.scraped_count += 1

        # Check if already in persistent state
        if self._is_processed(url):
            self.logger.debug(f"Already processed: {url}")
            result.skipped_count += 1
            return

        # Extract metadata from API response
        fields = item.get("fields", {})
        title = fields.get("headline") or item.get("webTitle", "")

        if not title:
            self.logger.warning(f"No title for article: {url}")
            return

        # Parse publication date (use base class ISO parser)
        pub_date = self._parse_iso_date(item.get("webPublicationDate", ""))

        # Track newest article date for incremental scraping
        self._track_article_date(pub_date)

        # Extract author from byline
        author = fields.get("byline", "")

        # Build tags list from API tags
        tags = ["The Guardian Australia"]
        for api_tag in item.get("tags", []):
            if api_tag.get("webTitle"):
                tags.append(api_tag["webTitle"])

        # Create safe filename
        safe_title = sanitize_filename(title)
        filename = f"{safe_title[:100]}.md"

        # Create DocumentMetadata
        metadata = DocumentMetadata(
            url=url,
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.base_url,
            organization="The Guardian Australia",
            document_type="Article",
            extra={
                "author": author,
                "subject_tag": source_tag,
                "api_id": item.get("id", ""),
                "section": item.get("sectionName", ""),
                "trail_text": fields.get("trailText", ""),
                "abstract": fields.get("trailText", ""),  # Use trail text as abstract
                "content_type": "article",
            },
        )

        # Check exclusion
        exclusion_reason = self.should_exclude_document(metadata)
        if exclusion_reason:
            self.logger.debug(f"Excluded: {title} ({exclusion_reason})")
            result.excluded_count += 1
            result.excluded.append(
                ExcludedDocument(
                    title=title,
                    url=url,
                    reason=exclusion_reason,
                ).to_dict()
            )
            return

        # Get body content
        body_html = fields.get("body", "")
        if not body_html:
            self.logger.warning(f"No body content for: {title}")
            result.failed_count += 1
            return

        # Convert body HTML to Markdown
        content = self._convert_body_to_markdown(body_html)

        # Save article
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {title}")
            result.downloaded_count += 1
            result.documents.append(metadata.to_dict())
        else:
            saved_path = self._save_article(metadata, content)
            if saved_path:
                result.downloaded_count += 1
                result.documents.append(metadata.to_dict())
                self._mark_processed(url, {"title": title})
            else:
                result.failed_count += 1

    def _convert_body_to_markdown(self, body_html: str) -> str:
        """
        Convert API body HTML to GFM Markdown.

        The API body is cleaner than scraped HTML (no nav, ads, etc.)
        but still needs conversion to Markdown.

        Args:
            body_html: HTML from API body field

        Returns:
            GFM-compliant Markdown
        """
        # Wrap in article tag for the converter
        full_html = f"<article>{body_html}</article>"

        # ArticleConverter ignores selectors, extracts content automatically
        return self._markdown.convert(full_html)
