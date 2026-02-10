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
