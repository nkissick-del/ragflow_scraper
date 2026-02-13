"""Tests for BaseScraper mixins."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.scrapers import common_mixins as _cm
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ScraperResult
from app.services.state_tracker import StateTracker
from app.utils.errors import ScraperError

_HAS_SELENIUM = _cm.webdriver is not None


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
                yield from ()
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
                yield from ()
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
                yield from ()
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

    @pytest.mark.skipif(not _HAS_SELENIUM, reason="selenium not installed")
    @patch("app.scrapers.common_mixins.webdriver.Remote")
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
                yield from ()
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
        call_order = []
        
        original_setup = self.scraper.setup
        original_teardown = self.scraper.teardown
        
        def tracked_setup():
            call_order.append('setup')
            original_setup()
        
        def tracked_teardown():
            call_order.append('teardown')
            original_teardown()
        
        self.scraper.setup = tracked_setup
        self.scraper.teardown = tracked_teardown
        self.scraper.setup_called = False
        self.scraper.teardown_called = False

        gen = self.scraper.run()
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        assert self.scraper.setup_called is True
        assert self.scraper.teardown_called is True
        assert call_order == ['setup', 'teardown']
        assert result is not None


# ---------------------------------------------------------------------------
# CloudflareBypassMixin tests
# ---------------------------------------------------------------------------


class TestCloudflareBypassFetchPage:
    """Test CloudflareBypassMixin.fetch_page() fallback behaviour."""

    def _make_mixin(self):
        """Build a standalone CloudflareBypassMixin with stubbed attributes."""
        mixin = _cm.CloudflareBypassMixin()
        mixin.logger = MagicMock()
        mixin.driver = None
        mixin.base_url = "http://example.com"
        mixin._flaresolverr = None
        mixin._cloudflare_session_id = None
        mixin._cloudflare_user_agent = ""
        mixin._flaresolverr_html = ""
        mixin.cloudflare_bypass_enabled = False
        return mixin

    def test_fetch_page_uses_cached_html_when_valid(self):
        """Should return cached HTML when use_cached=True and HTML is valid."""
        mixin = self._make_mixin()
        mixin._flaresolverr_html = "<html>Good page</html>"

        result = mixin.fetch_page("http://example.com/page", use_cached=True)

        assert result == "<html>Good page</html>"

    def test_fetch_page_ignores_cached_cloudflare_challenge(self):
        """Should not return cached HTML when it contains 'Just a moment'."""
        mixin = self._make_mixin()
        mixin._flaresolverr_html = "<html>Just a moment</html>"
        # No driver and no bypass → should raise
        with pytest.raises(ScraperError):
            mixin.fetch_page("http://example.com/page", use_cached=True)

    def test_fetch_page_flaresolverr_success(self):
        """Should return FlareSolverr HTML when bypass is enabled and session exists."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._cloudflare_cookies = {"cf_clearance": "abc"}

        mock_fs = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.html = "<html>Solved</html>"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        result = mixin.fetch_page("http://example.com/page")

        assert result == "<html>Solved</html>"

    def test_fetch_page_flaresolverr_fails_then_selenium_fallback(self):
        """FlareSolverr fail -> Selenium driver fallback."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._cloudflare_cookies = {"cf_clearance": "abc"}

        mock_fs = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "timeout"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        mock_driver = MagicMock()
        mixin.driver = mock_driver
        mixin.get_page_source = MagicMock(return_value="<html>Selenium page</html>")

        result = mixin.fetch_page("http://example.com/page")

        assert result == "<html>Selenium page</html>"
        mock_driver.get.assert_called_once_with("http://example.com/page")

    def test_fetch_page_flaresolverr_returns_challenge_falls_to_selenium(self):
        """FlareSolverr returns challenge HTML -> falls to Selenium."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._cloudflare_cookies = {"cf_clearance": "abc"}

        mock_fs = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.html = "<html>Just a moment</html>"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        mock_driver = MagicMock()
        mixin.driver = mock_driver
        mixin.get_page_source = MagicMock(return_value="<html>Good</html>")

        result = mixin.fetch_page("http://example.com/page")

        assert result == "<html>Good</html>"
        mixin.logger.warning.assert_called()

    def test_fetch_page_no_flaresolverr_no_driver_raises(self):
        """No FlareSolverr, no driver -> ScraperError."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = False
        mixin.driver = None

        with pytest.raises(ScraperError, match="Driver not initialized"):
            mixin.fetch_page("http://example.com/page")

    def test_fetch_page_flaresolverr_timeout_falls_to_selenium(self):
        """FlareSolverr times out (empty string) -> Selenium fallback."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._cloudflare_cookies = {"cf_clearance": "abc"}

        mock_fs = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Timeout reached"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        mock_driver = MagicMock()
        mixin.driver = mock_driver
        mixin.get_page_source = MagicMock(return_value="<html>Driver ok</html>")

        result = mixin.fetch_page("http://example.com/page")

        assert result == "<html>Driver ok</html>"


