"""
The Conversation scraper using Atom feed for Australian energy articles.

Fetches articles from: https://theconversation.com/topics/energy-662/articles.atom

Feed-based scraper (no Selenium/browser required).
Single-stage scraping: Feed contains full article HTML in <content> tags.
Saves article content as HTML for pipeline processing.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Optional

import feedparser  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename
from app.utils.errors import NetworkError, ParsingError
from app.utils.retry import retry_on_error


class TheConversationScraper(BaseScraper):
    """
    Atom feed-based scraper for The Conversation energy articles.

    Key features:
    - Uses Atom feed which includes full article HTML content
    - No browser required (HTTP requests only)
    - Single-stage: feed contains title, author, dates, and full body
    - Saves article content as HTML
    - ~39 HTTP requests vs ~1000+ for HTML scraping
    """

    name = "the-conversation"
    display_name = "The Conversation"
    description = "Scrapes energy articles from The Conversation via Atom feed"
    base_url = "https://theconversation.com"

    # Feed configuration
    FEED_URL = "https://theconversation.com/topics/energy-662/articles.atom"
    FEED_PAGE_SIZE = 25  # Items per feed page

    # Scraper settings
    request_delay = 1.0  # Polite delay between feed requests
    default_chunk_method = "naive"  # HTML articles use naive chunking
    default_parser = "Naive"  # No OCR needed for HTML content

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    # Elements to exclude from HTML content

    # Use base class HTTP session instead of Selenium
    skip_webdriver = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize feed-based scraper."""
        super().__init__(*args, **kwargs)

    def scrape(self) -> Generator[dict, None, ScraperResult]:
        """
        Scrape The Conversation energy articles via Atom feed.

        Workflow:
        1. Check for last scrape date (incremental mode)
        2. Paginate through feed pages
        3. Parse each feed entry
        4. Extract HTML content
        5. Save as .html with .json metadata sidecar
        6. Update last scrape date on success

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
        self._newest_article_date = None

        page = 1
        consecutive_empty_pages = 0

        try:
            while True:
                if self.check_cancelled():
                    result.status = "cancelled"
                    break

                # Apply max_pages limit
                if self.max_pages and page > self.max_pages:
                    self.logger.info(f"Reached max pages limit ({self.max_pages})")
                    break

                # Fetch and parse feed page
                feed_url = self._build_feed_url(page)
                self.logger.info(f"Fetching feed page {page}: {feed_url}")

                entries = self._fetch_feed_page(feed_url)

                if not entries:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 2:
                        self.logger.info("End of feed reached (2 empty pages)")
                        break
                    page += 1
                    continue

                consecutive_empty_pages = 0
                self.logger.info(f"Processing {len(entries)} entries from page {page}")

                # Process each entry
                for entry in entries:
                    if self.check_cancelled():
                        break
                    yield from self._process_feed_entry(entry, result)

                page += 1
                self._polite_delay()

            # Set final status
            if result.status != "cancelled":
                self._finalize_result(result)

            # Update last scrape date on success
            if result.status in ("completed", "partial") and not self.dry_run:
                self._update_last_scrape_date()

        except Exception as e:
            self.logger.error(f"Scraper failed: {e}")
            result.errors.append(str(e))
            result.status = "failed"

        return result

    def _build_feed_url(self, page: int) -> str:
        """
        Build URL for a feed page.

        Args:
            page: 1-indexed page number

        Returns:
            Full feed URL with pagination
        """
        if page == 1:
            return self.FEED_URL
        return f"{self.FEED_URL}?page={page}"

    @retry_on_error(exceptions=(NetworkError,), max_attempts=None)
    def _fetch_feed_page(self, url: str) -> list[Any]:
        """Fetch and parse a feed page with standardized retry."""
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        response = self._request_with_retry(self._session, "get", url, timeout=30)
        if response is None:
            raise NetworkError(
                "Request returned None response",
                scraper=self.name,
                recoverable=True,
                context={"url": url},
            )
        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            raise ParsingError(
                "Feed parse error",
                scraper=self.name,
                recoverable=False,
                context={"url": url},
            )

        return feed.entries

    def _process_feed_entry(self, entry: Any, result: ScraperResult) -> Generator[dict, None, None]:
        """
        Process a single feed entry.

        Args:
            entry: feedparser entry object
            result: ScraperResult to update

        Yields:
            dict — document metadata if article is downloaded
        """
        # Extract URL
        url = entry.get("link", "")
        if not url:
            return

        # Cross-page deduplication
        if url in self._session_processed_urls:
            self.logger.debug(f"Already seen in session: {url}")
            return

        self._session_processed_urls.add(url)
        result.scraped_count += 1

        # Check persistent state
        if self._is_processed(url):
            self.logger.debug(f"Already processed: {url}")
            result.skipped_count += 1
            return

        # Extract metadata from entry
        title = entry.get("title", "")
        if not title:
            self.logger.warning(f"No title for entry: {url}")
            return

        # Parse dates (feedparser normalizes to struct_time)
        pub_date = self._parse_feedparser_date(entry.get("published_parsed"))
        updated_date = self._parse_feedparser_date(entry.get("updated_parsed"))

        # Track newest date for incremental scraping
        self._track_article_date(pub_date)

        # Check date filter for incremental mode
        if self._from_date and pub_date:
            if pub_date < self._from_date:
                self.logger.debug(
                    f"Skipping old article: {pub_date} < {self._from_date}"
                )
                result.skipped_count += 1
                return

        # Extract author
        author = ""
        if entry.get("authors"):
            author = entry["authors"][0].get("name", "")
        elif entry.get("author"):
            author = entry["author"]

        # Extract article ID from feed ID
        article_id = self._extract_article_id(entry.get("id", ""))

        # Build tags
        tags = ["The Conversation", "Energy"]

        # Create safe filename
        safe_title = sanitize_filename(title)[:100]
        filename = f"{safe_title}.html"

        # Create DocumentMetadata
        metadata = DocumentMetadata(
            url=url,
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.FEED_URL,
            organization="The Conversation",
            document_type="Article",
            extra={
                "author": author,
                "article_id": article_id,
                "updated_date": updated_date,
                "summary": entry.get("summary", ""),
                "abstract": entry.get("summary", ""),  # Use summary as abstract
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

        # Extract HTML content from feed
        content_html = self._extract_content_html(entry)
        if not content_html:
            self.logger.warning(f"No content for: {title}")
            result.failed_count += 1
            return

        # Save article (HTML directly)
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {title}")
            result.downloaded_count += 1
            yield metadata.to_dict()
        else:
            saved_path = self._save_article(metadata, content_html)
            if saved_path:
                self._mark_processed(url, {"title": title})
                result.downloaded_count += 1
                yield metadata.to_dict()
            else:
                result.failed_count += 1

    def _extract_content_html(self, entry: Any) -> str:
        """
        Extract HTML content from feed entry.

        The Conversation's Atom feed includes full article HTML
        in the <content type="html"> element.

        Args:
            entry: feedparser entry

        Returns:
            HTML content string
        """
        # feedparser stores content in 'content' list
        if entry.get("content"):
            for content_item in entry["content"]:
                if content_item.get("type") == "text/html":
                    return content_item.get("value", "")
                # fallback to any content
                if content_item.get("value"):
                    return content_item["value"]

        # Fallback to summary (usually truncated)
        return entry.get("summary", "")

    def _parse_feedparser_date(self, time_struct: Any) -> Optional[str]:
        """
        Convert feedparser time struct to YYYY-MM-DD string.

        Args:
            time_struct: struct_time from feedparser

        Returns:
            Date string or None
        """
        if not time_struct:
            return None

        try:
            from time import strftime

            return strftime("%Y-%m-%d", time_struct)
        except (ValueError, TypeError):
            return None

    def _extract_article_id(self, feed_id: str) -> str:
        """
        Extract numeric article ID from feed ID.

        Feed ID format: "theconversation.com,2011:article/270866"

        Args:
            feed_id: Full feed ID string

        Returns:
            Article ID (e.g., "270866") or empty string
        """
        if "/" in feed_id:
            return feed_id.split("/")[-1]
        return ""
