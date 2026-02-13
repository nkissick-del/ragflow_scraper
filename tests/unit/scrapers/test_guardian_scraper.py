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


# -- New Test Classes -------------------------------------------------------


class TestBuildSearchParamsExtended:
    """Extended tests for _build_search_params."""

    def test_with_all_params(self, scraper):
        """All parameters are set correctly."""
        params = scraper._build_search_params(
            "environment/renewableenergy", page=3, from_date="2025-06-01"
        )
        assert params["tag"] == "environment/renewableenergy"
        assert params["page"] == 3
        assert params["page-size"] == scraper.API_PAGE_SIZE
        assert params["order-by"] == "newest"
        assert params["from-date"] == "2025-06-01"
        assert "body" in params["show-fields"]
        assert "headline" in params["show-fields"]
        assert params["show-tags"] == "keyword"

    def test_with_from_date(self, scraper):
        """from-date is included when provided."""
        params = scraper._build_search_params(
            "environment/coal", page=1, from_date="2024-01-01"
        )
        assert params["from-date"] == "2024-01-01"

    def test_without_from_date(self, scraper):
        """from-date key is not present when not provided."""
        params = scraper._build_search_params("environment/gas", page=1)
        assert "from-date" not in params


class TestProcessApiResultExtended:
    """Extended tests for _process_api_result."""

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

    def test_complete_result(self, scraper):
        """Complete API result is processed successfully."""
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item()

        scraper._process_api_result(item, "environment/renewableenergy", result)

        assert result.scraped_count == 1
        assert result.downloaded_count == 1
        assert len(result.documents) == 1
        doc = result.documents[0]
        assert doc["title"] == "Test Article"

    def test_missing_title_no_headline(self, scraper):
        """Missing headline and webTitle skips the article."""
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item(title="")
        item["fields"]["headline"] = ""
        item["webTitle"] = ""

        scraper._process_api_result(item, "tag-1", result)

        assert result.downloaded_count == 0
        assert result.scraped_count == 1

    def test_missing_body(self, scraper):
        """Empty body increments failed_count."""
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item(body="")

        scraper._process_api_result(item, "tag-1", result)

        assert result.failed_count == 1

    def test_missing_publication_date(self, scraper):
        """Article without webPublicationDate still processes."""
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item(pub_date="")

        scraper._process_api_result(item, "tag-1", result)

        assert result.downloaded_count == 1
        doc = result.documents[0]
        assert doc.get("publication_date") is None

    def test_tags_extracted(self, scraper):
        """API tags are added to document tags."""
        from app.scrapers.models import ScraperResult
        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_api_item()

        scraper._process_api_result(item, "tag-1", result)

        doc = result.documents[0]
        assert "The Guardian Australia" in doc["tags"]
        assert "Renewable energy" in doc["tags"]


class TestConvertBodyToMarkdown:
    """Tests for _convert_body_to_markdown."""

    def test_standard_html(self, scraper):
        """Standard HTML body converts to Markdown string."""
        result = scraper._convert_body_to_markdown("<p>Hello world</p>")
        assert isinstance(result, str)

    def test_empty_body(self, scraper):
        """Empty body HTML returns a string (possibly empty)."""
        result = scraper._convert_body_to_markdown("")
        assert isinstance(result, str)

    def test_html_with_links_and_lists(self, scraper):
        """HTML with links and lists converts without error."""
        html = """
        <p>Check out <a href="https://example.com">this link</a>.</p>
        <ul>
          <li>Item one</li>
          <li>Item two</li>
        </ul>
        """
        result = scraper._convert_body_to_markdown(html)
        assert isinstance(result, str)


