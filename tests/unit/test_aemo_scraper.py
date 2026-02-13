"""Unit tests for AEMOScraper parse_page and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.aemo_scraper import AEMOScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = AEMOScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

SINGLE_PDF_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/major-publications/report.pdf">
      <span>Electricity</span>
      <h3>Electricity Statement of Opportunities</h3>
      <div class="is-date field-publisheddate"><span>31/07/2025</span></div>
      <div class="search-result-list-item--content">File type PDF</div>
      <div class="search-result-list-item--content">Size 2.46 MB</div>
    </a>
  </li>
</ul>
</body></html>
"""

TWO_ITEMS_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/report1.pdf">
      <h3>Report One</h3>
      <div class="search-result-list-item--content">File type PDF</div>
    </a>
  </li>
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/report2.pdf">
      <h3>Report Two</h3>
      <div class="search-result-list-item--content">File type PDF</div>
    </a>
  </li>
</ul>
</body></html>
"""

NON_PDF_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/spreadsheet.xlsx">
      <h3>Data Spreadsheet</h3>
      <div class="search-result-list-item--content">File type XLSX</div>
    </a>
  </li>
</ul>
</body></html>
"""

EMPTY_LIST_HTML = """
<html><body>
<ul class="search-result-list"></ul>
</body></html>
"""

FALLBACK_SELECTOR_HTML = """
<html><body>
<a class="search-result-list-item" href="https://www.aemo.com.au/report.pdf">
  <h3>Standalone Link Item</h3>
  <div class="search-result-list-item--content">File type PDF</div>
</a>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParsePageBasic:
    """parse_page extracts documents from .search-result-list > li."""

    def test_extracts_single_pdf(self, scraper):
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Electricity Statement of Opportunities"
        assert doc.url.endswith("report.pdf")
        assert doc.organization == "AEMO"

    def test_extracts_multiple_documents(self, scraper):
        docs = scraper.parse_page(TWO_ITEMS_HTML)
        assert len(docs) == 2
        assert docs[0].title == "Report One"
        assert docs[1].title == "Report Two"

    def test_skips_non_pdf_files(self, scraper):
        docs = scraper.parse_page(NON_PDF_HTML)
        assert len(docs) == 0

    def test_empty_list_returns_no_documents(self, scraper):
        docs = scraper.parse_page(EMPTY_LIST_HTML)
        assert len(docs) == 0

    def test_fallback_selector_when_no_li(self, scraper):
        """When no <li> items exist, parse_page falls back to direct <a> selector."""
        docs = scraper.parse_page(FALLBACK_SELECTOR_HTML)
        assert len(docs) == 1
        assert docs[0].title == "Standalone Link Item"


class TestParseDateAEMO:
    """_parse_date handles DD/MM/YYYY and other formats."""

    def test_dd_mm_yyyy(self, scraper):
        assert scraper._parse_date("31/07/2025") == "2025-07-31"

    def test_dd_month_yyyy(self, scraper):
        assert scraper._parse_date("15 January 2024") == "2024-01-15"

    def test_dd_mon_yyyy(self, scraper):
        assert scraper._parse_date("1 Jul 2023") == "2023-07-01"

    def test_iso_format(self, scraper):
        assert scraper._parse_date("2025-12-01") == "2025-12-01"

    def test_empty_string(self, scraper):
        assert scraper._parse_date("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date(None) is None

    def test_unparseable_returns_none(self, scraper):
        assert scraper._parse_date("not-a-date") is None


class TestFileSizeExtraction:
    """parse_page extracts file_size_str from content divs."""

    def test_extracts_file_size(self, scraper):
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert len(docs) == 1
        assert docs[0].file_size_str == "2.46 MB"

    def test_extracts_file_size_bytes(self, scraper):
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert docs[0].file_size is not None
        assert docs[0].file_size > 0


class TestDateExtractionFromHTML:
    """parse_page extracts publication_date from .is-date.field-publisheddate."""

    def test_extracts_date_from_html(self, scraper):
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert len(docs) == 1
        assert docs[0].publication_date == "2025-07-31"


class TestCategoryTagExtraction:
    """parse_page extracts tags from category span."""

    def test_extracts_category_as_tag(self, scraper):
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert "Electricity" in docs[0].tags


# -- Additional HTML fixtures for appended tests ----------------------------

PAGINATION_WITH_LINKS_HTML = """
<html><body>
<div class="search-result-paging">
  <a>1</a>
  <a>2</a>
  <a>3</a>
  <a>5</a>
