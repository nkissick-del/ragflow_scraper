"""Tests for BaseScraper mixins."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from datetime import datetime

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ExcludedDocument, ScraperResult
from app.services.state_tracker import StateTracker


class TestIncrementalStateMixin:
    """Test incremental state tracking mixin."""

    def setup_method(self):
        """Create a test scraper with state tracking."""
        # Create a minimal concrete scraper for testing
        class TestScraper(BaseScraper):
            name = "test_scraper"
            base_url = "http://example.com"
            skip_webdriver = True

            def scrape(self):
                return ScraperResult(
                    status="completed",
                    scraper=self.name,
                    documents=[],
                    errors=[],
                )

        self.scraper = TestScraper(max_pages=1)
        # Mock the state tracker after initialization
        self.state_tracker = Mock(spec=StateTracker)
        self.state_tracker.get_state.return_value = {}
        self.state_tracker.set_value = Mock()
        self.state_tracker.save = Mock()
        self.scraper.state_tracker = self.state_tracker

    def test_get_last_scrape_date_returns_none_when_not_set(self):
        """Should return None when no last scrape date is stored."""
        self.state_tracker.get_state.return_value = {}

        date = self.scraper._get_last_scrape_date()

        assert date is None

    def test_get_last_scrape_date_returns_stored_value(self):
        """Should return stored last scrape date."""
        self.state_tracker.get_state.return_value = {
            "_test_scraper_last_scrape_date": "2026-01-07"
        }

        date = self.scraper._get_last_scrape_date()

        assert date == "2026-01-07"

    def test_update_last_scrape_date(self):
        """Should update last scrape date in state."""
        self.scraper._update_last_scrape_date("2026-01-08")

        self.state_tracker.set_value.assert_called_once()
        self.state_tracker.save.assert_called_once()

    def test_track_article_date_updates_newest(self):
        """Should track the newest article date."""
        self.scraper._newest_article_date = "2026-01-06"

        self.scraper._track_article_date("2026-01-08")

        assert self.scraper._newest_article_date == "2026-01-08"

    def test_track_article_date_ignores_older(self):
        """Should not update if newer date exists."""
        self.scraper._newest_article_date = "2026-01-08"

        self.scraper._track_article_date("2026-01-06")

        assert self.scraper._newest_article_date == "2026-01-08"

    def test_parse_iso_date_converts_correctly(self):
        """Should parse ISO8601 dates."""
        result = self.scraper._parse_iso_date("2026-01-07T10:30:00Z")

        assert result == "2026-01-07"

    def test_parse_iso_date_handles_invalid(self):
        """Should return None for invalid dates."""
        result = self.scraper._parse_iso_date("invalid-date")

        assert result is None


class TestExclusionRulesMixin:
    """Test exclusion rules mixin."""

    def setup_method(self):
        """Create a test scraper with exclusion rules."""
        class TestScraper(BaseScraper):
            name = "test_scraper"
            base_url = "http://example.com"
            skip_webdriver = True
            excluded_tags = ["Gas"]
            excluded_keywords = ["Budget"]
            required_tags = ["Electricity"]

            def scrape(self):
                return ScraperResult(
                    status="completed",
                    scraper=self.name,
                    documents=[],
                    errors=[],
                )

        self.scraper = TestScraper(max_pages=1)
        self.state_tracker = Mock(spec=StateTracker)
        self.state_tracker.get_state.return_value = {}
        self.scraper.state_tracker = self.state_tracker

    def test_should_exclude_matches_excluded_tag(self):
        """Should identify excluded tags."""
        result = self.scraper._should_exclude(["Gas", "Energy"])

        assert result is True

    def test_should_exclude_case_insensitive(self):
        """Should match tags case-insensitively."""
        result = self.scraper._should_exclude(["gas", "energy"])

        assert result is True

    def test_should_exclude_ignores_missing_tags(self):
        """Should not exclude if no excluded tags present."""
        result = self.scraper._should_exclude(["Electricity"])

        assert result is False

    def test_should_exclude_document_with_excluded_tag(self):
        """Should exclude documents with excluded tags."""
        doc = Mock()
        doc.tags = ["Gas"]
        doc.title = "Energy Report"

        result = self.scraper.should_exclude_document(doc)

        assert result is not None
        assert "tag: Gas" in result

    def test_should_exclude_document_with_excluded_keyword(self):
        """Should exclude documents with excluded keywords."""
        doc = Mock()
        doc.tags = ["Electricity"]
        doc.title = "Annual Budget 2026"

        result = self.scraper.should_exclude_document(doc)

        assert result is not None
        assert "keyword: Budget" in result

    def test_should_exclude_document_missing_required_tag(self):
        """Should exclude documents without required tags."""
        doc = Mock()
        doc.tags = ["Gas"]
        doc.title = "Energy Report"

        result = self.scraper.should_exclude_document(doc)

        assert result is not None

    def test_should_exclude_document_includes_required_tag(self):
        """Should include documents with required tags."""
        doc = Mock()
        doc.tags = ["Electricity"]
        doc.title = "Energy Report"

        result = self.scraper.should_exclude_document(doc)

        assert result is None


class TestWebDriverLifecycleMixin:
    """Test WebDriver lifecycle mixin."""

    def setup_method(self):
        """Create a test scraper with WebDriver."""
        class TestScraper(BaseScraper):
            name = "test_scraper"
            base_url = "http://example.com"

            def scrape(self):
                return ScraperResult(
                    status="completed",
                    scraper=self.name,
                    documents=[],
                    errors=[],
                )

        self.scraper = TestScraper(max_pages=1)
        self.state_tracker = Mock(spec=StateTracker)
        self.state_tracker.get_state.return_value = {}
        self.scraper.state_tracker = self.state_tracker

    @patch("app.scrapers.mixins.webdriver.Remote")
    def test_init_driver_creates_driver(self, mock_remote):
        """Should create a Selenium WebDriver."""
        mock_driver = Mock()
        mock_remote.return_value = mock_driver

        driver = self.scraper._init_driver()

        assert driver == mock_driver
        mock_remote.assert_called_once()

    def test_close_driver_quits_if_exists(self):
        """Should quit driver if it exists."""
        mock_driver = Mock()
        mock_driver.quit = Mock()
        self.scraper.driver = mock_driver

        self.scraper._close_driver()

        mock_driver.quit.assert_called_once()
        assert self.scraper.driver is None

    def test_close_driver_no_op_if_none(self):
        """Should handle None driver gracefully."""
        self.scraper.driver = None

        self.scraper._close_driver()  # Should not raise

        assert self.scraper.driver is None


class TestBaseScrapeTemplate:
    """Test BaseScraper setup/scrape/teardown template."""

    def setup_method(self):
        """Create a test scraper."""
        class TestScraper(BaseScraper):
            name = "test_scraper"
            base_url = "http://example.com"
            skip_webdriver = True

            def setup(self):
                self.setup_called = True

            def scrape(self):
                return ScraperResult(
                    status="completed",
                    scraper=self.name,
                    documents=[],
                    errors=[],
                )

            def teardown(self):
                self.teardown_called = True

        self.scraper = TestScraper(max_pages=1)
        self.state_tracker = Mock(spec=StateTracker)
        self.state_tracker.get_state.return_value = {}
        self.scraper.state_tracker = self.state_tracker

    def test_run_calls_template_methods_in_order(self):
        """Should call setup, scrape, teardown in sequence."""
        self.scraper.setup_called = False
        self.scraper.teardown_called = False

        result = self.scraper.run()

        assert self.scraper.setup_called is True
        assert self.scraper.teardown_called is True
        assert result is not None