class TestApiRequest:
    """Tests for _api_request."""

    def test_successful_request(self, scraper):
        """Successful API request returns parsed JSON."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": {"status": "ok", "results": []}
        }
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        result = scraper._api_request(params={"tag": "test"})
        assert result["response"]["status"] == "ok"

    def test_http_error_response(self, scraper):
        """None response raises NetworkError."""
        from unittest.mock import MagicMock
        from app.utils.errors import NetworkError

        mock_session = MagicMock()
        scraper._session = mock_session
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._api_request(params={"tag": "test"})

    def test_json_parse_error(self, scraper):
        """Invalid JSON raises ParsingError."""
        from unittest.mock import MagicMock
        from app.utils.errors import ParsingError

        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("No JSON")
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        with pytest.raises(ParsingError):
            scraper._api_request(params={"tag": "test"})

    def test_missing_api_key_still_sends_request(self, scraper):
        """Even with empty API key, request is made (server will reject)."""
        from unittest.mock import MagicMock

        scraper._api_key = ""
        mock_session = MagicMock()
        scraper._session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": {"status": "error"}}
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        result = scraper._api_request(params={"tag": "test"})
        assert result["response"]["status"] == "error"

    def test_no_session_raises(self, scraper):
        """Calling with no session raises RuntimeError."""
        scraper._session = None
        with pytest.raises(RuntimeError, match="HTTP session not initialized"):
            scraper._api_request(params={"tag": "test"})


# -- Appended Test Classes --------------------------------------------------


class TestBuildSearchParamsNew:
    """New tests for _build_search_params edge cases."""

    def test_with_all_params_including_from_date(self, scraper):
        """All params including from-date are correctly set."""
        params = scraper._build_search_params(
            "australia-news/energy-australia",
            page=2,
            from_date="2025-03-15",
        )
        assert params["tag"] == "australia-news/energy-australia"
        assert params["page"] == 2
        assert params["from-date"] == "2025-03-15"
        assert params["order-by"] == "newest"
        assert params["show-tags"] == "keyword"

    def test_without_from_date(self, scraper):
        """No from-date means key is absent."""
        params = scraper._build_search_params("environment/coal", page=1)
        assert "from-date" not in params
        assert params["tag"] == "environment/coal"

    def test_with_custom_page_size(self, scraper):
        """page-size matches scraper's API_PAGE_SIZE attribute."""
        scraper.API_PAGE_SIZE = 100
        params = scraper._build_search_params("environment/solarpower", page=1)
        assert params["page-size"] == 100


class TestProcessApiResultNew:
    """New tests for _process_api_result edge cases."""

    def _make_item(self, **overrides):
        item = {
            "webUrl": "https://www.theguardian.com/article/new-test",
            "webTitle": "New Test Article",
            "webPublicationDate": "2025-08-01T12:00:00Z",
            "id": "article/new-test",
            "sectionName": "Environment",
            "fields": {
                "headline": "New Test Article",
                "body": "<p>Some body content</p>",
                "byline": "Alice Reporter",
                "trailText": "Trail text here",
                "thumbnail": None,
            },
            "tags": [
                {"webTitle": "Solar power"},
                {"webTitle": "Australia news"},
            ],
        }
        for k, v in overrides.items():
            if k in item:
                item[k] = v
            elif k in item.get("fields", {}):
                item["fields"][k] = v
        return item

    def test_complete_item_with_body_tags_byline(self, scraper):
        """Complete item with body, tags, and byline is processed."""
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_item()
        scraper._process_api_result(item, "environment/solarpower", result)

        assert result.downloaded_count == 1
        doc = result.documents[0]
        assert doc["title"] == "New Test Article"
        assert doc["extra"]["author"] == "Alice Reporter"
        assert "Solar power" in doc["tags"]
        assert "Australia news" in doc["tags"]
        assert "The Guardian Australia" in doc["tags"]

    def test_missing_web_title_defaults(self, scraper):
        """When webTitle is empty, headline from fields is used."""
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_item()
        item["webTitle"] = ""
        # headline is still set
        scraper._process_api_result(item, "tag", result)
        assert result.downloaded_count == 1
        assert result.documents[0]["title"] == "New Test Article"

    def test_missing_web_publication_date(self, scraper):
        """Missing webPublicationDate still processes article."""
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_item()
        item["webPublicationDate"] = ""
        scraper._process_api_result(item, "tag", result)
        assert result.downloaded_count == 1
        assert result.documents[0].get("publication_date") is None

    def test_missing_fields_body_returns_empty_markdown(self, scraper):
        """Empty body increments failed_count."""
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_item()
        item["fields"]["body"] = ""
        scraper._process_api_result(item, "tag", result)
        assert result.failed_count == 1

    def test_item_with_pillar_name(self, scraper):
        """Item with pillarName in sectionName populates extra.section."""
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="guardian")
        item = self._make_item()
        item["sectionName"] = "News"
        scraper._process_api_result(item, "tag", result)
        assert result.downloaded_count == 1
        assert result.documents[0]["extra"]["section"] == "News"