class TestCloudflareBypassInit:
    """Test CloudflareBypassMixin._init_cloudflare_bypass() edge cases."""

    def _make_mixin(self):
        mixin = _cm.CloudflareBypassMixin()
        mixin.logger = MagicMock()
        mixin.driver = None
        mixin.base_url = "http://example.com"
        mixin._flaresolverr = None
        mixin._cloudflare_session_id = None
        mixin._cloudflare_user_agent = ""
        mixin._flaresolverr_html = ""
        mixin.cloudflare_bypass_enabled = True
        mixin.settings_mgr = None
        return mixin

    def test_bypass_disabled(self):
        """Should return False immediately when bypass not enabled."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = False

        result = mixin._init_cloudflare_bypass()

        assert result is False

    @patch.object(_cm.Config, "FLARESOLVERR_URL", "")
    def test_no_flaresolverr_url_configured(self):
        """Should return False when FLARESOLVERR_URL is empty."""
        mixin = self._make_mixin()

        result = mixin._init_cloudflare_bypass()

        assert result is False
        mixin.logger.error.assert_called()

    @patch.object(_cm.Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    def test_session_creation_fails(self):
        """Should return False when session creation fails."""
        mixin = self._make_mixin()
        mock_fs = MagicMock()
        mock_fs.create_session.return_value = False
        mixin._flaresolverr = mock_fs

        result = mixin._init_cloudflare_bypass()

        assert result is False
        mixin.logger.error.assert_called()

    @patch.object(_cm.Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    def test_initial_page_fetch_fails(self):
        """Should return False when FlareSolverr cannot fetch initial page."""
        mixin = self._make_mixin()
        mock_fs = MagicMock()
        mock_fs.create_session.return_value = True
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Network error"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        result = mixin._init_cloudflare_bypass()

        assert result is False

    @patch.object(_cm.Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    def test_no_cookies_returned(self):
        """Should succeed even when FlareSolverr returns no cookies."""
        mixin = self._make_mixin()
        mock_fs = MagicMock()
        mock_fs.create_session.return_value = True
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.cookies = []
        mock_result.user_agent = "Mozilla/5.0"
        mock_result.html = "<html>Page</html>"
        mock_fs.get_page.return_value = mock_result
        mixin._flaresolverr = mock_fs

        result = mixin._init_cloudflare_bypass()

        assert result is True
        assert mixin._cloudflare_cookies == {}

    @patch.object(_cm.Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    def test_session_creation_exception(self):
        """Should return False when session creation raises."""
        mixin = self._make_mixin()
        mock_fs = MagicMock()
        mock_fs.create_session.side_effect = ConnectionError("refused")
        mixin._flaresolverr = mock_fs

        result = mixin._init_cloudflare_bypass()

        assert result is False


class TestCloudflareBypassInitAndFetchFirstPage:
    """Test init_cloudflare_and_fetch_first_page() redirect detection."""

    def _make_mixin(self):
        mixin = _cm.CloudflareBypassMixin()
        mixin.logger = MagicMock()
        mixin.driver = None
        mixin.base_url = "http://example.com"
        mixin._flaresolverr = None
        mixin._cloudflare_session_id = None
        mixin._cloudflare_user_agent = ""
        mixin._flaresolverr_html = ""
        mixin.cloudflare_bypass_enabled = False
        mixin.settings_mgr = None
        return mixin

    def test_returns_false_on_cloudflare_challenge(self):
        """Should return (False, html) when page is still a challenge."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = False
        mock_driver = MagicMock()
        mixin.driver = mock_driver
        mixin.get_page_source = MagicMock(
            return_value="<html>Just a moment</html>"
        )

        success, html = mixin.init_cloudflare_and_fetch_first_page()

        assert success is False
        assert "Just a moment" in html

    def test_bypass_success_uses_flaresolverr_html(self):
        """When bypass succeeds and HTML is valid, should use FlareSolverr HTML."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._cloudflare_cookies = {"cf_clearance": "abc"}

        # Mock _init_cloudflare_bypass to succeed
        mixin._init_cloudflare_bypass = MagicMock(return_value=True)
        mixin._flaresolverr_html = "<html>Good page</html>"

        success, html = mixin.init_cloudflare_and_fetch_first_page()

        assert success is True
        assert html == "<html>Good page</html>"

    def test_bypass_failure_falls_to_selenium(self):
        """When bypass fails, should fall back to Selenium."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True

        mixin._init_cloudflare_bypass = MagicMock(return_value=False)
        mock_driver = MagicMock()
        mixin.driver = mock_driver
        mixin.get_page_source = MagicMock(return_value="<html>Selenium page</html>")

        success, html = mixin.init_cloudflare_and_fetch_first_page()

        assert success is True
        assert html == "<html>Selenium page</html>"

    def test_no_driver_no_bypass_raises(self):
        """When bypass fails and no driver, should raise ScraperError."""
        mixin = self._make_mixin()
        mixin.cloudflare_bypass_enabled = True
        mixin._init_cloudflare_bypass = MagicMock(return_value=False)
        mixin.driver = None

        with pytest.raises(ScraperError, match="Driver not initialized"):
            mixin.init_cloudflare_and_fetch_first_page()


