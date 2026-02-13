"""Unit tests for TheConversationScraper (feed-based, skip_webdriver=True)."""

from __future__ import annotations

import time

import pytest
from unittest.mock import Mock, patch

from app.scrapers.the_conversation_scraper import TheConversationScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = TheConversationScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Tests -------------------------------------------------------------------


class TestParseFeedparserDate:
    """_parse_feedparser_date converts struct_time to YYYY-MM-DD."""

    def test_valid_struct_time(self, scraper):
        ts = time.strptime("2025-06-15", "%Y-%m-%d")
        assert scraper._parse_feedparser_date(ts) == "2025-06-15"

    def test_another_date(self, scraper):
        ts = time.strptime("2024-01-01", "%Y-%m-%d")
        assert scraper._parse_feedparser_date(ts) == "2024-01-01"

    def test_none_returns_none(self, scraper):
        assert scraper._parse_feedparser_date(None) is None

    def test_invalid_struct(self, scraper):
        # Non-struct_time that triggers TypeError
        assert scraper._parse_feedparser_date("not-a-struct") is None


class TestExtractArticleId:
    """_extract_article_id parses numeric ID from feed ID string."""

    def test_standard_id(self, scraper):
        feed_id = "theconversation.com,2011:article/270866"
        assert scraper._extract_article_id(feed_id) == "270866"

    def test_another_id(self, scraper):
        feed_id = "theconversation.com,2011:article/123456"
        assert scraper._extract_article_id(feed_id) == "123456"

    def test_no_slash(self, scraper):
        assert scraper._extract_article_id("noslash") == ""

    def test_empty_string(self, scraper):
        assert scraper._extract_article_id("") == ""


class TestExtractContentHTML:
    """_extract_content_html gets HTML from feedparser entry content list."""

    def test_html_content(self, scraper):
        entry = {
            "content": [
                {"type": "text/html", "value": "<p>Full article body here.</p>"}
            ]
        }
        html = scraper._extract_content_html(entry)
        assert html == "<p>Full article body here.</p>"

    def test_fallback_to_any_content(self, scraper):
        entry = {
            "content": [
                {"type": "text/plain", "value": "Plaintext content"}
            ]
        }
        html = scraper._extract_content_html(entry)
        assert html == "Plaintext content"

    def test_fallback_to_summary(self, scraper):
        entry = {"summary": "Summary fallback text"}
        html = scraper._extract_content_html(entry)
        assert html == "Summary fallback text"

    def test_no_content_no_summary(self, scraper):
        entry = {}
        html = scraper._extract_content_html(entry)
        assert html == ""


class TestBuildFeedURL:
    """_build_feed_url constructs correct feed URLs."""

    def test_page_1(self, scraper):
        url = scraper._build_feed_url(1)
        assert url == "https://theconversation.com/topics/energy-662/articles.atom"
        assert "?page=" not in url

    def test_page_2(self, scraper):
        url = scraper._build_feed_url(2)
        assert url == "https://theconversation.com/topics/energy-662/articles.atom?page=2"

    def test_page_10(self, scraper):
        url = scraper._build_feed_url(10)
        assert url.endswith("?page=10")


class TestSkipWebdriver:
    """TheConversationScraper uses skip_webdriver=True."""

    def test_skip_webdriver_flag(self, scraper):
        assert scraper.skip_webdriver is True

    def test_session_processed_urls_initialized(self, scraper):
        assert isinstance(scraper._session_processed_urls, set)
        assert len(scraper._session_processed_urls) == 0


# -- New Test Classes -------------------------------------------------------


class TestExtractContentHtmlExtended:
    """Extended tests for _extract_content_html."""

    def test_with_html_content_field(self, scraper):
        """text/html content is preferred."""
        entry = {
            "content": [
                {"type": "text/html", "value": "<p>Full HTML body.</p>"}
            ]
        }
        html = scraper._extract_content_html(entry)
        assert html == "<p>Full HTML body.</p>"

    def test_fallback_to_summary(self, scraper):
        """When no content list, falls back to summary."""
        entry = {"summary": "Summary fallback text"}
        html = scraper._extract_content_html(entry)
        assert html == "Summary fallback text"

    def test_no_content_or_summary(self, scraper):
        """When both content and summary are missing, returns empty string."""
        entry = {}
        html = scraper._extract_content_html(entry)
        assert html == ""

    def test_content_with_empty_value(self, scraper):
        """Content item with empty value falls through to summary."""
        entry = {
            "content": [{"type": "text/html", "value": ""}],
            "summary": "Backup summary",
        }
        html = scraper._extract_content_html(entry)
        # text/html entry with empty value returns "" (matched on type first)
        assert html == ""

    def test_multiple_content_items_prefers_html(self, scraper):
        """When multiple content items exist, text/html is preferred."""
        entry = {
            "content": [
                {"type": "text/plain", "value": "Plain text version"},
                {"type": "text/html", "value": "<p>HTML version</p>"},
            ]
        }
        html = scraper._extract_content_html(entry)
        # Iterates through content list; text/plain has value so returns it first
        assert html == "Plain text version"