</div>
</body></html>
"""

NO_PAGINATION_HTML = """
<html><body>
<div class="content">No paging here.</div>
</body></html>
"""

CLOUDFLARE_CHALLENGE_HTML = """
<html><head><title>Just a moment...</title></head>
<body>
<div>Just a moment while we check your browser.</div>
</body></html>
"""

ITEM_MISSING_URL_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="">
      <h3>Missing URL Doc</h3>
      <div class="search-result-list-item--content">File type PDF</div>
    </a>
  </li>
</ul>
</body></html>
"""

ITEM_MISSING_TITLE_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/no-title.pdf">
      <div class="search-result-list-item--content">File type PDF</div>
    </a>
  </li>
</ul>
</body></html>
"""

ITEM_NON_PDF_EXTENSION_HTML = """
<html><body>
<ul class="search-result-list">
  <li>
    <a class="search-result-list-item" href="/media/-/media/files/data.csv">
      <h3>CSV Data File</h3>
      <div class="search-result-list-item--content">File type CSV</div>
    </a>
  </li>
</ul>
</body></html>
"""


# -- Appended Test Classes --------------------------------------------------


class TestDetectPaginationInfoNew:
    """New tests for _detect_pagination_info_from_html."""

    def test_js_rendered_pagination_with_total_count(self, scraper):
        """Pagination links in HTML yield correct total pages."""
        offset, pages = scraper._detect_pagination_info_from_html(PAGINATION_WITH_LINKS_HTML)
        assert offset == 0
        assert pages == 5

    def test_no_pagination_element_fallback(self, scraper):
        """No pagination elements falls back to default of 22."""
        offset, pages = scraper._detect_pagination_info_from_html(NO_PAGINATION_HTML)
        assert offset == 0
        assert pages == 22

    def test_explicit_count_from_html(self, scraper):
        """Single page link gives max_page of 1 which is < 2, so default is used."""
        html = """
        <html><body>
        <div class="search-result-paging">
          <a>1</a>
        </div>
        </body></html>
        """
        offset, pages = scraper._detect_pagination_info_from_html(html)
        assert offset == 0
        # max_page is 1 which is not > 1, so default 22 is used
        assert pages == 22


class TestFetchWithCloudflareRetryNew:
    """New tests for _fetch_with_cloudflare_retry."""

    def test_successful_first_attempt(self, scraper):
        """Clean HTML on first attempt is returned directly."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value="<html>Good content</html>")
        scraper._polite_delay = MagicMock()

        result = scraper._fetch_with_cloudflare_retry("https://example.com")

        assert result == "<html>Good content</html>"
        assert scraper.fetch_rendered_page.call_count == 1

    def test_cloudflare_detected_triggers_retry(self, scraper):
        """'Just a moment' on first attempt triggers retry."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(
            side_effect=[CLOUDFLARE_CHALLENGE_HTML, "<html>Good content</html>"]
        )
        scraper._polite_delay = MagicMock()

        result = scraper._fetch_with_cloudflare_retry("https://example.com")

        assert result == "<html>Good content</html>"
        assert scraper.fetch_rendered_page.call_count == 2

    def test_max_retries_exceeded_returns_none(self, scraper):
        """Cloudflare on both attempts returns None."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(
            side_effect=[CLOUDFLARE_CHALLENGE_HTML, CLOUDFLARE_CHALLENGE_HTML]
        )
        scraper._polite_delay = MagicMock()

        result = scraper._fetch_with_cloudflare_retry("https://example.com")

        assert result is None

    def test_successful_on_second_attempt(self, scraper):
        """Cloudflare on first, clean on second returns the clean HTML."""
        from unittest.mock import MagicMock

        clean_html = "<html><body>Real content</body></html>"
        scraper.fetch_rendered_page = MagicMock(
            side_effect=[CLOUDFLARE_CHALLENGE_HTML, clean_html]
        )
        scraper._polite_delay = MagicMock()

        result = scraper._fetch_with_cloudflare_retry("https://example.com")

        assert result == clean_html
        assert scraper.fetch_rendered_page.call_count == 2


