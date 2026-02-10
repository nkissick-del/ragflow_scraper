"""Unit tests for GuardianScraper (API-based, skip_webdriver=True)."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.guardian_scraper import GuardianScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        with patch("app.scrapers.guardian_scraper.Config") as mock_config:
            mock_config.GUARDIAN_API_KEY = "test-api-key"
            mock_config.REQUEST_TIMEOUT = 30
            s = GuardianScraper(max_pages=1, dry_run=True)
            s.state_tracker = Mock()
            s.state_tracker.is_processed.return_value = False
            yield s


# -- Tests -------------------------------------------------------------------


class TestBuildSearchParams:
    """_build_search_params constructs correct API parameters."""

    def test_basic_params(self, scraper):
        params = scraper._build_search_params("environment/renewableenergy", page=1)
        assert params["tag"] == "environment/renewableenergy"
        assert params["page"] == 1
        assert params["page-size"] == scraper.API_PAGE_SIZE
        assert params["order-by"] == "newest"
        assert "body" in params["show-fields"]
        assert "headline" in params["show-fields"]

    def test_page_parameter(self, scraper):
        params = scraper._build_search_params("environment/coal", page=5)
        assert params["page"] == 5

    def test_from_date_filter(self, scraper):
        params = scraper._build_search_params(
            "environment/solarpower", page=1, from_date="2025-01-01"
        )
        assert params["from-date"] == "2025-01-01"

    def test_no_from_date(self, scraper):
        params = scraper._build_search_params("environment/gas", page=1)
        assert "from-date" not in params

    def test_show_tags_included(self, scraper):
        params = scraper._build_search_params("environment/windpower", page=1)
        assert params["show-tags"] == "keyword"


class TestProcessApiResult:
    """_process_api_result handles dedup, metadata extraction, and body conversion."""

    def _make_api_item(
        self,
        url="https://www.theguardian.com/article/test",
        title="Test Article",
        body="<p>Article body</p>",
        pub_date="2025-06-15T10:00:00Z",
        byline="Jane Smith",
    ):
        return {
            "webUrl": url,
            "webTitle": title,
            "webPublicationDate": pub_date,
            "id": "article/test",
            "sectionName": "Environment",
            "fields": {
                "headline": title,
                "body": body,
                "byline": byline,
                "trailText": "Test trail text",
                "thumbnail": None,
            },
            "tags": [{"webTitle": "Renewable energy"}],
        }

    def test_processes_new_article(self, scraper):
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item()

        scraper._process_api_result(item, "environment/renewableenergy", result)

        assert result.scraped_count == 1
        assert result.downloaded_count == 1  # dry_run counts as downloaded

    def test_deduplicates_across_tags(self, scraper):
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item()

        scraper._process_api_result(item, "tag-1", result)
        scraper._process_api_result(item, "tag-2", result)

        # Second call should be silently skipped
        assert result.scraped_count == 1
        assert result.downloaded_count == 1

    def test_skips_no_body(self, scraper):
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item(body="")

        scraper._process_api_result(item, "tag-1", result)

        assert result.failed_count == 1

    def test_extracts_author(self, scraper):
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item(byline="John Doe")

        scraper._process_api_result(item, "tag-1", result)

        assert result.downloaded_count == 1
        doc = result.documents[0]
        assert doc["extra"]["author"] == "John Doe"


class TestParseIsoDateGuardian:
    """_parse_iso_date (from IncrementalStateMixin) handles ISO 8601."""

    def test_full_iso(self, scraper):
        assert scraper._parse_iso_date("2025-06-15T10:00:00Z") == "2025-06-15"

    def test_with_offset(self, scraper):
        assert scraper._parse_iso_date("2025-06-15T10:00:00+11:00") == "2025-06-15"

    def test_date_only(self, scraper):
        assert scraper._parse_iso_date("2025-06-15") == "2025-06-15"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_iso_date("") is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_iso_date("not-a-date") is None


class TestCrossTagDedup:
    """Cross-tag deduplication uses _session_processed_urls."""

    def test_fresh_scraper_has_empty_set(self, scraper):
        assert len(scraper._session_processed_urls) == 0

    def test_url_added_after_processing(self, scraper):
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = {
            "webUrl": "https://www.theguardian.com/unique",
            "webTitle": "Unique Article",
            "webPublicationDate": "2025-01-01T00:00:00Z",
            "id": "article/unique",
            "sectionName": "Test",
            "fields": {
                "headline": "Unique Article",
                "body": "<p>Body</p>",
                "byline": "",
                "trailText": "",
            },
            "tags": [],
        }
        scraper._process_api_result(item, "tag-a", result)
        assert "https://www.theguardian.com/unique" in scraper._session_processed_urls