class TestParseFeedparserDateExtended:
    """Extended tests for _parse_feedparser_date."""

    def test_valid_time_struct(self, scraper):
        ts = time.strptime("2024-03-15", "%Y-%m-%d")
        assert scraper._parse_feedparser_date(ts) == "2024-03-15"

    def test_none_time_struct(self, scraper):
        assert scraper._parse_feedparser_date(None) is None

    def test_invalid_fields_in_struct(self, scraper):
        """Non-struct_time triggers TypeError, returns None."""
        assert scraper._parse_feedparser_date(42) is None

    def test_empty_dict_returns_none(self, scraper):
        """Dict instead of struct_time triggers TypeError."""
        assert scraper._parse_feedparser_date({}) is None

    def test_string_returns_none(self, scraper):
        """String instead of struct_time triggers TypeError."""
        assert scraper._parse_feedparser_date("2024-01-01") is None


class TestExtractArticleIdExtended:
    """Extended tests for _extract_article_id."""

    def test_standard_feed_id_with_slash(self, scraper):
        feed_id = "theconversation.com,2011:article/270866"
        assert scraper._extract_article_id(feed_id) == "270866"

    def test_feed_id_without_slash(self, scraper):
        assert scraper._extract_article_id("noslash") == ""

    def test_empty_id(self, scraper):
        assert scraper._extract_article_id("") == ""

    def test_multiple_slashes(self, scraper):
        """Multiple slashes returns the last segment."""
        feed_id = "theconversation.com,2011:section/article/99999"
        assert scraper._extract_article_id(feed_id) == "99999"

    def test_trailing_slash(self, scraper):
        """Trailing slash results in empty last segment."""
        feed_id = "theconversation.com,2011:article/"
        assert scraper._extract_article_id(feed_id) == ""


class TestFetchFeedPage:
    """Tests for _fetch_feed_page."""

    def test_successful_fetch(self, scraper):
        """Successful feed fetch returns entries."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Test Entry</title>
            <link href="https://theconversation.com/test-123"/>
          </entry>
        </feed>
        """
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        entries = scraper._fetch_feed_page("https://theconversation.com/topics/energy-662/articles.atom")
        assert len(entries) == 1
        assert entries[0].get("title") == "Test Entry"

    def test_empty_feed(self, scraper):
        """Empty feed returns empty list."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>
        """
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        entries = scraper._fetch_feed_page("https://theconversation.com/topics/energy-662/articles.atom")
        assert entries == []

    def test_network_error(self, scraper):
        """None response raises NetworkError."""
        from unittest.mock import MagicMock
        from app.utils.errors import NetworkError

        mock_session = MagicMock()
        scraper._session = mock_session
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._fetch_feed_page("https://theconversation.com/bad-url")

    def test_no_session_raises(self, scraper):
        """Calling with no session raises RuntimeError."""
        scraper._session = None
        with pytest.raises(RuntimeError, match="HTTP session not initialized"):
            scraper._fetch_feed_page("https://theconversation.com/test")


# -- New Test Classes for Additional Coverage --------------------------------


class TestExtractContentHtmlNew:
    """Additional tests for _extract_content_html code paths."""

    def test_with_content_value_field(self, scraper):
        """content[0].value with text/html type is returned."""
        entry = {
            "content": [
                {"type": "text/html", "value": "<p>Article body.</p>"}
            ]
        }
        html = scraper._extract_content_html(entry)
        assert html == "<p>Article body.</p>"

    def test_fallback_to_summary_when_no_content(self, scraper):
        """Falls back to summary field when content list is missing."""
        entry = {"summary": "Summary fallback"}
        html = scraper._extract_content_html(entry)
        assert html == "Summary fallback"

    def test_no_content_or_summary_returns_empty(self, scraper):
        """Entry with neither content nor summary returns empty string."""
        entry = {}
        html = scraper._extract_content_html(entry)
        assert html == ""


class TestParseFeedparserDateNew:
    """Additional tests for _parse_feedparser_date edge cases."""

    def test_valid_struct_time(self, scraper):
        """Standard struct_time produces YYYY-MM-DD."""
        ts = time.strptime("2025-11-20", "%Y-%m-%d")
        assert scraper._parse_feedparser_date(ts) == "2025-11-20"

    def test_none_returns_none(self, scraper):
        """None input returns None."""
        assert scraper._parse_feedparser_date(None) is None

    def test_incomplete_struct_returns_none(self, scraper):
        """Non-struct_time input triggers TypeError, returns None."""
        assert scraper._parse_feedparser_date([2024, 1, 1]) is None


