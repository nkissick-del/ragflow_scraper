"""Unit tests for TheEnergyScraper RSS + sitemap scrape flow."""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from app.scrapers.theenergy_scraper import TheEnergyScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _consume_scrape(scraper):
    """Consume scraper.scrape() generator and return (docs, result).

    scrape() is a generator that yields document dicts and returns a
    ScraperResult via ``return result`` (accessible as StopIteration.value).
    """
    gen = scraper.scrape()
    docs = []
    try:
        while True:
            docs.append(next(gen))
    except StopIteration as e:
        result = e.value
    return docs, result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = TheEnergyScraper(max_pages=None, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        s.state_tracker.get_state.return_value = {}
        s._session = Mock()
        # Prevent real HTTP/delay calls
        s._polite_delay = lambda: None  # type: ignore[assignment]
        yield s


def _make_rss_entry(
    title: str = "Test Article",
    link: str = "https://theenergy.co/article/test",
    summary: str = "<p>Full HTML content here.</p>",
    published_parsed: object = None,
    tags: list[dict[str, str]] | None = None,
) -> dict:
    """Build a feedparser-like entry dict."""
    entry: dict = {
        "title": title,
        "link": link,
        "summary": summary,
    }
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    if tags is not None:
        entry["tags"] = tags
    return entry


SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://theenergy.co/article/energy-policy-update</loc>
    <lastmod>2025-12-20</lastmod>
  </url>
  <url>
    <loc>https://theenergy.co/article/grid-battery</loc>
    <lastmod>2025-12-15</lastmod>
  </url>
  <url>
    <loc>https://theenergy.co/about</loc>
    <lastmod>2025-01-01</lastmod>
  </url>
</urlset>
"""

ARTICLE_HTML = """\
<html><head><title>Energy Policy Update - The Energy</title></head>
<body>
<h1>Energy Policy Update</h1>
<script type="application/ld+json">
{
  "@type": "Article",
  "datePublished": "2025-12-20T07:30:00+11:00"
}
</script>
<article><p>Article body content.</p></article>
</body></html>
"""


# ---------------------------------------------------------------------------
# RSS Phase Tests
# ---------------------------------------------------------------------------


class TestScrapeRSS:
    """Phase 1: RSS feed parsing and processing."""

    def test_rss_entries_processed(self, scraper):
        """RSS entries are scraped and counted."""
        entries = [
            _make_rss_entry(title="Article 1", link="https://theenergy.co/article/1"),
            _make_rss_entry(title="Article 2", link="https://theenergy.co/article/2"),
        ]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._session.get = Mock(return_value=mock_resp)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 2
        assert result.scraped_count >= 2

    def test_rss_deduplicates_urls(self, scraper):
        """Same URL appearing twice in RSS is only counted once."""
        url = "https://theenergy.co/article/dup"
        entries = [
            _make_rss_entry(title="Dup 1", link=url),
            _make_rss_entry(title="Dup 2", link=url),
        ]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 1

    def test_rss_skips_already_processed(self, scraper):
        """Articles already in persistent state are skipped."""
        scraper.state_tracker.is_processed.return_value = True
        entries = [_make_rss_entry()]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.skipped_count == 1
        assert result.downloaded_count == 0

    def test_rss_extracts_pub_date(self, scraper):
        """Publication date is extracted from feedparser struct_time."""
        ts = time.strptime("2025-12-24", "%Y-%m-%d")
        entries = [_make_rss_entry(published_parsed=ts)]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 1
        doc = docs[0]
        assert doc["publication_date"] == "2025-12-24"

    def test_rss_extracts_tags_from_entry(self, scraper):
        """RSS entry categories are added as tags."""
        entries = [_make_rss_entry(tags=[{"term": "Policy"}, {"term": "Solar"}])]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 1
        doc = docs[0]
        assert "TheEnergy" in doc["tags"]
        assert "Policy" in doc["tags"]
        assert "Solar" in doc["tags"]

    def test_rss_error_does_not_crash(self, scraper):
        """RSS fetch failure is recorded but scraper continues to sitemap."""
        scraper._request_with_retry = Mock(return_value=None)
        # Sitemap also fails so we get a clean test
        docs, result = _consume_scrape(scraper)

        assert any("RSS" in e for e in result.errors)

    def test_rss_no_content_entry_counted_as_failed(self, scraper):
        """Entry with empty summary counts as failed."""
        entries = [_make_rss_entry(summary="")]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.failed_count == 1


# ---------------------------------------------------------------------------
# Sitemap Phase Tests
# ---------------------------------------------------------------------------


class TestSitemapParsing:
    """_parse_sitemap extracts article URLs from sitemap XML."""

    def test_extracts_article_urls(self, scraper):
        mock_resp = Mock()
        mock_resp.content = SITEMAP_XML.encode()
        scraper._request_with_retry = Mock(return_value=mock_resp)

        entries = scraper._parse_sitemap()

        # Should include 2 /article/ URLs, exclude /about
        assert len(entries) == 2
        urls = [e[0] for e in entries]
        assert "https://theenergy.co/article/energy-policy-update" in urls
        assert "https://theenergy.co/article/grid-battery" in urls

    def test_extracts_lastmod(self, scraper):
        mock_resp = Mock()
        mock_resp.content = SITEMAP_XML.encode()
        scraper._request_with_retry = Mock(return_value=mock_resp)

        entries = scraper._parse_sitemap()

        # Check lastmod values
        by_url = {url: lastmod for url, lastmod in entries}
        assert by_url["https://theenergy.co/article/energy-policy-update"] == "2025-12-20"

    def test_filters_non_article_urls(self, scraper):
        mock_resp = Mock()
        mock_resp.content = SITEMAP_XML.encode()
        scraper._request_with_retry = Mock(return_value=mock_resp)

        entries = scraper._parse_sitemap()

        urls = [e[0] for e in entries]
        assert "https://theenergy.co/about" not in urls


class TestScrapeSitemap:
    """Phase 2: Sitemap backfill processing."""

    def test_sitemap_articles_processed(self, scraper):
        """Sitemap articles are fetched and saved."""
        mock_rss_resp = Mock()
        mock_rss_resp.content = b"<rss></rss>"

        mock_sitemap_resp = Mock()
        mock_sitemap_resp.content = SITEMAP_XML.encode()

        call_count = 0

        def mock_request(session, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "rss" in url:
                return mock_rss_resp
            if "sitemap" in url:
                return mock_sitemap_resp
            return None

        scraper._request_with_retry = mock_request
        scraper.fetch_rendered_page = Mock(return_value=ARTICLE_HTML)

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=[], bozo=False)

            docs, result = _consume_scrape(scraper)

        # 2 article URLs in sitemap (dry_run mode)
        assert result.downloaded_count == 2

    def test_sitemap_skips_rss_urls(self, scraper):
        """URLs already processed via RSS are skipped in sitemap phase."""
        rss_url = "https://theenergy.co/article/energy-policy-update"
        rss_entries = [_make_rss_entry(title="Energy Policy Update", link=rss_url)]

        mock_rss_resp = Mock()
        mock_rss_resp.content = b"<rss></rss>"

        mock_sitemap_resp = Mock()
        mock_sitemap_resp.content = SITEMAP_XML.encode()

        def mock_request(session, method, url, **kwargs):
            if "rss" in url:
                return mock_rss_resp
            if "sitemap" in url:
                return mock_sitemap_resp
            return None

        scraper._request_with_retry = mock_request
        scraper.fetch_rendered_page = Mock(return_value=ARTICLE_HTML)

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=rss_entries, bozo=False)

            docs, result = _consume_scrape(scraper)

        # 1 from RSS + 1 from sitemap (the other sitemap URL is deduped)
        assert result.downloaded_count == 2

    def test_sitemap_skips_persistent_duplicates(self, scraper):
        """Articles in persistent state are skipped."""
        scraper.state_tracker.is_processed.return_value = True

        mock_rss_resp = Mock()
        mock_rss_resp.content = b"<rss></rss>"
        mock_sitemap_resp = Mock()
        mock_sitemap_resp.content = SITEMAP_XML.encode()

        def mock_request(session, method, url, **kwargs):
            if "rss" in url:
                return mock_rss_resp
            if "sitemap" in url:
                return mock_sitemap_resp
            return None

        scraper._request_with_retry = mock_request

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=[], bozo=False)

            docs, result = _consume_scrape(scraper)

        assert result.skipped_count == 2
        assert result.downloaded_count == 0

    def test_sitemap_error_does_not_crash(self, scraper):
        """Sitemap fetch failure is recorded as error."""
        mock_rss_resp = Mock()
        mock_rss_resp.content = b"<rss></rss>"

        def mock_request(session, method, url, **kwargs):
            if "rss" in url:
                return mock_rss_resp
            return None  # sitemap fails

        scraper._request_with_retry = mock_request

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=[], bozo=False)

            docs, result = _consume_scrape(scraper)

        assert any("Sitemap" in e for e in result.errors)


# ---------------------------------------------------------------------------
# max_pages / Article Limit Tests
# ---------------------------------------------------------------------------


class TestMaxPages:
    """max_pages limits total articles processed."""

    def test_max_pages_limits_rss(self, scraper):
        """max_pages=1 with articles_per_page=10 stops at 10 articles."""
        scraper.max_pages = 1
        entries = [
            _make_rss_entry(title=f"Article {i}", link=f"https://theenergy.co/article/{i}")
            for i in range(15)
        ]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 10

    def test_max_pages_none_no_limit(self, scraper):
        """No max_pages means all articles are processed."""
        scraper.max_pages = None
        entries = [
            _make_rss_entry(title=f"Article {i}", link=f"https://theenergy.co/article/{i}")
            for i in range(15)
        ]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 15


# ---------------------------------------------------------------------------
# Dry Run Mode
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry run mode processes but doesn't persist."""

    def test_dry_run_counts_downloads(self, scraper):
        entries = [_make_rss_entry()]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 1
        scraper.state_tracker.mark_processed.assert_not_called()


# ---------------------------------------------------------------------------
# Incremental Mode
# ---------------------------------------------------------------------------


class TestIncrementalMode:
    """Date-based incremental filtering."""

    def test_rss_skips_old_articles(self, scraper):
        """Articles older than last scrape date are skipped."""
        scraper.state_tracker.get_state.return_value = {
            "_theenergy_last_scrape_date": "2025-12-20"
        }
        old_ts = time.strptime("2025-12-15", "%Y-%m-%d")
        entries = [
            _make_rss_entry(
                title="Old Article",
                link="https://theenergy.co/article/old",
                published_parsed=old_ts,
            )
        ]
        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.skipped_count == 1
        assert result.downloaded_count == 0

    def test_sitemap_skips_old_lastmod(self, scraper):
        """Sitemap articles with old lastmod are skipped."""
        scraper.state_tracker.get_state.return_value = {
            "_theenergy_last_scrape_date": "2025-12-18"
        }
        mock_rss_resp = Mock()
        mock_rss_resp.content = b"<rss></rss>"

        # Only one article has lastmod >= from_date
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://theenergy.co/article/new</loc>
    <lastmod>2025-12-20</lastmod>
  </url>
  <url>
    <loc>https://theenergy.co/article/old</loc>
    <lastmod>2025-12-10</lastmod>
  </url>
</urlset>
"""
        mock_sitemap_resp = Mock()
        mock_sitemap_resp.content = sitemap_xml.encode()

        def mock_request(session, method, url, **kwargs):
            if "rss" in url:
                return mock_rss_resp
            if "sitemap" in url:
                return mock_sitemap_resp
            return None

        scraper._request_with_retry = mock_request
        scraper.fetch_rendered_page = Mock(return_value=ARTICLE_HTML)

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=[], bozo=False)

            docs, result = _consume_scrape(scraper)

        assert result.downloaded_count == 1  # only the new one
        assert result.skipped_count == 1  # old one skipped


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    """Scraper respects cancellation during both phases."""

    def test_cancellation_during_rss(self, scraper):
        """Cancellation stops processing mid-RSS."""
        scraper._cancelled = True
        scraper.check_cancelled = Mock(return_value=True)

        mock_resp = Mock()
        mock_resp.content = b"<rss></rss>"
        entries = [_make_rss_entry()]

        with patch("app.scrapers.theenergy_scraper.feedparser") as mock_fp:
            mock_fp.parse.return_value = Mock(entries=entries, bozo=False)
            scraper._request_with_retry = Mock(return_value=mock_resp)

            docs, result = _consume_scrape(scraper)

        assert result.status == "cancelled"