class TestConvertBodyToMarkdownNew:
    """New tests for _convert_body_to_markdown."""

    def test_standard_html_paragraphs(self, scraper):
        """Multiple paragraphs produce a markdown string."""
        html = (
            "<p>Australia's energy transition is accelerating as renewable "
            "generation capacity continues to grow across the National "
            "Electricity Market. New solar and wind installations are being "
            "deployed at record rates, with battery storage providing "
            "firming capacity for intermittent generation sources.</p>"
            "<p>The Clean Energy Regulator reported that large-scale "
            "renewable energy generation reached new highs, with solar "
            "farms and wind projects contributing significantly to the "
            "overall energy mix in the country.</p>"
        )
        md = scraper._convert_body_to_markdown(html)
        assert isinstance(md, str)

    def test_empty_body(self, scraper):
        """Empty string input returns a string."""
        md = scraper._convert_body_to_markdown("")
        assert isinstance(md, str)

    def test_html_with_links_preserved(self, scraper):
        """HTML containing links converts without error."""
        html = '<p>See <a href="https://example.com">the report</a> for details.</p>'
        md = scraper._convert_body_to_markdown(html)
        assert isinstance(md, str)


class TestApiRequestNew:
    """New tests for _api_request edge cases."""

    def test_successful_json_response(self, scraper):
        """Successful request returns parsed JSON dict."""
        from unittest.mock import MagicMock

        scraper._session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": {"status": "ok", "total": 42, "results": []}
        }
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        data = scraper._api_request(params={"tag": "test"})
        assert data["response"]["total"] == 42

    def test_http_error_non_200(self, scraper):
        """None from _request_with_retry raises NetworkError."""
        from unittest.mock import MagicMock
        from app.utils.errors import NetworkError

        scraper._session = MagicMock()
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._api_request(params={"tag": "test"})

    def test_json_parse_error(self, scraper):
        """ValueError from response.json() raises ParsingError."""
        from unittest.mock import MagicMock
        from app.utils.errors import ParsingError

        scraper._session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("bad json")
        scraper._request_with_retry = MagicMock(return_value=mock_response)

        with pytest.raises(ParsingError):
            scraper._api_request(params={"tag": "test"})

    def test_connection_error(self, scraper):
        """ConnectionError from _request_with_retry returns None -> NetworkError."""
        from unittest.mock import MagicMock
        from app.utils.errors import NetworkError

        scraper._session = MagicMock()
        scraper._request_with_retry = MagicMock(return_value=None)

        with pytest.raises(NetworkError):
            scraper._api_request(params={"tag": "bad"})


class TestScrapeFlowNew:
    """New tests for scrape() flow."""

    def test_searches_multiple_tags(self, scraper):
        """Scrape iterates through SUBJECT_TAGS."""
        from unittest.mock import MagicMock

        # Limit to 2 tags for simplicity
        scraper.SUBJECT_TAGS = ["tag-a", "tag-b"]
        scraper._from_date = None
        scraper._newest_article_date = None

        empty_response = {"response": {"pages": 1, "total": 0, "results": []}}
        scraper._api_request = MagicMock(return_value=empty_response)

        result = scraper.scrape()

        assert result.status == "completed"
        assert scraper._api_request.call_count == 2

    def test_pagination_stops_at_max_pages(self, scraper):
        """max_pages limits how many API pages are fetched per tag."""
        from unittest.mock import MagicMock

        scraper.SUBJECT_TAGS = ["single-tag"]
        scraper.max_pages = 1
        scraper._from_date = None
        scraper._newest_article_date = None

        page1_response = {
            "response": {
                "pages": 5,
                "total": 250,
                "results": [],
            }
        }
        scraper._api_request = MagicMock(return_value=page1_response)

        result = scraper.scrape()

        assert result.status == "completed"
        # Only 1 page should be fetched due to max_pages=1
        assert scraper._api_request.call_count == 1

    def test_no_results_on_first_page(self, scraper):
        """Empty results list on first page stops tag scraping."""
        from unittest.mock import MagicMock

        scraper.SUBJECT_TAGS = ["empty-tag"]
        scraper._from_date = None
        scraper._newest_article_date = None

        empty_response = {"response": {"pages": 1, "total": 0, "results": []}}
        scraper._api_request = MagicMock(return_value=empty_response)

        result = scraper.scrape()

        assert result.status == "completed"
        assert result.scraped_count == 0