# ---------------------------------------------------------------------------
# WebDriverLifecycleMixin.get_page_source() tests
# ---------------------------------------------------------------------------


class TestGetPageSource:
    """Test WebDriverLifecycleMixin.get_page_source() edge cases."""

    def _make_mixin(self):
        mixin = _cm.WebDriverLifecycleMixin()
        mixin.logger = MagicMock()
        mixin.driver = None
        return mixin

    def test_get_page_source_no_driver_raises(self):
        """Should raise ScraperError when driver is None."""
        mixin = self._make_mixin()

        with pytest.raises(ScraperError, match="Driver not initialized"):
            mixin.get_page_source()

    def test_get_page_source_returns_driver_page_source(self):
        """Should return driver.page_source when driver exists."""
        mixin = self._make_mixin()
        mock_driver = MagicMock()
        mock_driver.page_source = "<html>Content</html>"
        mixin.driver = mock_driver

        result = mixin.get_page_source()

        assert result == "<html>Content</html>"

    def test_get_page_source_returns_empty_string(self):
        """Should return empty string when driver.page_source is empty."""
        mixin = self._make_mixin()
        mock_driver = MagicMock()
        mock_driver.page_source = ""
        mixin.driver = mock_driver

        result = mixin.get_page_source()

        assert result == ""

    def test_close_driver_handles_quit_exception(self):
        """Should handle exception during driver.quit() gracefully."""
        mixin = self._make_mixin()
        mock_driver = MagicMock()
        mock_driver.quit.side_effect = Exception("Session not found")
        mixin.driver = mock_driver

        mixin._close_driver()

        assert mixin.driver is None
        mixin.logger.warning.assert_called()


# ---------------------------------------------------------------------------
# MetadataIOMixin tests
# ---------------------------------------------------------------------------


