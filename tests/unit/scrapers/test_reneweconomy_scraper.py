"""Unit tests for RenewEconomyScraper (WordPress REST API-based)."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock, patch

from app.scrapers.reneweconomy_scraper import RenewEconomyScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = RenewEconomyScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Helper utilities --------------------------------------------------------


def _make_post(
    url="https://reneweconomy.com.au/big-battery-milestone/",
    title="Big Battery Milestone Reached",
    body="<p>Australia sets a new record for battery storage.</p>",
    date="2025-12-23T01:59:09",
    modified="2025-12-23T02:30:00",
    categories=None,
    slug="big-battery-milestone",
    wp_id=12345,
):
    """Create a WordPress post dict matching API response shape."""
    return {
        "id": wp_id,
        "link": url,
        "slug": slug,
        "date": date,
        "modified": modified,
        "title": {"rendered": title},
        "content": {"rendered": body},
        "excerpt": {"rendered": f"<p>{title}</p>"},
        "categories": categories or [10, 20],
        "tags": [],
    }


def _exhaust_scrape(scraper):
    """Exhaust scrape() generator and return (docs, ScraperResult)."""
    gen = scraper.scrape()
    docs = []
    try:
        while True:
            docs.append(next(gen))
    except StopIteration as e:
        result = e.value
    return docs, result


# -- Tests -------------------------------------------------------------------


class TestBuildPostsParams:
    """_build_posts_params constructs correct WordPress API parameters."""

    def test_basic_params(self, scraper):
        params = scraper._build_posts_params(page=1)
        assert params["per_page"] == scraper.API_PAGE_SIZE
        assert params["page"] == 1
        assert params["orderby"] == "date"
        assert params["order"] == "desc"
        assert "after" not in params

    def test_page_parameter(self, scraper):
        params = scraper._build_posts_params(page=5)
        assert params["page"] == 5

    def test_from_date_filter(self, scraper):
        params = scraper._build_posts_params(page=1, from_date="2025-01-01")
        assert params["after"] == "2025-01-01T00:00:00"

    def test_no_from_date(self, scraper):
        params = scraper._build_posts_params(page=1)
        assert "after" not in params

    def test_with_all_params(self, scraper):
        params = scraper._build_posts_params(page=3, from_date="2025-06-01")
        assert params["page"] == 3
        assert params["per_page"] == scraper.API_PAGE_SIZE
        assert params["orderby"] == "date"
        assert params["order"] == "desc"
        assert params["after"] == "2025-06-01T00:00:00"


class TestFetchCategories:
    """_fetch_categories resolves WP category IDs to names."""

    def test_basic_categories(self, scraper):
        api_data = [
            {"id": 10, "name": "Solar"},
            {"id": 20, "name": "Storage"},
            {"id": 30, "name": "Wind"},
        ]
        headers = {"X-WP-TotalPages": "1"}
        scraper._api_request = MagicMock(return_value=(api_data, headers))

        categories = scraper._fetch_categories()

        assert categories == {10: "Solar", 20: "Storage", 30: "Wind"}
        scraper._api_request.assert_called_once()

    def test_empty_response(self, scraper):
        scraper._api_request = MagicMock(return_value=([], {"X-WP-TotalPages": "1"}))

        categories = scraper._fetch_categories()

        assert categories == {}

    def test_multi_page_categories(self, scraper):
        page1 = [{"id": 1, "name": "Cat A"}]
        page2 = [{"id": 2, "name": "Cat B"}]
        scraper._api_request = MagicMock(
            side_effect=[
                (page1, {"X-WP-TotalPages": "2"}),
                (page2, {"X-WP-TotalPages": "2"}),
            ]
        )

        categories = scraper._fetch_categories()

        assert categories == {1: "Cat A", 2: "Cat B"}
        assert scraper._api_request.call_count == 2

    def test_api_error_returns_partial(self, scraper):
        from app.utils.errors import NetworkError

        scraper._api_request = MagicMock(
            side_effect=NetworkError("connection failed", scraper="reneweconomy")
        )

        categories = scraper._fetch_categories()

        assert categories == {}

    def test_skips_categories_without_name(self, scraper):
        api_data = [
            {"id": 10, "name": "Solar"},
            {"id": 20, "name": ""},
            {"id": 30},
        ]
        scraper._api_request = MagicMock(
            return_value=(api_data, {"X-WP-TotalPages": "1"})
        )

        categories = scraper._fetch_categories()

        assert categories == {10: "Solar"}


class TestProcessPost:
    """_process_post handles dedup, metadata extraction, and body conversion."""

    def test_processes_new_post(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar", 20: "Storage"}
        post = _make_post()

        docs = list(scraper._process_post(post, result))

        assert result.scraped_count == 1
        assert result.downloaded_count == 1  # dry_run counts as downloaded
        assert len(docs) == 1

    def test_deduplicates_across_pages(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar", 20: "Storage"}
        post = _make_post()

        docs1 = list(scraper._process_post(post, result))
        docs2 = list(scraper._process_post(post, result))

        # Second call should be silently skipped
        assert result.scraped_count == 1
        assert result.downloaded_count == 1
        assert len(docs1) == 1
        assert len(docs2) == 0

    def test_skips_already_processed(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar", 20: "Storage"}
        scraper.state_tracker.is_processed.return_value = True
        post = _make_post()

        docs = list(scraper._process_post(post, result))

        assert result.scraped_count == 1
        assert result.skipped_count == 1
        assert result.downloaded_count == 0
        assert len(docs) == 0

    def test_skips_no_body(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar", 20: "Storage"}
        post = _make_post(body="")

        docs = list(scraper._process_post(post, result))

        assert result.failed_count == 1
        assert len(docs) == 0

    def test_skips_no_title(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post(title="")

        docs = list(scraper._process_post(post, result))

        # No title -> skipped, not counted as scraped (logged warning)
        assert result.downloaded_count == 0
        assert len(docs) == 0

    def test_category_resolution(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar", 20: "Storage", 99: "Unknown"}
        post = _make_post(categories=[10, 20])

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert "RenewEconomy" in doc["tags"]
        assert "Solar" in doc["tags"]
        assert "Storage" in doc["tags"]

    def test_unknown_category_id_ignored(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar"}
        post = _make_post(categories=[10, 999])

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert "Solar" in doc["tags"]
        assert len([t for t in doc["tags"] if t not in ("RenewEconomy", "Solar")]) == 0

    def test_publication_date_extracted(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post(date="2025-12-23T01:59:09")

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert doc["publication_date"] == "2025-12-23"

    def test_missing_date(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post(date="")

        docs = list(scraper._process_post(post, result))

        assert result.downloaded_count == 1
        doc = docs[0]
        assert doc.get("publication_date") is None

    def test_extra_metadata(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {10: "Solar"}
        post = _make_post(
            slug="test-slug",
            wp_id=42,
            categories=[10],
            modified="2025-12-24T10:00:00",
        )

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert doc["extra"]["slug"] == "test-slug"
        assert doc["extra"]["wp_id"] == 42
        assert doc["extra"]["categories"] == ["Solar"]
        assert doc["extra"]["date_modified"] == "2025-12-24T10:00:00"
        assert doc["extra"]["content_type"] == "article"

    def test_filename_is_md(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post()

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert doc["filename"].endswith(".md")

    def test_organization_is_reneweconomy(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post()

        docs = list(scraper._process_post(post, result))

        doc = docs[0]
        assert doc["organization"] == "RenewEconomy"
        assert doc["document_type"] == "Article"


class TestConvertContentToMarkdown:
    """_convert_content_to_markdown converts WP body HTML to Markdown."""

    def test_standard_html(self, scraper):
        result = scraper._convert_content_to_markdown("<p>Hello world</p>")
        assert isinstance(result, str)

    def test_empty_body(self, scraper):
        result = scraper._convert_content_to_markdown("")
        assert isinstance(result, str)

    def test_html_with_links_and_lists(self, scraper):
        html = """
        <p>Check out <a href="https://example.com">this link</a>.</p>
        <ul>
          <li>Item one</li>
          <li>Item two</li>
        </ul>
        """
        result = scraper._convert_content_to_markdown(html)
        assert isinstance(result, str)


class TestApiRequest:
    """_api_request handles HTTP responses and errors."""

    def test_successful_request(self, scraper):
        scraper._session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": 1, "title": {"rendered": "Test"}}]
        mock_response.headers = {"X-WP-Total": "1", "X-WP-TotalPages": "1"}
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        data, headers = scraper._api_request("/posts", {"per_page": 10})

        assert len(data) == 1
        assert headers["X-WP-Total"] == "1"

    def test_none_response_raises_network_error(self, scraper):
        from app.utils.errors import NetworkError

        scraper._session = MagicMock()
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._api_request("/posts", {"per_page": 10})

    def test_json_parse_error(self, scraper):
        from app.utils.errors import ParsingError

        scraper._session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("No JSON")
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        with pytest.raises(ParsingError):
            scraper._api_request("/posts", {"per_page": 10})

    def test_no_session_raises(self, scraper):
        scraper._session = None
        with pytest.raises(RuntimeError, match="HTTP session not initialized"):
            scraper._api_request("/posts", {"per_page": 10})

    def test_returns_headers(self, scraper):
        scraper._session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.headers = {"X-WP-Total": "42", "X-WP-TotalPages": "5"}
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        _, headers = scraper._api_request("/posts")

        assert headers["X-WP-Total"] == "42"
        assert headers["X-WP-TotalPages"] == "5"


class TestScrapeFlow:
    """Tests for scrape() orchestration."""

    def test_completes_with_no_posts(self, scraper):
        scraper._from_date = None
        scraper._newest_article_date = None
        scraper._categories = {}

        scraper._fetch_categories = MagicMock(return_value={})
        empty_response = ([], {"X-WP-TotalPages": "1", "X-WP-Total": "0"})
        scraper._api_request = MagicMock(return_value=empty_response)

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "completed"
        assert result.scraped_count == 0

    def test_pagination_stops_at_max_pages(self, scraper):
        scraper.max_pages = 1
        scraper._from_date = None
        scraper._newest_article_date = None

        scraper._fetch_categories = MagicMock(return_value={})
        page_response = (
            [],
            {"X-WP-TotalPages": "5", "X-WP-Total": "500"},
        )
        scraper._api_request = MagicMock(return_value=page_response)

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "completed"
        # Only 1 page should be fetched due to max_pages=1
        assert scraper._api_request.call_count == 1

    def test_processes_posts_from_api(self, scraper):
        scraper._from_date = None
        scraper._newest_article_date = None

        scraper._fetch_categories = MagicMock(return_value={10: "Solar"})
        posts = [_make_post(categories=[10])]
        page_response = (posts, {"X-WP-TotalPages": "1", "X-WP-Total": "1"})
        scraper._api_request = MagicMock(return_value=page_response)

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "completed"
        assert result.downloaded_count == 1
        assert len(docs) == 1

    def test_incremental_mode_passes_from_date(self, scraper):
        scraper.state_tracker.get_state.return_value = {
            "_reneweconomy_last_scrape_date": "2025-12-01"
        }
        scraper._newest_article_date = None

        scraper._fetch_categories = MagicMock(return_value={})
        empty_response = ([], {"X-WP-TotalPages": "1", "X-WP-Total": "0"})
        scraper._api_request = MagicMock(return_value=empty_response)

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "completed"
        # Verify from_date was loaded
        assert scraper._from_date == "2025-12-01"
        # Verify after param was passed
        call_args = scraper._api_request.call_args
        params = call_args[1].get("params") or call_args[0][1]
        assert params.get("after") == "2025-12-01T00:00:00"

    def test_cancellation_stops_scrape(self, scraper):
        scraper._from_date = None
        scraper._newest_article_date = None

        scraper._fetch_categories = MagicMock(return_value={})
        scraper.check_cancelled = MagicMock(return_value=True)
        scraper._api_request = MagicMock()

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "cancelled"
        scraper._api_request.assert_not_called()

    def test_api_error_sets_failed(self, scraper):
        scraper._from_date = None
        scraper._newest_article_date = None

        scraper._fetch_categories = MagicMock(
            side_effect=Exception("API unreachable")
        )

        docs, result = _exhaust_scrape(scraper)

        assert result.status == "failed"
        assert len(result.errors) > 0


class TestParseIsoDate:
    """_parse_iso_date handles ISO 8601 date strings."""

    def test_full_datetime(self, scraper):
        assert scraper._parse_iso_date("2025-12-23T01:59:09+00:00") == "2025-12-23"

    def test_with_z(self, scraper):
        assert scraper._parse_iso_date("2024-06-15T10:00:00Z") == "2024-06-15"

    def test_date_only(self, scraper):
        assert scraper._parse_iso_date("2024-01-01") == "2024-01-01"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_iso_date("") is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_iso_date("not-a-date") is None

    def test_wp_format_no_tz(self, scraper):
        """WordPress API returns dates without timezone suffix."""
        assert scraper._parse_iso_date("2025-12-23T01:59:09") == "2025-12-23"


class TestCrossPageDedup:
    """Cross-page deduplication uses _session_processed_urls."""

    def test_fresh_scraper_has_empty_set(self, scraper):
        assert len(scraper._session_processed_urls) == 0

    def test_url_added_after_processing(self, scraper):
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")
        scraper._categories = {}
        post = _make_post()

        list(scraper._process_post(post, result))

        assert "https://reneweconomy.com.au/big-battery-milestone/" in scraper._session_processed_urls