class TestParseDocumentItemNew:
    """New tests for _parse_document_item."""

    def test_complete_document_item(self, scraper):
        """Complete document item is fully parsed."""
        docs = scraper.parse_page(SINGLE_PDF_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Electricity Statement of Opportunities"
        assert doc.organization == "AEMO"
        assert doc.publication_date == "2025-07-31"
        assert doc.file_size_str == "2.46 MB"

    def test_item_missing_url_returns_none(self, scraper):
        """Item with empty href is skipped."""
        docs = scraper.parse_page(ITEM_MISSING_URL_HTML)
        assert len(docs) == 0

    def test_item_missing_title_gets_filename_default(self, scraper):
        """Item without <h3> gets title from URL filename."""
        docs = scraper.parse_page(ITEM_MISSING_TITLE_HTML)
        assert len(docs) == 1
        # Title should be derived from filename "no-title.pdf" -> "no title"
        assert "no" in docs[0].title.lower() or "title" in docs[0].title.lower()

    def test_non_pdf_extension_detected_correctly(self, scraper):
        """Non-PDF file type (CSV) is skipped."""
        docs = scraper.parse_page(ITEM_NON_PDF_EXTENSION_HTML)
        assert len(docs) == 0


class TestParseDateNew:
    """New tests for _parse_date format handling."""

    def test_dd_mm_yyyy_format(self, scraper):
        """DD/MM/YYYY format is parsed correctly."""
        assert scraper._parse_date("15/03/2025") == "2025-03-15"

    def test_dd_month_yyyy_format(self, scraper):
        """'DD Month YYYY' format is parsed correctly."""
        assert scraper._parse_date("5 October 2024") == "2024-10-05"

    def test_iso_format(self, scraper):
        """ISO YYYY-MM-DD format passes through."""
        assert scraper._parse_date("2025-06-30") == "2025-06-30"

    def test_invalid_format_returns_none(self, scraper):
        """Unparseable date string returns None."""
        assert scraper._parse_date("not a date at all") is None


class TestScrapeFlowNew:
    """New tests for scrape() flow."""

    def test_basic_scrape_with_hash_fragment_pagination(self, scraper):
        """Scrape processes first page and detects pagination."""
        from unittest.mock import MagicMock

        scraper._fetch_with_cloudflare_retry = MagicMock(return_value=SINGLE_PDF_HTML)
        scraper._is_processed = MagicMock(return_value=False)
        scraper._polite_delay = MagicMock()
        # max_pages=1 from fixture limits to 1 page

        result = scraper.scrape()

        assert result.scraped_count >= 1
        assert result.downloaded_count >= 1  # dry_run

    def test_empty_page_stops(self, scraper):
        """None from _fetch_with_cloudflare_retry on first page fails."""
        from unittest.mock import MagicMock

        scraper._fetch_with_cloudflare_retry = MagicMock(return_value=None)

        result = scraper.scrape()

        assert result.status == "failed"
        assert len(result.errors) > 0

    def test_all_items_processed_skipped(self, scraper):
        """When all items are already processed, they are skipped."""
        from unittest.mock import MagicMock

        scraper._fetch_with_cloudflare_retry = MagicMock(return_value=SINGLE_PDF_HTML)
        scraper._is_processed = MagicMock(return_value=True)
        scraper._polite_delay = MagicMock()

        result = scraper.scrape()

        assert result.skipped_count >= 1
        assert result.downloaded_count == 0
