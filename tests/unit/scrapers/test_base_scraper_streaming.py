"""Tests for BaseScraper streaming/generator behavior."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch, MagicMock

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import ScraperResult


class DummyScraper(BaseScraper):
    """Concrete scraper for testing the generator pattern."""

    name = "dummy"
    display_name = "Dummy Scraper"
    description = "Test scraper"
    base_url = "http://example.com"
    skip_webdriver = True

    def __init__(self, docs_to_yield=None, error=None, **kwargs):
        self._docs_to_yield = docs_to_yield or []
        self._error = error
        with patch("app.container.get_container") as mock_gc:
            mock_container = MagicMock()
            mock_container.state_tracker.return_value = MagicMock()
            mock_gc.return_value = mock_container
            super().__init__(**kwargs)

    def scrape(self) -> Generator[dict, None, ScraperResult]:
        result = ScraperResult(status="in_progress", scraper=self.name)
        if self._error:
            raise self._error
        for doc in self._docs_to_yield:
            result.downloaded_count += 1
            yield doc
        result.status = "completed"
        return result


class TestScraperIsGenerator:
    def test_run_returns_generator(self):
        """run() should return a generator."""
        scraper = DummyScraper()
        gen = scraper.run()
        assert isinstance(gen, Generator)

    def test_scrape_returns_generator(self):
        """scrape() should return a generator."""
        scraper = DummyScraper()
        gen = scraper.scrape()
        assert isinstance(gen, Generator)


class TestRunGenerator:
    def test_yields_documents(self):
        """run() generator yields doc dicts from scrape()."""
        docs = [{"title": "Doc 1"}, {"title": "Doc 2"}]
        scraper = DummyScraper(docs_to_yield=docs)

        gen = scraper.run()
        yielded = []
        try:
            while True:
                yielded.append(next(gen))
        except StopIteration as e:
            result = e.value

        assert yielded == docs
        assert result.downloaded_count == 2

    def test_returns_scraper_result(self):
        """run() generator returns ScraperResult via StopIteration.value."""
        scraper = DummyScraper(docs_to_yield=[{"title": "Doc"}])

        gen = scraper.run()
        # Exhaust the generator
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        assert isinstance(result, ScraperResult)
        assert result.status == "completed"
        assert result.downloaded_count == 1

    def test_empty_scraper(self):
        """run() with no docs yields nothing and returns completed."""
        scraper = DummyScraper()

        gen = scraper.run()
        yielded = []
        try:
            while True:
                yielded.append(next(gen))
        except StopIteration as e:
            result = e.value

        assert yielded == []
        assert result.status == "completed"

    def test_error_in_scrape_returns_failed_result(self):
        """run() catches errors and includes error message in result."""
        scraper = DummyScraper(error=RuntimeError("test error"))

        gen = scraper.run()
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        # The error is captured in the result's errors list
        assert any("test error" in err for err in result.errors)

    def test_setup_and_teardown_called(self):
        """run() calls setup() and teardown()."""
        scraper = DummyScraper()
        scraper.setup = MagicMock()
        scraper.teardown = MagicMock()

        gen = scraper.run()
        try:
            while True:
                next(gen)
        except StopIteration:
            pass

        scraper.setup.assert_called_once()
        scraper.teardown.assert_called_once()

    def test_teardown_called_on_error(self):
        """teardown() is called even when scrape() raises."""
        scraper = DummyScraper(error=RuntimeError("boom"))
        scraper.teardown = MagicMock()

        gen = scraper.run()
        try:
            while True:
                next(gen)
        except StopIteration:
            pass

        scraper.teardown.assert_called_once()

    def test_cancelled_status(self):
        """Cancelled scraper returns cancelled status."""
        scraper = DummyScraper(docs_to_yield=[{"title": "Doc"}])
        scraper._cancelled = True

        gen = scraper.run()
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        assert result.status == "cancelled"


class TestMarkProcessedSavesImmediately:
    def test_mark_processed_calls_save(self):
        """_mark_processed should call state_tracker.save() immediately."""
        scraper = DummyScraper()
        scraper._mark_processed("http://example.com/doc.pdf", {"title": "test"})
        scraper.state_tracker.mark_processed.assert_called_once()
        scraper.state_tracker.save.assert_called_once()