class TestMetadataIOMixinEdgeCases:
    """Test MetadataIOMixin._save_metadata() and _save_article() edge cases."""

    def _make_mixin(self):
        mixin = _cm.MetadataIOMixin()
        mixin.logger = MagicMock()
        mixin.dry_run = False
        mixin.name = "test_scraper"
        return mixin

    @patch("app.scrapers.common_mixins.ensure_dir")
    def test_save_metadata_write_error(self, mock_ensure_dir, tmp_path):
        """Should propagate file write errors from _save_metadata."""
        mixin = self._make_mixin()
        # Point to a non-existent nested dir to trigger write error
        bad_dir = tmp_path / "nonexistent"
        mock_ensure_dir.return_value = bad_dir

        doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Test Doc",
            filename="test_doc.pdf",
        )

        with pytest.raises(FileNotFoundError):
            mixin._save_metadata(doc)

    @patch("app.scrapers.common_mixins.ensure_dir")
    def test_save_article_dry_run(self, mock_ensure_dir):
        """Should not write files in dry_run mode."""
        mixin = self._make_mixin()
        mixin.dry_run = True

        doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Test Doc",
            filename="test_doc.pdf",
        )

        result = mixin._save_article(doc, "# Content")

        assert result is None
        mock_ensure_dir.assert_not_called()

    @patch("app.scrapers.common_mixins.ensure_dir")
    def test_save_article_success(self, mock_ensure_dir, tmp_path):
        """Should save markdown and JSON files and return path."""
        mixin = self._make_mixin()
        output_dir = tmp_path / "downloads" / "test_scraper"
        output_dir.mkdir(parents=True)
        mock_ensure_dir.return_value = output_dir

        doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Test Doc",
            filename="test_doc.pdf",
        )

        result = mixin._save_article(doc, "# Test Content")

        assert result is not None
        assert result.endswith(".md")
        md_path = Path(result)
        assert md_path.exists()
        assert md_path.read_text(encoding="utf-8") == "# Test Content"

        json_path = md_path.with_suffix(".json")
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["title"] == "Test Doc"

    @patch("app.scrapers.common_mixins.ensure_dir")
    def test_save_article_with_html_content(self, mock_ensure_dir, tmp_path):
        """Should save HTML alongside markdown when html_content provided."""
        mixin = self._make_mixin()
        output_dir = tmp_path / "downloads" / "test_scraper"
        output_dir.mkdir(parents=True)
        mock_ensure_dir.return_value = output_dir

        doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Test Doc",
            filename="test_doc.pdf",
        )

        result = mixin._save_article(doc, "# Content", html_content="<h1>Content</h1>")

        assert result is not None
        # HTML file should exist — sanitize_filename preserves the dot
        html_path = output_dir / "test_doc.pdf.html"
        assert html_path.exists()
        assert html_path.read_text(encoding="utf-8") == "<h1>Content</h1>"

    @patch("pathlib.Path.write_bytes")
    @patch("app.scrapers.common_mixins.ensure_dir")
    def test_save_article_write_error_returns_none(self, mock_ensure_dir, mock_write_bytes, tmp_path):
        """Should return None and clean up temps on write failure."""
        mixin = self._make_mixin()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        mock_ensure_dir.return_value = output_dir

        # Mock write_bytes to raise PermissionError
        mock_write_bytes.side_effect = PermissionError("Permission denied")

        doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Test Doc",
            filename="test_doc.pdf",
        )

        result = mixin._save_article(doc, "# Content")
        assert result is None
        mixin.logger.error.assert_called()


# ---------------------------------------------------------------------------
# IncrementalStateMixin additional tests
# ---------------------------------------------------------------------------


