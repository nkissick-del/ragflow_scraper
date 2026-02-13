"""Unit tests for BaseScraper abstract class.

Uses a concrete test subclass to test lifecycle, cancellation, and status finalization.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import ScraperResult


class ConcreteScraper(BaseScraper):
    """Minimal concrete scraper for testing BaseScraper lifecycle."""

    name = "test_concrete"
    display_name = "Test Concrete"
    description = "Test scraper"
    base_url = "http://example.com"
    skip_webdriver = True

    def __init__(self, scrape_fn=None, **kwargs):
        super().__init__(**kwargs)
        self._scrape_fn = scrape_fn

    def scrape(self) -> ScraperResult:
        if self._scrape_fn:
            return self._scrape_fn(self)
        return ScraperResult(status="completed", scraper=self.name)


@pytest.fixture
def scraper():
    """Create a ConcreteScraper with mocked container."""
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = ConcreteScraper(max_pages=1, dry_run=True)
        yield s


# ── TestRunLifecycle ────────────────────────────────────────────────────


class TestRunLifecycle:
    """Tests for BaseScraper.run() lifecycle."""

    def test_calls_setup_scrape_teardown(self, scraper):
        """run() calls setup → scrape → teardown in order."""
        call_order = []

        original_setup = scraper.setup
        original_teardown = scraper.teardown

        def mock_setup():
            call_order.append("setup")
            original_setup()

        def mock_teardown():
            call_order.append("teardown")
            original_teardown()

        scraper.setup = mock_setup
        scraper.teardown = mock_teardown
        scraper._scrape_fn = lambda self: (
            call_order.append("scrape") or
            ScraperResult(status="completed", scraper=self.name)
        )

        scraper.run()

        assert call_order == ["setup", "scrape", "teardown"]

    def test_teardown_called_on_error(self, scraper):
        """teardown() is called even when scrape() raises."""
        teardown_called = []

        original_teardown = scraper.teardown

        def mock_teardown():
            teardown_called.append(True)
            original_teardown()

        def raising_scrape(self):
            raise RuntimeError("boom")

        scraper.teardown = mock_teardown
        scraper._scrape_fn = raising_scrape

        result = scraper.run()

        assert teardown_called == [True]
        # Error is captured in errors list
        assert any("boom" in e for e in result.errors)

    def test_duration_and_completed_at_set(self, scraper):
        """run() sets duration_seconds and completed_at on result."""
        result = scraper.run()

        assert result.duration_seconds >= 0
        assert result.completed_at is not None


# ── TestCancellation ────────────────────────────────────────────────────


class TestCancellation:
    """Tests for cancellation support."""

    def test_cancel_sets_flag(self, scraper):
        """cancel() sets _cancelled flag."""
        scraper.cancel()
        assert scraper._cancelled is True

    def test_check_cancelled_returns_true(self, scraper):
        """check_cancelled() returns True after cancel()."""
        scraper.cancel()
        assert scraper.check_cancelled() is True

    def test_run_sets_cancelled_status(self, scraper):
        """run() sets 'cancelled' status when cancelled during scrape."""
        def cancelling_scrape(self):
            self.cancel()
            return ScraperResult(status="completed", scraper=self.name)

        scraper._scrape_fn = cancelling_scrape

        result = scraper.run()

        assert result.status == "cancelled"


# ── TestFinalizeResult ──────────────────────────────────────────────────


class TestFinalizeResult:
    """Tests for _finalize_result() status determination."""

    def test_all_errors_failed(self, scraper):
        """All errors with no downloads → 'failed'."""
        result = ScraperResult(
            status="running", scraper="test",
            errors=["err1", "err2"], downloaded_count=0
        )
        scraper._finalize_result(result)
        assert result.status == "failed"

    def test_mixed_partial(self, scraper):
        """Errors with some downloads → 'partial'."""
        result = ScraperResult(
            status="running", scraper="test",
            errors=["err1"], downloaded_count=3
        )
        scraper._finalize_result(result)
        assert result.status == "partial"

    def test_no_errors_completed(self, scraper):
        """No errors → 'completed'."""
        result = ScraperResult(
            status="running", scraper="test",
            errors=[], downloaded_count=5
        )
        scraper._finalize_result(result)
        assert result.status == "completed"