class TestExtractArticleIdNew:
    """Additional tests for _extract_article_id edge cases."""

    def test_feed_id_with_slash(self, scraper):
        """Standard feed ID with slash extracts the last segment."""
        result = scraper._extract_article_id("theconversation.com,2011:article/123456")
        assert result == "123456"

    def test_no_slash_returns_empty(self, scraper):
        """Feed ID without slash returns empty string."""
        result = scraper._extract_article_id("no-slash-here")
        assert result == ""

    def test_empty_string_returns_empty(self, scraper):
        """Empty feed ID returns empty string."""
        result = scraper._extract_article_id("")
        assert result == ""


class TestFetchFeedPageNew:
    """Additional tests for _fetch_feed_page."""

    def test_successful_parse(self, scraper):
        """Successfully parses a valid Atom feed."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Energy Article</title>
            <link href="https://theconversation.com/energy-article-12345"/>
          </entry>
          <entry>
            <title>Solar Article</title>
            <link href="https://theconversation.com/solar-article-67890"/>
          </entry>
        </feed>
        """
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        entries = scraper._fetch_feed_page("https://theconversation.com/topics/energy-662/articles.atom")
        assert len(entries) == 2

    def test_empty_entries(self, scraper):
        """Feed with no entries returns empty list."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>
        """
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        entries = scraper._fetch_feed_page("https://theconversation.com/topics/energy-662/articles.atom")
        assert entries == []

    def test_request_error_raises_network_error(self, scraper):
        """None response raises NetworkError."""
        from unittest.mock import MagicMock
        from app.utils.errors import NetworkError

        mock_session = MagicMock()
        scraper._session = mock_session
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._fetch_feed_page("https://theconversation.com/bad-url")


class TestIncrementalFiltering:
    """Tests for incremental scraping date filtering in _process_feed_entry."""

    def test_article_newer_than_last_scrape_included(self, scraper):
        """Article published after last scrape date is processed."""
        from unittest.mock import MagicMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="the-conversation")
        scraper._from_date = "2025-01-01"
        scraper._newest_article_date = None
        scraper._session_processed_urls = set()

        # Mock entry with a recent date
        entry = {
            "link": "https://theconversation.com/new-article-123",
            "title": "New Energy Article",
            "published_parsed": time.strptime("2025-06-15", "%Y-%m-%d"),
            "updated_parsed": time.strptime("2025-06-15", "%Y-%m-%d"),
            "content": [{"type": "text/html", "value": "<p>Content</p>"}],
            "id": "theconversation.com,2011:article/123",
        }

        # Mock methods to avoid actual file I/O
        scraper._is_processed = MagicMock(return_value=False)
        scraper.should_exclude_document = MagicMock(return_value=None)
        scraper._save_article = MagicMock(return_value="/tmp/fake/path.md")
        scraper._mark_processed = MagicMock()

        scraper._process_feed_entry(entry, result)
        # Article should have been counted
        assert result.scraped_count == 1
        assert result.downloaded_count == 1

    def test_older_article_skipped(self, scraper):
        """Article published before last scrape date is skipped."""
        from unittest.mock import MagicMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="the-conversation")
        scraper._from_date = "2025-06-01"
        scraper._newest_article_date = None
        scraper._session_processed_urls = set()

        entry = {
            "link": "https://theconversation.com/old-article-456",
            "title": "Old Energy Article",
            "published_parsed": time.strptime("2025-01-15", "%Y-%m-%d"),
            "updated_parsed": time.strptime("2025-01-15", "%Y-%m-%d"),
            "content": [{"type": "text/html", "value": "<p>Old</p>"}],
            "id": "theconversation.com,2011:article/456",
        }

        scraper._is_processed = MagicMock(return_value=False)

        scraper._process_feed_entry(entry, result)
        assert result.scraped_count == 1
        assert result.skipped_count == 1
        assert result.downloaded_count == 0

    def test_no_last_scrape_date_includes_all(self, scraper):
        """When from_date is None, no date filtering occurs."""
        from unittest.mock import MagicMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="the-conversation")
        scraper._from_date = None
        scraper._newest_article_date = None
        scraper._session_processed_urls = set()

        entry = {
            "link": "https://theconversation.com/any-article-789",
            "title": "Any Energy Article",
            "published_parsed": time.strptime("2020-01-01", "%Y-%m-%d"),
            "updated_parsed": time.strptime("2020-01-01", "%Y-%m-%d"),
            "content": [{"type": "text/html", "value": "<p>Any date</p>"}],
            "id": "theconversation.com,2011:article/789",
        }

        scraper._is_processed = MagicMock(return_value=False)
        scraper.should_exclude_document = MagicMock(return_value=None)
        scraper._save_article = MagicMock(return_value="/tmp/fake/path.md")
        scraper._mark_processed = MagicMock()

        scraper._process_feed_entry(entry, result)
        assert result.scraped_count == 1
        assert result.downloaded_count == 1