class TestIncrementalStateMixinEdgeCases:
    """Test IncrementalStateMixin with various date formats and edge cases."""

    def _make_mixin(self):
        mixin = _cm.IncrementalStateMixin()
        mixin.name = "test_scraper"
        mixin.state_tracker = MagicMock()
        mixin.state_tracker.get_state.return_value = {}
        mixin.logger = MagicMock()
        mixin._newest_article_date = None
        return mixin

    def test_track_article_date_none_ignored(self):
        """Should not update _newest_article_date when given None."""
        mixin = self._make_mixin()
        mixin._newest_article_date = "2026-01-01"

        mixin._track_article_date(None)

        assert mixin._newest_article_date == "2026-01-01"

    def test_track_article_date_empty_string_ignored(self):
        """Should not update _newest_article_date when given empty string."""
        mixin = self._make_mixin()
        mixin._newest_article_date = "2026-01-01"

        mixin._track_article_date("")

        assert mixin._newest_article_date == "2026-01-01"

    def test_track_article_date_first_date_sets_value(self):
        """Should set _newest_article_date when starting from None."""
        mixin = self._make_mixin()

        mixin._track_article_date("2026-03-15")

        assert mixin._newest_article_date == "2026-03-15"

    def test_update_last_scrape_date_uses_explicit_date(self):
        """Should use explicit date_str when provided."""
        mixin = self._make_mixin()

        mixin._update_last_scrape_date("2026-06-15")

        call_args = mixin.state_tracker.set_value.call_args[0]
        assert call_args[1] == "2026-06-15"
        mixin.state_tracker.save.assert_called_once()

    def test_update_last_scrape_date_uses_newest_article_date(self):
        """Should fall back to _newest_article_date when no explicit date."""
        mixin = self._make_mixin()
        mixin._newest_article_date = "2026-05-01"

        mixin._update_last_scrape_date()

        call_args = mixin.state_tracker.set_value.call_args[0]
        assert call_args[1] == "2026-05-01"

    def test_update_last_scrape_date_falls_back_to_today(self):
        """Should fall back to today's date when no date_str and no _newest_article_date."""
        mixin = self._make_mixin()
        mixin._newest_article_date = None

        mixin._update_last_scrape_date()

        call_args = mixin.state_tracker.set_value.call_args[0]
        # Should be today's date in YYYY-MM-DD format
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        assert call_args[1] == today

    def test_parse_iso_date_with_timezone_offset(self):
        """Should handle ISO dates with timezone offset."""
        mixin = self._make_mixin()

        result = mixin._parse_iso_date("2026-01-07T10:30:00+05:30")

        assert result == "2026-01-07"

    def test_parse_iso_date_date_only(self):
        """Should handle date-only ISO strings."""
        mixin = self._make_mixin()

        result = mixin._parse_iso_date("2026-03-15")

        assert result == "2026-03-15"


# ---------------------------------------------------------------------------
# ExclusionRulesMixin additional tests
# ---------------------------------------------------------------------------


class TestExclusionRulesMixinEdgeCases:
    """Test ExclusionRulesMixin with keyword matching and combined exclusions."""

    def _make_mixin(self):
        mixin = _cm.ExclusionRulesMixin()
        mixin.excluded_tags = ["Gas", "Coal"]
        mixin.required_tags = ["Electricity"]
        mixin.excluded_keywords = ["Budget", "Draft"]
        mixin.logger = MagicMock()
        return mixin

    def test_should_exclude_document_keyword_case_insensitive(self):
        """Should match keywords case-insensitively in title."""
        mixin = self._make_mixin()
        doc = MagicMock()
        doc.tags = ["Electricity"]
        doc.title = "Annual BUDGET Report 2026"

        result = mixin.should_exclude_document(doc)

        assert result is not None
        assert "keyword: Budget" in result

    def test_should_exclude_document_combined_excluded_tag_overridden_by_required(self):
        """Excluded tag should be skipped when document also has required tag."""
        mixin = self._make_mixin()
        doc = MagicMock()
        doc.tags = ["Gas", "Electricity"]
        doc.title = "Energy Report"

        result = mixin.should_exclude_document(doc)

        # Has required tag AND excluded tag -- excluded tag check continues (skips)
        # but required tag is present, so no exclusion for missing required tag
        assert result is None

    def test_should_exclude_document_no_tags_no_keywords(self):
        """Document with no tags and clean title should not be excluded."""
        mixin = self._make_mixin()
        mixin.required_tags = None  # Remove required tag constraint
        doc = MagicMock()
        doc.tags = []
        doc.title = "Clean Energy Report"

        result = mixin.should_exclude_document(doc)

        assert result is None

    def test_should_exclude_document_multiple_keywords(self):
        """Should match the first matching excluded keyword."""
        mixin = self._make_mixin()
        doc = MagicMock()
        doc.tags = ["Electricity"]
        doc.title = "Draft Budget for 2026"

        result = mixin.should_exclude_document(doc)

        assert result is not None
        # Should match either Budget or Draft
        assert "keyword:" in result

    def test_should_exclude_empty_excluded_tags(self):
        """_should_exclude should return False when excluded_tags is empty."""
        mixin = self._make_mixin()
        mixin.excluded_tags = []

        result = mixin._should_exclude(["Gas", "Coal"])

        assert result is False

    def test_should_exclude_document_no_title(self):
        """Should handle document with None title gracefully."""
        mixin = self._make_mixin()
        mixin.required_tags = None
        doc = MagicMock()
        doc.tags = ["Electricity"]
        doc.title = None

        result = mixin.should_exclude_document(doc)

        # No keyword match possible, required_tags is None, tags clean
        assert result is None
