"""
TheEnergy (theenergy.co) scraper for Australian energy news articles.

Two-phase approach:
  Phase 1 — RSS feed (recent articles with full HTML content embedded)
  Phase 2 — Sitemap backfill (historical articles, fetched via FlareSolverr)

Replaces the previous HTML-pagination approach which looped forever because
theenergy.co echoes the oldest page for any page number beyond the last real one.
"""

from __future__ import annotations

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
from collections.abc import Generator
from typing import Any, Optional

import feedparser  # type: ignore[import-untyped]

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin
from app.scrapers.jsonld_mixin import JSONLDDateExtractionMixin
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.utils import sanitize_filename, ArticleConverter


class TheEnergyScraper(FlareSolverrPageFetchMixin, JSONLDDateExtractionMixin, BaseScraper):
    """
    RSS + Sitemap scraper for TheEnergy news articles.

    Key features:
    - Phase 1: RSS feed provides ~15 recent articles with full HTML content
    - Phase 2: Sitemap XML provides ~577 historical article URLs for backfill
    - Uses FlareSolverr for fetching article pages during sitemap phase
    - JSON-LD date extraction for accurate publication dates
    - Extracts article content as Markdown
    """

    name = "theenergy"
    display_name = "The Energy"
    description = "Scrapes articles from The Energy (theenergy.co)"
    base_url = "https://theenergy.co"

    RSS_URL = "https://theenergy.co/rss"
    SITEMAP_URL = "https://theenergy.co/sitemap-articles-1.xml"

    skip_webdriver = True  # Use FlareSolverr instead of Selenium

    # TheEnergy-specific settings
    articles_per_page = 10
    request_delay = 1.0  # Polite crawling
    default_chunk_method = "naive"  # Markdown articles need naive chunking
    default_parser = "Naive"  # No OCR needed for markdown

    # No sector-based filtering for news articles
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize scraper with GFM markdown converter."""
        super().__init__(*args, **kwargs)
        self._markdown = ArticleConverter()

    # ------------------------------------------------------------------
    # Article limit helper
    # ------------------------------------------------------------------

    def _reached_limit(self, result: ScraperResult) -> bool:
        """Check whether the effective article limit has been reached."""
        if not self.max_pages:
            return False
        limit = self.max_pages * self.articles_per_page
        return result.downloaded_count + result.skipped_count >= limit

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape(self) -> Generator[dict, None, ScraperResult]:
        """
        Scrape TheEnergy articles via RSS feed + sitemap backfill.

        Yields:
            dict — document metadata for each downloaded article

        Returns:
            ScraperResult with statistics
        """
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        # Incremental mode support
        self._from_date = self._get_last_scrape_date()
        self._newest_article_date: Optional[str] = None

        try:
            # Phase 1: RSS feed (recent articles with full content)
            yield from self._scrape_rss(result)

            # Phase 2: Sitemap backfill (historical articles)
            if not self.check_cancelled() and not self._reached_limit(result):
                yield from self._scrape_sitemap(result)

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

    # ------------------------------------------------------------------
    # Phase 1 — RSS feed
    # ------------------------------------------------------------------

    def _scrape_rss(self, result: ScraperResult) -> Generator[dict, None, None]:
        """Fetch RSS feed and process entries (full HTML content in feed)."""
        self.logger.info(f"Phase 1: Fetching RSS feed from {self.RSS_URL}")

        try:
            feed_entries = self._fetch_rss_feed()
        except Exception as e:
            self.logger.error(f"RSS feed fetch failed: {e}")
            result.errors.append(f"RSS feed: {str(e)}")
            return

        if not feed_entries:
            self.logger.info("RSS feed returned no entries")
            return

        self.logger.info(f"RSS feed: {len(feed_entries)} entries")

        for entry in feed_entries:
            if self.check_cancelled():
                result.status = "cancelled"
                break
            if self._reached_limit(result):
                self.logger.info("Reached article limit during RSS phase")
                break

            yield from self._process_rss_entry(entry, result)

    def _fetch_rss_feed(self) -> list[Any]:
        """Fetch and parse the RSS feed.

        Returns:
            List of feedparser entry objects.
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        response = self._request_with_retry(
            self._session, "get", self.RSS_URL, timeout=30
        )
        if response is None:
            raise RuntimeError("RSS feed request returned None")

        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            raise RuntimeError(f"RSS feed parse error: {feed.bozo_exception}")

        return feed.entries

    def _process_rss_entry(self, entry: Any, result: ScraperResult) -> Generator[dict, None, None]:
        """Process a single RSS feed entry.

        RSS entries contain full HTML content in the description/summary,
        so no extra HTTP request is needed per article.
        """
        url = entry.get("link", "")
        if not url:
            return

        # Cross-phase deduplication
        if url in self._session_processed_urls:
            return
        self._session_processed_urls.add(url)
        result.scraped_count += 1

        # Persistent state check
        if self._is_processed(url):
            self.logger.debug(f"Already processed: {url}")
            result.skipped_count += 1
            return

        # Extract metadata
        title = entry.get("title", "")
        if not title:
            return

        pub_date = self._parse_feedparser_date(entry.get("published_parsed"))
        self._track_article_date(pub_date)

        # Incremental mode: skip old articles
        if self._from_date and pub_date and pub_date < self._from_date:
            self.logger.debug(f"Skipping old article: {pub_date} < {self._from_date}")
            result.skipped_count += 1
            return

        # Build tags
        tags = ["TheEnergy"]
        categories = [t.get("term", "") for t in entry.get("tags", [])]
        for cat in categories:
            if cat and cat not in tags:
                tags.append(cat)

        safe_title = sanitize_filename(title)[:100]
        filename = f"{safe_title}.md"

        metadata = DocumentMetadata(
            url=url,
            title=title,
            filename=filename,
            publication_date=pub_date,
            tags=tags,
            source_page=self.RSS_URL,
            organization="The Energy",
            document_type="Article",
            extra={
                "content_type": "article",
                "source": "rss",
            },
        )

        # Exclusion check
        exclusion_reason = self.should_exclude_document(metadata)
        if exclusion_reason:
            self.logger.debug(f"Excluded: {title} ({exclusion_reason})")
            result.excluded_count += 1
            result.excluded.append(
                ExcludedDocument(title=title, url=url, reason=exclusion_reason).to_dict()
            )
            return

        # Extract HTML content from RSS entry
        content_html = self._extract_rss_content(entry)
        if not content_html:
            self.logger.warning(f"No content in RSS entry: {title}")
            result.failed_count += 1
            return

        # Convert to Markdown
        content_md = self._convert_html_to_markdown(content_html)

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would save: {title}")
            result.downloaded_count += 1
            yield metadata.to_dict()
        else:
            saved_path = self._save_article(metadata, content_md, html_content=content_html)
            if saved_path:
                self._mark_processed(url, {"title": title})
                result.downloaded_count += 1
                yield metadata.to_dict()
            else:
                result.failed_count += 1

    def _extract_rss_content(self, entry: Any) -> str:
        """Extract HTML content from an RSS feed entry.

        TheEnergy RSS uses ``<description>`` with full HTML in CDATA.
        feedparser exposes this as ``entry.summary`` or ``entry.content``.
        """
        # Try content list first (some feeds use this)
        if entry.get("content"):
            for item in entry["content"]:
                value = item.get("value", "")
                if value:
                    return value

        # Fall back to summary/description
        return entry.get("summary", "")

    def _parse_feedparser_date(self, time_struct: Any) -> Optional[str]:
        """Convert feedparser time struct to YYYY-MM-DD string."""
        if not time_struct:
            return None
        try:
            from time import strftime
            return strftime("%Y-%m-%d", time_struct)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Phase 2 — Sitemap backfill
    # ------------------------------------------------------------------

    def _scrape_sitemap(self, result: ScraperResult) -> Generator[dict, None, None]:
        """Parse sitemap XML and fetch article pages for unprocessed URLs."""
        self.logger.info(f"Phase 2: Fetching sitemap from {self.SITEMAP_URL}")

        try:
            sitemap_entries = self._parse_sitemap()
        except Exception as e:
            self.logger.error(f"Sitemap fetch failed: {e}")
            result.errors.append(f"Sitemap: {str(e)}")
            return

        if not sitemap_entries:
            self.logger.info("Sitemap returned no entries")
            return

        self.logger.info(f"Sitemap: {len(sitemap_entries)} article URLs")

        for url, lastmod in sitemap_entries:
            if self.check_cancelled():
                result.status = "cancelled"
                break
            if self._reached_limit(result):
                self.logger.info("Reached article limit during sitemap phase")
                break

            yield from self._process_sitemap_article(url, lastmod, result)
            self._polite_delay()

    def _parse_sitemap(self) -> list[tuple[str, Optional[str]]]:
        """Fetch and parse the sitemap XML.

        Returns:
            List of ``(url, lastmod)`` tuples. *lastmod* may be ``None``.
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        response = self._request_with_retry(
            self._session, "get", self.SITEMAP_URL, timeout=30
        )
        if response is None:
            raise RuntimeError("Sitemap request returned None")

        root = ET.fromstring(response.content)

        # Sitemap XML uses a namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        entries: list[tuple[str, Optional[str]]] = []
        for url_el in root.findall("sm:url", ns):
            loc_el = url_el.find("sm:loc", ns)
            if loc_el is None or not loc_el.text:
                continue

            loc = loc_el.text.strip()

            # Filter to article URLs only
            if "/article/" not in loc:
                continue

            lastmod_el = url_el.find("sm:lastmod", ns)
            lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None

            entries.append((loc, lastmod))

        return entries

    def _process_sitemap_article(
        self, url: str, lastmod: Optional[str], result: ScraperResult
    ) -> Generator[dict, None, None]:
        """Fetch an article page from the sitemap and process it."""
        # Cross-phase deduplication (may have been processed via RSS)
        if url in self._session_processed_urls:
            return
        self._session_processed_urls.add(url)
        result.scraped_count += 1

        # Persistent state check
        if self._is_processed(url):
            self.logger.debug(f"Already processed (sitemap): {url}")
            result.skipped_count += 1
            return

        # Incremental mode: skip by lastmod date
        if self._from_date and lastmod:
            lastmod_date = lastmod[:10]  # YYYY-MM-DD prefix
            if lastmod_date < self._from_date:
                self.logger.debug(
                    f"Skipping old sitemap article: {lastmod_date} < {self._from_date}"
                )
                result.skipped_count += 1
                return

        # Fetch article page via FlareSolverr
        try:
            self.logger.debug(f"Fetching sitemap article: {url}")
            article_html = self.fetch_rendered_page(url)
            if not article_html:
                self.logger.warning(f"Empty response for sitemap article: {url}")
                result.failed_count += 1
                return

            # Extract JSON-LD dates
            dates = self._extract_jsonld_dates(article_html)
            pub_date = dates["date_published"]
            self._track_article_date(pub_date)

            # Extract title from HTML
            title = self._extract_title(article_html)
            if not title:
                self.logger.warning(f"No title for sitemap article: {url}")
                result.failed_count += 1
                return

            # Build tags
            tags = ["TheEnergy"]

            safe_title = sanitize_filename(title)[:100]
            filename = f"{safe_title}.md"

            metadata = DocumentMetadata(
                url=url,
                title=title,
                filename=filename,
                publication_date=pub_date,
                tags=tags,
                source_page=self.SITEMAP_URL,
                organization="The Energy",
                document_type="Article",
                extra={
                    "content_type": "article",
                    "source": "sitemap",
                    "date_published_iso": dates["date_published"],
                    "date_created": dates["date_created"],
                    "date_modified": dates["date_modified"],
                    "lastmod": lastmod,
                },
            )

            # Exclusion check
            exclusion_reason = self.should_exclude_document(metadata)
            if exclusion_reason:
                self.logger.debug(f"Excluded: {title} ({exclusion_reason})")
                result.excluded_count += 1
                result.excluded.append(
                    ExcludedDocument(
                        title=title, url=url, reason=exclusion_reason
                    ).to_dict()
                )
                return

            # Extract article content as Markdown
            content = self._extract_article_content(article_html)

            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would save: {title}")
                result.downloaded_count += 1
                yield metadata.to_dict()
            else:
                saved_path = self._save_article(metadata, content)
                if saved_path:
                    self._mark_processed(url, {"title": title})
                    result.downloaded_count += 1
                    yield metadata.to_dict()
                else:
                    result.failed_count += 1

        except Exception as e:
            self.logger.warning(f"Failed to process sitemap article {url}: {e}")
            result.failed_count += 1

    # ------------------------------------------------------------------
    # Content extraction helpers
    # ------------------------------------------------------------------

    def _extract_article_content(self, html: str) -> str:
        """Extract article body content and convert to GFM Markdown."""
        return self._markdown.convert(html)

    def _convert_html_to_markdown(self, html: str) -> str:
        """Convert HTML snippet (from RSS) to GFM Markdown."""
        full_html = f"<article>{html}</article>"
        return self._markdown.convert(full_html)

    def _extract_title(self, html: str) -> str:
        """Extract page title from HTML ``<title>`` or ``<h1>``."""
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        soup = BeautifulSoup(html, "lxml")

        # Try h1 first (more specific)
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(strip=True)
            if text:
                return text

        # Fall back to <title>
        title_el = soup.find("title")
        if title_el:
            text = title_el.get_text(strip=True)
            # Strip site name suffix (e.g. " - The Energy")
            if " - " in text:
                text = text.rsplit(" - ", 1)[0].strip()
            if text:
                return text

        return ""
