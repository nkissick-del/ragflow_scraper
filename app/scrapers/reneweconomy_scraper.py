"""
RenewEconomy (reneweconomy.com.au) scraper using WordPress REST API.

Fetches articles from: https://reneweconomy.com.au/wp-json/wp/v2/posts
API-based scraper (no FlareSolverr/browser required).
Single-stage scraping: API returns full article content, categories, dates.
Saves article content as HTML for pipeline processing.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any, Optional

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename
from app.utils.retry import retry_on_error
from app.utils.errors import NetworkError, ParsingError


class RenewEconomyScraper(BaseScraper):
    """
    API-based scraper for RenewEconomy Australian energy news articles.

    Key features:
    - Uses WordPress REST API (no browser required)
    - Single-stage: API returns title, content, dates, categories
    - Category ID→name resolution via /categories endpoint
    - Incremental scraping via `after` date parameter
    - Saves article content as HTML
    """

    name = "reneweconomy"
    display_name = "RenewEconomy"
    description = "Scrapes articles from RenewEconomy (reneweconomy.com.au) via WordPress API"
    base_url = "https://reneweconomy.com.au"

    # API configuration
    API_BASE_URL = "https://reneweconomy.com.au/wp-json/wp/v2"
    API_PAGE_SIZE = 100  # WP API max per_page

    # RenewEconomy-specific settings
    request_delay = 0.5  # API is lighter than HTML scraping
    default_chunk_method = "naive"  # HTML articles use naive chunking
    default_parser = "Naive"  # No OCR needed for HTML content

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    # Use base class HTTP session instead of Selenium
    skip_webdriver = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize API-based scraper."""
        super().__init__(*args, **kwargs)

        # Category ID→name cache (populated on first scrape)
        self._categories: dict[int, str] = {}

    @retry_on_error(exceptions=(NetworkError,), max_attempts=5)
    def _api_request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> tuple[Any, dict[str, str]]:
        """
        Make WordPress REST API request with retry.

        Args:
            endpoint: API path (e.g., "/posts", "/categories")
            params: Query parameters

        Returns:
            Tuple of (parsed JSON response, response headers dict)

        Raises:
            NetworkError: If request fails
            ParsingError: If JSON parsing fails
            RuntimeError: If session not initialized
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        url = f"{self.API_BASE_URL}{endpoint}"

        response = self._request_with_retry(
            self._session,
            "get",
            url,
            params=params or {},
            timeout=30,
        )

        if response is None:
            raise NetworkError(
                f"Failed to fetch {endpoint}",
                scraper=self.name,
                context={"url": url, "endpoint": endpoint},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ParsingError(
                f"Failed to parse API response for {url}",
                scraper=self.name,
                context={"url": url},
            ) from exc

        headers = dict(response.headers)
        return data, headers

    def _fetch_categories(self) -> dict[int, str]:
        """
        Fetch all WordPress categories and return ID→name mapping.

        Returns:
            Dict mapping category ID (int) to category name (str)
        """
        categories: dict[int, str] = {}
        page = 1

        while True:
            params = {"per_page": 100, "page": page}
            try:
                data, headers = self._api_request("/categories", params)  # type: ignore[misc]
            except (NetworkError, ParsingError) as e:
                self.logger.warning(f"Failed to fetch categories page {page}: {e}")
                break

            if not data:
                break

            for cat in data:
                cat_id = cat.get("id")
                cat_name = cat.get("name", "")
                if cat_id is not None and cat_name:
                    categories[cat_id] = cat_name

            # Check if more pages
            try:
                total_pages = int(headers.get("X-WP-TotalPages", "1"))
            except ValueError:
                break
            if page >= total_pages:
                break
            page += 1

        self.logger.info(f"Fetched {len(categories)} categories")
        return categories

    def _build_posts_params(
        self,
        page: int = 1,
        from_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build API query parameters for the posts endpoint.

        Args:
            page: Page number (1-indexed)
            from_date: Optional date filter (YYYY-MM-DD) for incremental scraping

        Returns:
            Dictionary of API parameters
        """
        params: dict[str, Any] = {
            "per_page": self.API_PAGE_SIZE,
            "page": page,
            "orderby": "date",
            "order": "desc",
        }

        if from_date:
            params["after"] = f"{from_date}T00:00:00"

        return params

    def scrape(self) -> Generator[dict, None, ScraperResult]:
        """
        Scrape RenewEconomy articles via WordPress REST API.

        Workflow:
        1. Fetch category ID→name mapping
        2. Check for last scrape date (incremental mode)
        3. Paginate through all posts (with after filter if set)
        4. Deduplicate by URL
        5. Save article HTML with metadata sidecar
        7. Update last scrape date on success

        Yields:
            dict — document metadata for each downloaded article

        Returns:
            ScraperResult with statistics
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        # Get last scrape date for incremental mode
        self._from_date = self._get_last_scrape_date()

        # Reset newest article tracker for this scrape
        self._newest_article_date = None

        try:
            # Fetch categories for ID→name resolution
            self._categories = self._fetch_categories()

            # Paginate through posts
            yield from self._scrape_posts(result)

            # Set final status
            if result.status != "cancelled":
                if result.errors and result.downloaded_count == 0:
                    result.status = "failed"
                elif result.errors:
                    result.status = "partial"
                else:
                    result.status = "completed"

            # Update last scrape date on success
            if result.status in ("completed", "partial") and not self.dry_run:
                if self._newest_article_date:
                    self._update_last_scrape_date(self._newest_article_date)
                else:
                    today = datetime.now().strftime("%Y-%m-%d")
                    self._update_last_scrape_date(today)

        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _scrape_posts(self, result: ScraperResult) -> Generator[dict, None, None]:
        """
        Paginate through WordPress posts API.

        Args:
            result: ScraperResult to update

        Yields:
            dict — document metadata for each downloaded article
        """
        from_date_str = f" (from {self._from_date})" if self._from_date else ""
        self.logger.info(f"Scraping posts via API{from_date_str}")

        page = 1
        total_pages: Optional[int] = None

        while True:
            if self.check_cancelled():
                self.logger.info("Scraper cancelled")
                result.status = "cancelled"
                break

            # Apply user's max_pages limit
            if self.max_pages and page > self.max_pages:
                self.logger.info(f"Reached max pages limit ({self.max_pages})")
                break

            # Stop if we've exceeded known pages
            if total_pages is not None and page > total_pages:
                break

            try:
                params = self._build_posts_params(page, self._from_date)
                data, headers = self._api_request("/posts", params)  # type: ignore[misc]

                # Get pagination info on first page
                if page == 1:
                    try:
                        total_pages = int(headers.get("X-WP-TotalPages", "1"))
                        total_results = int(headers.get("X-WP-Total", "0"))
                    except ValueError:
                        total_pages = 1
                        total_results = len(data) if data else 0
                    self.logger.info(
                        f"Found {total_results} posts across {total_pages} pages"
                    )

                # Process results
                if not data:
                    self.logger.debug(f"No results on page {page}")
                    break

                self.logger.info(
                    f"Processing {len(data)} posts from page {page}"
                )

                for post in data:
                    if self.check_cancelled():
                        result.status = "cancelled"
                        break
                    yield from self._process_post(post, result)

                page += 1
                self._polite_delay()

            except (NetworkError, ParsingError) as e:
                self.logger.error(f"API error on page {page}: {e}")
                result.errors.append(f"Page {page}: {str(e)}")
                break

    def _process_post(
        self,
        post: dict[str, Any],
        result: ScraperResult,
    ) -> Generator[dict, None, None]:
        """
        Process a single WordPress post from the API.

        Args:
            post: WordPress post dict from API
            result: ScraperResult to update

        Yields:
            dict — document metadata if article is downloaded
        """
        url = post.get("link", "")

        # Cross-page dedup
        if url in self._session_processed_urls:
            self.logger.debug(f"Already seen in session: {url}")
            return

        self._session_processed_urls.add(url)
        result.scraped_count += 1

        # Persistent state dedup
        if self._is_processed(url):
            self.logger.debug(f"Already processed: {url}")
            result.skipped_count += 1
            return

        # Extract title
        title_obj = post.get("title", {})
        title = title_obj.get("rendered", "") if isinstance(title_obj, dict) else ""
        if not title:
            self.logger.warning(f"No title for post: {url}")
            return

        # Parse publication date
        pub_date = self._parse_iso_date(post.get("date", ""))

        # Track newest article date for incremental scraping
        self._track_article_date(pub_date)

        # Resolve category IDs to names
        category_ids = post.get("categories", [])
        category_names = [
            self._categories[cid]
            for cid in category_ids
            if cid in self._categories
        ]

        # Build tags
        tags = ["RenewEconomy"]
        tags.extend(category_names)

        # Create safe filename
        safe_title = sanitize_filename(title)
        filename = f"{safe_title[:100]}.html"

        # Create DocumentMetadata
        metadata = DocumentMetadata(
            url=url,
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.base_url,
            organization="RenewEconomy",
            document_type="Article",
            extra={
                "slug": post.get("slug", ""),
                "wp_id": post.get("id", ""),
                "categories": category_names,
                "date_modified": post.get("modified", ""),
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
        content_obj = post.get("content", {})
        body_html = content_obj.get("rendered", "") if isinstance(content_obj, dict) else ""
        if not body_html:
            self.logger.warning(f"No body content for: {title}")
            result.failed_count += 1
            return

        # Save article (HTML directly)
        body_html = self._build_article_html(body_html, metadata)

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {title}")
            result.downloaded_count += 1
            yield metadata.to_dict()
        else:
            saved_path = self._save_article(metadata, body_html)
            if saved_path:
                self._mark_processed(url, {"title": title})
                result.downloaded_count += 1
                yield metadata.to_dict()
            else:
                result.failed_count += 1

