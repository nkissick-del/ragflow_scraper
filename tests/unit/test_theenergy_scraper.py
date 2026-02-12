"""Unit tests for TheEnergyScraper helpers (JSON-LD, title extraction, etc.)."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.theenergy_scraper import TheEnergyScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = TheEnergyScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

JSONLD_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@type": "Article",
  "datePublished": "2025-12-24T07:30:00+11:00",
  "dateCreated": "2025-12-24T12:04:37+11:00",
  "dateModified": "2025-12-24T12:39:08+11:00"
}
</script>
</body></html>
"""

JSONLD_GRAPH_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@graph": [
    {
      "@type": "WebPage",
      "name": "TheEnergy"
    },
    {
      "@type": "Article",
      "datePublished": "2024-01-15T09:00:00+00:00"
    }
  ]
}
</script>
</body></html>
"""

NO_JSONLD_HTML = """<html><body><div>No JSON-LD here.</div></body></html>"""

TITLE_H1_HTML = """
<html><body><h1>Energy Policy Update</h1><p>Content here.</p></body></html>
"""

TITLE_TAG_HTML = """
<html><head><title>Grid Battery Project - The Energy</title></head><body></body></html>
"""

NO_TITLE_HTML = """<html><body><p>No title element.</p></body></html>"""


# -- Tests -------------------------------------------------------------------


class TestExtractJsonLDDatesTE:
    """_extract_jsonld_dates extracts dates from JSON-LD."""

    def test_single_object(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_HTML)
        assert dates["date_published"] == "2025-12-24"
        assert dates["date_created"] == "2025-12-24"
        assert dates["date_modified"] == "2025-12-24"

    def test_graph_array(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_GRAPH_HTML)
        assert dates["date_published"] == "2024-01-15"

    def test_no_jsonld(self, scraper):
        dates = scraper._extract_jsonld_dates(NO_JSONLD_HTML)
        assert dates["date_published"] is None
        assert dates["date_created"] is None
        assert dates["date_modified"] is None


class TestParseIsoDateTE:
    """_parse_iso_date handles various ISO 8601 formats."""

    def test_with_timezone_offset(self, scraper):
        assert scraper._parse_iso_date("2025-12-24T07:30:00+11:00") == "2025-12-24"

    def test_with_utc_z(self, scraper):
        assert scraper._parse_iso_date("2024-06-15T10:00:00Z") == "2024-06-15"

    def test_date_only(self, scraper):
        assert scraper._parse_iso_date("2024-01-01") == "2024-01-01"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_iso_date("") is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_iso_date("not-a-date") is None


class TestExtractTitle:
    """_extract_title extracts title from H1 or <title> tag."""

    def test_extracts_h1(self, scraper):
        title = scraper._extract_title(TITLE_H1_HTML)
        assert title == "Energy Policy Update"

    def test_extracts_title_tag_strips_suffix(self, scraper):
        title = scraper._extract_title(TITLE_TAG_HTML)
        assert title == "Grid Battery Project"

    def test_no_title_returns_empty(self, scraper):
        title = scraper._extract_title(NO_TITLE_HTML)
        assert title == ""


class TestParseFeedparserDateTE:
    """_parse_feedparser_date converts struct_time to YYYY-MM-DD."""

    def test_valid_struct(self, scraper):
        import time
        ts = time.strptime("2025-06-15", "%Y-%m-%d")
        assert scraper._parse_feedparser_date(ts) == "2025-06-15"

    def test_none_returns_none(self, scraper):
        assert scraper._parse_feedparser_date(None) is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_feedparser_date("not-a-struct") is None


class TestExtractRSSContent:
    """_extract_rss_content extracts HTML from feedparser entry."""

    def test_content_list(self, scraper):
        entry = {"content": [{"type": "text/html", "value": "<p>Article body.</p>"}]}
        assert scraper._extract_rss_content(entry) == "<p>Article body.</p>"

    def test_summary_fallback(self, scraper):
        entry = {"summary": "<p>Summary content.</p>"}
        assert scraper._extract_rss_content(entry) == "<p>Summary content.</p>"

    def test_empty_entry(self, scraper):
        assert scraper._extract_rss_content({}) == ""


class TestReachedLimit:
    """_reached_limit checks article limit based on max_pages."""

    def test_no_max_pages(self, scraper):
        scraper.max_pages = None
        result = Mock()
        result.downloaded_count = 100
        result.skipped_count = 50
        assert scraper._reached_limit(result) is False

    def test_below_limit(self, scraper):
        scraper.max_pages = 2
        result = Mock()
        result.downloaded_count = 10
        result.skipped_count = 5
        assert scraper._reached_limit(result) is False

    def test_at_limit(self, scraper):
        scraper.max_pages = 2  # limit = 20
        result = Mock()
        result.downloaded_count = 15
        result.skipped_count = 5
        assert scraper._reached_limit(result) is True


class TestScraperConfig:
    """Basic configuration checks."""

    def test_skip_webdriver(self, scraper):
        assert scraper.skip_webdriver is True

    def test_rss_url(self, scraper):
        assert scraper.RSS_URL == "https://theenergy.co/rss"

    def test_sitemap_url(self, scraper):
        assert scraper.SITEMAP_URL == "https://theenergy.co/sitemap-articles-1.xml"

    def test_session_processed_urls_initialized(self, scraper):
        assert isinstance(scraper._session_processed_urls, set)
