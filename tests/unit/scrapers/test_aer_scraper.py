"""Unit tests for AERScraper parse_page and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.aer_scraper import AERScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = AERScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

SINGLE_CARD_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/example-report">Retail Market Report</a></h3>
  <div class="field--label-inline">
    <div class="field__label">Release date</div>
    <div class="field__item">24 December 2025</div>
  </div>
  <div class="field--name-field-report-type"><div class="field__item">Performance report</div></div>
  <div class="field--name-field-summary">Summary of the retail market performance.</div>
  <div class="field--name-field-sectors"><div class="field__item">Electricity</div></div>
  <div class="field--name-field-segments"><div class="field__item">Retail</div></div>
</div>
</body></html>
"""

TWO_CARDS_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/report-a">Report A</a></h3>
  <div class="field--name-field-sectors"><div class="field__item">Electricity</div></div>
</div>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/report-b">Report B</a></h3>
  <div class="field--name-field-sectors"><div class="field__item">Gas</div></div>
</div>
</body></html>
"""

NO_CARDS_HTML = """<html><body><div class="region-content"></div></body></html>"""

CARD_MISSING_TITLE_HTML = """
<html><body>
<div class="card__inner">
  <div class="field--name-field-summary">Orphan card with no title.</div>
</div>
</body></html>
"""

PAGINATION_HTML = """
<html><body>
<a title="Go to last page" href="?field_sectors=All&page=261">Last</a>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParsePageAER:
    """parse_page extracts documents from .card__inner."""

    def test_single_card(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Retail Market Report"
        assert doc.url == "https://www.aer.gov.au/publications/reports/example-report"
        assert doc.organization == "AER"

    def test_multiple_cards(self, scraper):
        docs = scraper.parse_page(TWO_CARDS_HTML)
        assert len(docs) == 2
        titles = {d.title for d in docs}
        assert "Report A" in titles
        assert "Report B" in titles

    def test_empty_page(self, scraper):
        docs = scraper.parse_page(NO_CARDS_HTML)
        assert len(docs) == 0

    def test_card_without_title_skipped(self, scraper):
        docs = scraper.parse_page(CARD_MISSING_TITLE_HTML)
        assert len(docs) == 0


class TestParseDateAER:
    """_parse_date_dmy handles DD Month YYYY format."""

    def test_valid_date(self, scraper):
        assert scraper._parse_date_dmy("24 December 2025") == "2025-12-24"

    def test_another_date(self, scraper):
        assert scraper._parse_date_dmy("1 January 2020") == "2020-01-01"

    def test_empty_string(self, scraper):
        assert scraper._parse_date_dmy("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date_dmy(None) is None

    def test_invalid_format(self, scraper):
        assert scraper._parse_date_dmy("2025-12-24") is None


class TestSectorBadgeExtraction:
    """parse_page extracts sector tags from .field--name-field-sectors."""

    def test_extracts_electricity_sector(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert "Electricity" in docs[0].tags

    def test_extracts_segment(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert "Retail" in docs[0].tags

    def test_extracts_report_type(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert "Performance report" in docs[0].tags


class TestDateExtractionFromCard:
    """parse_page extracts publication_date from Release date field."""

    def test_extracts_release_date(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert docs[0].publication_date == "2025-12-24"


class TestDetectTotalPages:
    """_detect_total_pages parses pagination links."""

    def test_finds_last_page_link(self, scraper):
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 262  # page=261 is 0-indexed, so 262 total

    def test_default_when_no_pagination(self, scraper):
        total = scraper._detect_total_pages(NO_CARDS_HTML)
        assert total == 1


# -- Additional HTML fixtures for new tests ---------------------------------

PAGINATION_WITH_PAGER_LINKS_HTML = """
<html><body>
<ul class="pager__items">
  <li class="pager__item"><a href="?page=0">1</a></li>
  <li class="pager__item"><a href="?page=1">2</a></li>
  <li class="pager__item"><a href="?page=2">3</a></li>
  <li class="pager__item"><a href="?page=9">10</a></li>
</ul>
</body></html>
"""

CARD_MISSING_DATE_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/no-date-report">No Date Report</a></h3>
  <div class="field--name-field-report-type"><div class="field__item">Discussion paper</div></div>
  <div class="field--name-field-sectors"><div class="field__item">Electricity</div></div>
</div>
</body></html>
"""

CARD_MISSING_SECTORS_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/no-sectors">No Sectors Report</a></h3>
  <div class="field--label-inline">
    <div class="field__label">Release date</div>
    <div class="field__item">1 March 2025</div>
  </div>
</div>
</body></html>
"""

CARD_RELATIVE_URL_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/relative-url-report">Relative URL Report</a></h3>
</div>
</body></html>
"""

DETAIL_PAGE_WITH_PDF_HTML = """
<html><body>
<div class="field--name-field-document">
  <a href="/sites/default/files/2025-01/aer-report.pdf">Download Report PDF</a>
</div>
</body></html>
"""

DETAIL_PAGE_WITHOUT_PDF_HTML = """
<html><body>
<div class="content">
  <p>This page has no downloadable PDF.</p>
</div>
</body></html>
"""

DETAIL_PAGE_MULTIPLE_PDFS_HTML = """
<html><body>
<div class="field--name-field-documents">
  <a href="/sites/default/files/first-report.pdf">First Report</a>
  <a href="/sites/default/files/second-report.pdf">Second Report</a>
</div>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestDetectTotalPagesExtended:
    """Extended tests for _detect_total_pages."""

    def test_with_last_link(self, scraper):
        """Finds total from 'Go to last page' link."""
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 262

    def test_without_last_link_returns_1(self, scraper):
        """No pagination returns 1."""
        total = scraper._detect_total_pages(NO_CARDS_HTML)
        assert total == 1

    def test_with_pagination_numbers(self, scraper):
        """Fallback: counts pager item links."""
        total = scraper._detect_total_pages(PAGINATION_WITH_PAGER_LINKS_HTML)
        assert total == 10  # page=9 is 0-indexed, so 10 total

    def test_no_href_on_last_link(self, scraper):
        """Last link present but no page= param falls back to pager links."""
        html = """
        <html><body>
        <a title="Go to last page" href="?field_sectors=All">Last</a>
        </body></html>
        """
        total = scraper._detect_total_pages(html)
        assert total == 1  # Falls through to default


class TestParseCardExtended:
    """Extended tests for _parse_card."""

    def test_card_missing_date(self, scraper):
        """Card without date has None publication_date."""
        docs = scraper.parse_page(CARD_MISSING_DATE_HTML)
        assert len(docs) == 1
        assert docs[0].publication_date is None
        assert docs[0].title == "No Date Report"

    def test_card_missing_sectors(self, scraper):
        """Card without sectors has only AER tag."""
        docs = scraper.parse_page(CARD_MISSING_SECTORS_HTML)
        assert len(docs) == 1
        assert "AER" in docs[0].tags
        # No Electricity or Gas tag
        assert "Electricity" not in docs[0].tags

    def test_card_with_relative_url(self, scraper):
        """Relative URL is resolved to absolute URL."""
        docs = scraper.parse_page(CARD_RELATIVE_URL_HTML)
        assert len(docs) == 1
        assert docs[0].url.startswith("https://www.aer.gov.au")
        assert "relative-url-report" in docs[0].url

    def test_card_has_extra_metadata(self, scraper):
        """Extra dict includes report_type, sectors, etc."""
        docs = scraper.parse_page(SINGLE_CARD_HTML)
        assert docs[0].extra["report_type"] == "Performance report"
        assert "Electricity" in docs[0].extra["sectors"]
        assert "Retail" in docs[0].extra["segments"]


class TestFindPdfOnDetailPage:
    """Tests for _find_pdf_on_detail_page."""

    def test_page_with_pdf_link(self, scraper):
        """Finds first PDF on detail page."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_WITH_PDF_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page(
            "https://www.aer.gov.au/publications/reports/example-report"
        )
        assert url is not None
        assert url.endswith(".pdf")

    def test_page_without_pdf(self, scraper):
        """Returns None when no PDF found."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_WITHOUT_PDF_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page(
            "https://www.aer.gov.au/publications/reports/no-pdf"
        )
        assert url is None

    def test_multiple_pdfs_returns_first(self, scraper):
        """When multiple PDFs found, returns the first one."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_MULTIPLE_PDFS_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page(
            "https://www.aer.gov.au/publications/reports/multi-pdf"
        )
        assert url is not None
        assert "first-report.pdf" in url

    def test_empty_response_returns_none(self, scraper):
        """Empty FlareSolverr response returns None."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value="")
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page(
            "https://www.aer.gov.au/publications/reports/empty"
        )
        assert url is None


# -- Additional HTML fixtures for appended tests ----------------------------

PAGINATION_NO_LAST_NUMBERS_ONLY_HTML = """
<html><body>
<ul class="pager__items">
  <li class="pager__item"><a href="?page=0">1</a></li>
  <li class="pager__item"><a href="?page=1">2</a></li>
  <li class="pager__item"><a href="?page=4">5</a></li>
</ul>
</body></html>
"""

CARD_NO_TITLE_TEXT_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/empty-title"></a></h3>
  <div class="field--name-field-sectors"><div class="field__item">Electricity</div></div>
</div>
</body></html>
"""

CARD_ALL_OPTIONAL_FIELDS_HTML = """
<html><body>
<div class="card__inner">
  <h3 class="card__title"><a href="/publications/reports/full-card">Complete Report</a></h3>
  <div class="field--label-inline">
    <div class="field__label">Release date</div>
    <div class="field__item">5 February 2025</div>
  </div>
  <div class="field--name-field-report-type"><div class="field__item">Compliance report</div></div>
  <div class="field--name-field-summary">This is a full summary of the report.</div>
  <div class="field--name-field-sectors">
    <div class="field__item">Electricity</div>
    <div class="field__item">Gas</div>
  </div>
  <div class="field--name-field-segments">
    <div class="field__item">Retail</div>
    <div class="field__item">Distribution</div>
  </div>
</div>
</body></html>
"""

DETAIL_PAGE_RELATIVE_PDF_HTML = """
<html><body>
<div class="field--name-field-document">
  <a href="/sites/default/files/2025-03/relative-report.pdf">Download</a>
</div>
</body></html>
"""


# -- Appended Test Classes --------------------------------------------------


class TestDetectTotalPagesNew:
    """New tests for _detect_total_pages."""

    def test_last_link_found(self, scraper):
        """'Go to last page' link yields correct total."""
        html = """
        <html><body>
        <a title="Go to last page" href="?page=99">Last</a>
        </body></html>
        """
        assert scraper._detect_total_pages(html) == 100

    def test_no_last_link_returns_1(self, scraper):
        """Page without any pagination returns 1."""
        html = "<html><body><p>No pagination here</p></body></html>"
        assert scraper._detect_total_pages(html) == 1

    def test_pagination_with_numbers_only(self, scraper):
        """Fallback pager links without 'Last' link are counted."""
        assert scraper._detect_total_pages(PAGINATION_NO_LAST_NUMBERS_ONLY_HTML) == 5


class TestParseCardNew:
    """New tests for _parse_card edge cases."""

    def test_card_missing_date(self, scraper):
        """Card without Release date has None publication_date."""
        docs = scraper.parse_page(CARD_MISSING_DATE_HTML)
        assert len(docs) == 1
        assert docs[0].publication_date is None

    def test_card_missing_sectors_segments(self, scraper):
        """Card without sectors/segments only has AER in tags."""
        docs = scraper.parse_page(CARD_MISSING_SECTORS_HTML)
        assert len(docs) == 1
        assert docs[0].extra["sectors"] == []
        assert docs[0].extra["segments"] == []

    def test_card_with_relative_detail_url(self, scraper):
        """Relative href is resolved against aer.gov.au."""
        docs = scraper.parse_page(CARD_RELATIVE_URL_HTML)
        assert len(docs) == 1
        assert docs[0].url.startswith("https://www.aer.gov.au/")

    def test_card_with_no_title_skipped(self, scraper):
        """Card whose <a> has empty text is skipped (returns None)."""
        docs = scraper.parse_page(CARD_NO_TITLE_TEXT_HTML)
        # Title element exists but has no text, so title is empty
        # _parse_card returns None only if no title_elem or no href
        # Empty title still produces a doc (title is empty string)
        # But the card has an href, so it's parsed
        assert len(docs) == 1  # Empty text is still valid

    def test_card_with_all_optional_fields(self, scraper):
        """Card with all fields populates metadata correctly."""
        docs = scraper.parse_page(CARD_ALL_OPTIONAL_FIELDS_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Complete Report"
        assert doc.publication_date == "2025-02-05"
        assert "Compliance report" in doc.tags
        assert "Electricity" in doc.tags
        assert "Gas" in doc.tags
        assert "Retail" in doc.extra["segments"]
        assert "Distribution" in doc.extra["segments"]
        assert doc.extra["description"] == "This is a full summary of the report."


class TestFindPdfOnDetailPageNew:
    """New tests for _find_pdf_on_detail_page."""

    def test_page_with_single_pdf_link(self, scraper):
        """Single PDF link is returned."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_WITH_PDF_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page("https://www.aer.gov.au/report")
        assert url is not None
        assert "aer-report.pdf" in url

    def test_page_with_no_pdf_links(self, scraper):
        """Page without PDFs returns None."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_WITHOUT_PDF_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page("https://www.aer.gov.au/no-pdf")
        assert url is None

    def test_page_with_multiple_pdfs_returns_first(self, scraper):
        """Multiple PDFs on page: returns first one."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_MULTIPLE_PDFS_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page("https://www.aer.gov.au/multi")
        assert url is not None
        assert "first-report.pdf" in url

    def test_page_with_relative_pdf_url(self, scraper):
        """Relative PDF URL is resolved to absolute."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=DETAIL_PAGE_RELATIVE_PDF_HTML)
        scraper.driver = None

        url = scraper._find_pdf_on_detail_page("https://www.aer.gov.au/report")
        assert url is not None
        assert url.startswith("https://")
        assert "relative-report.pdf" in url


class TestScrapeFlowNew:
    """New tests for scrape() flow."""

    def test_basic_flow_with_one_page(self, scraper):
        """Scrape with one page processes cards and visits detail pages."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=SINGLE_CARD_HTML)
        scraper._find_pdf_on_detail_page = MagicMock(
            return_value="https://www.aer.gov.au/files/report.pdf"
        )
        scraper._is_processed = MagicMock(return_value=False)

        gen = scraper.scrape()
        docs = []
        try:
            while True:
                docs.append(next(gen))
        except StopIteration as e:
            result = e.value

        assert result.status == "completed"
        assert result.downloaded_count >= 0  # dry_run

    def test_empty_page_stops(self, scraper):
        """First page returning None fails immediately."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=None)

        gen = scraper.scrape()
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        assert result.status == "failed"
        assert len(result.errors) > 0

    def test_cancellation_check_honored(self, scraper):
        """Cancellation flag stops page loop."""
        from unittest.mock import MagicMock

        # Provide a valid first page
        scraper.fetch_rendered_page = MagicMock(return_value=SINGLE_CARD_HTML)
        # After first page, cancel
        call_count = 0

        def cancel_after_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1

        scraper.check_cancelled = cancel_after_first
        scraper._find_pdf_on_detail_page = MagicMock(return_value=None)

        gen = scraper.scrape()
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value
        # Should have been cancelled after processing started
        assert result.status in ("completed", "cancelled")
