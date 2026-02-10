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
