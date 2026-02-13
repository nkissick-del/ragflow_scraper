"""Unit tests for AEMCScraper _parse_reviews_table, _clean_text, _extract_cell_text."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.aemc_scraper import AEMCScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = AEMCScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

REVIEWS_TABLE_HTML = """
<html><body>
<table class="list-table">
  <tr><th>Check</th><th>Title</th><th>Date Initiated</th><th>Stage</th><th>Completion</th><th>Submission</th><th>Reference</th><th>Status</th></tr>
  <tr>
    <td></td>
    <td><a href="/our-work/review-one">Review One Title</a></td>
    <td>15 Jan 2024</td>
    <td>Final report</td>
    <td>30 Jun 2024</td>
    <td>28 Feb 2024</td>
    <td>EMO0042</td>
    <td>Completed</td>
  </tr>
  <tr>
    <td></td>
    <td><a href="/our-work/review-two">Review Two Title</a></td>
    <td>01 Mar 2023</td>
    <td>Draft report</td>
    <td></td>
    <td>15 Apr 2023</td>
    <td>ERC0328</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""

EMPTY_TABLE_HTML = """
<html><body>
<table class="list-table">
  <tr><th>Title</th><th>Date</th></tr>
</table>
</body></html>
"""

NO_TABLE_HTML = """<html><body><p>No table here.</p></body></html>"""

ZERO_WIDTH_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td><a href="/review">\u200bClean\u200b Title\u200b</a></td>
    <td>01 Jan 2024</td>
    <td>Open</td>
    <td></td>
    <td></td>
    <td>REF001</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParseReviewsTable:
    """_parse_reviews_table extracts review entries from <table class='list-table'>."""

    def test_extracts_two_reviews(self, scraper):
        reviews = scraper._parse_reviews_table(REVIEWS_TABLE_HTML)
        assert len(reviews) == 2

    def test_review_fields(self, scraper):
        reviews = scraper._parse_reviews_table(REVIEWS_TABLE_HTML)
        r = reviews[0]
        assert r["title"] == "Review One Title"
        assert r["url"] == "https://www.aemc.gov.au/our-work/review-one"
        assert r["date_initiated"] == "15 Jan 2024"
        assert r["stage"] == "Final report"
        assert r["reference"] == "EMO0042"
        assert r["status"] == "Completed"

    def test_empty_table_returns_empty(self, scraper):
        reviews = scraper._parse_reviews_table(EMPTY_TABLE_HTML)
        assert reviews == []

    def test_no_table_returns_empty(self, scraper):
        reviews = scraper._parse_reviews_table(NO_TABLE_HTML)
        assert reviews == []

    def test_second_review_url(self, scraper):
        reviews = scraper._parse_reviews_table(REVIEWS_TABLE_HTML)
        assert reviews[1]["url"] == "https://www.aemc.gov.au/our-work/review-two"
        assert reviews[1]["status"] == "Open"


class TestCleanText:
    """_clean_text strips zero-width characters and normalizes whitespace."""

    def test_removes_zero_width_space(self, scraper):
        assert scraper._clean_text("\u200bHello\u200b") == "Hello"

    def test_normalizes_whitespace(self, scraper):
        assert scraper._clean_text("  too   many   spaces  ") == "too many spaces"

    def test_replaces_html_entities(self, scraper):
        assert scraper._clean_text("A &amp; B") == "A & B"

    def test_empty_string(self, scraper):
        assert scraper._clean_text("") == ""

    def test_none_returns_empty(self, scraper):
        assert scraper._clean_text(None) == ""

    def test_nbsp_replaced(self, scraper):
        assert scraper._clean_text("word&nbsp;word") == "word word"


class TestExtractCellText:
    """_extract_cell_text retrieves cleaned text from a specific table cell."""

    def test_extracts_column_3(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]  # First data row
        text = scraper._extract_cell_text(row, 3)
        assert text == "15 Jan 2024"

    def test_extracts_column_7(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 7)
        assert text == "EMO0042"

    def test_missing_column_returns_empty(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 99)
        assert text == ""


class TestZeroWidthInTable:
    """_parse_reviews_table cleans zero-width characters from titles."""

    def test_title_cleaned(self, scraper):
        reviews = scraper._parse_reviews_table(ZERO_WIDTH_HTML)
        assert len(reviews) == 1
        assert reviews[0]["title"] == "Clean Title"


# -- Additional HTML fixtures for new tests ---------------------------------

REVIEW_ROW_MISSING_CELLS_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td><a href="/our-work/short-review">Short Review</a></td>
  </tr>
</table>
</body></html>
"""

REVIEW_ROW_NO_LINK_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td>No link here</td>
    <td>01 Jan 2024</td>
    <td>Open</td>
    <td></td>
    <td></td>
    <td>REF999</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""

REVIEW_ROW_NO_HREF_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td><a>Missing Href Title</a></td>
    <td>01 Jan 2024</td>
    <td>Open</td>
    <td></td>
    <td></td>
    <td>REF000</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""

REVIEW_PAGE_WITH_PDFS_HTML = """
<html><body>
<div class="field--name-field-documents">
  <a href="/sites/default/files/report-final.pdf">Final Report PDF</a>
  <a href="/sites/default/files/draft-report.pdf">Draft Report PDF</a>
</div>
<a href="/sites/default/files/report-final.pdf">Duplicate of Final Report</a>
</body></html>
"""

REVIEW_PAGE_NO_PDFS_HTML = """
<html><body>
<div class="field--name-field-documents">
  <a href="/about-this-review">About</a>
</div>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestCleanTextExtended:
    """Extended tests for _clean_text."""

    def test_removes_zero_width_characters(self, scraper):
        """Removes \u200b and related characters."""
        assert scraper._clean_text("\u200bTest\u200f") == "Test"

    def test_removes_extra_whitespace(self, scraper):
        """Normalizes multiple spaces to single space."""
        assert scraper._clean_text("  a   b   c  ") == "a b c"

    def test_handles_none(self, scraper):
        assert scraper._clean_text(None) == ""

    def test_handles_empty(self, scraper):
        assert scraper._clean_text("") == ""

    def test_mixed_invisible_chars(self, scraper):
        """Multiple different invisible chars removed."""
        assert scraper._clean_text("\u200b\u200c\u200dHello\u200e") == "Hello"

    def test_lt_gt_entities(self, scraper):
        assert scraper._clean_text("a &lt; b &gt; c") == "a < b > c"


class TestExtractCellTextExtended:
    """Extended tests for _extract_cell_text."""

    def test_valid_column(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 4)
        assert text == "Final report"

    def test_out_of_bounds_column(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 100)
        assert text == ""

    def test_row_with_fewer_cells(self, scraper):
        """Row with only 2 cells, requesting column 5 returns empty."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEW_ROW_MISSING_CELLS_HTML, "lxml")
        row = soup.select("tr")[0]
        text = scraper._extract_cell_text(row, 5)
        assert text == ""


class TestParseReviewRowExtended:
    """Extended tests for _parse_review_row."""

    def test_complete_row(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        review = scraper._parse_review_row(row)
        assert review is not None
        assert review["title"] == "Review One Title"
        assert review["url"] == "https://www.aemc.gov.au/our-work/review-one"
        assert review["reference"] == "EMO0042"

    def test_missing_cells(self, scraper):
        """Row with few cells still parses title and URL."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEW_ROW_MISSING_CELLS_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is not None
        assert review["title"] == "Short Review"

    def test_no_link_returns_none(self, scraper):
        """Row without an anchor in column 2 returns None."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEW_ROW_NO_LINK_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is None

    def test_no_href_returns_none(self, scraper):
        """Row with anchor but no href returns None."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(REVIEW_ROW_NO_HREF_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is None


class TestFindPdfsOnReviewPage:
    """Tests for _find_pdfs_on_review_page."""

    def test_page_with_pdf_links(self, scraper):
        """Finds PDF documents on a review detail page."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/review-one", session
        )
        assert len(pdfs) >= 1
        assert all(p.url.endswith(".pdf") for p in pdfs)

    def test_url_dedup(self, scraper):
        """Duplicate PDF URLs are deduplicated."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/review-one", session
        )
        urls = [p.url for p in pdfs]
        assert len(urls) == len(set(urls)), "Duplicate URLs should be removed"

    def test_no_pdfs_found(self, scraper):
        """Page with no PDF links returns empty list."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_NO_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/review-two", session
        )
        assert pdfs == []

    def test_request_failure_returns_empty(self, scraper):
        """When _request_with_retry returns None, returns empty list."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        scraper._request_with_retry = MagicMock(return_value=None)

        # Should catch the exception internally and return []
        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/fail", session
        )
        assert pdfs == []


# -- Additional HTML fixtures for new tests ---------------------------------

REVIEW_PAGE_RELATIVE_PDFS_HTML = """
<html><body>
<a href="files/relative-doc.pdf">Relative Document</a>
</body></html>
"""

REVIEW_PAGE_DUPLICATE_PDFS_HTML = """
<html><body>
<a href="/sites/default/files/same-report.pdf">Same Report</a>
<a href="/sites/default/files/same-report.pdf">Same Report Copy</a>
<a href="/sites/default/files/other-report.pdf">Other Report</a>
</body></html>
"""

TABLE_WITH_HEADER_ONLY_HTML = """
<html><body>
<table class="list-table">
  <tr><th>Title</th><th>Date</th><th>Stage</th></tr>
</table>
</body></html>
"""

TABLE_HIDDEN_ROWS_HTML = """
<html><body>
<table class="list-table">
  <tr><th>Check</th><th>Title</th><th>Date</th><th>Stage</th><th>Completion</th><th>Submission</th><th>Reference</th><th>Status</th></tr>
  <tr>
    <td></td>
    <td><a href="/our-work/visible-review">Visible Review</a></td>
    <td>01 Jan 2024</td>
    <td>Open</td>
    <td></td>
    <td></td>
    <td>REF001</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""

ROW_EMPTY_DATE_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td><a href="/our-work/no-date-review">No Date Review</a></td>
    <td></td>
    <td>Draft</td>
    <td></td>
    <td></td>
    <td>REF002</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""

ROW_WITHOUT_URL_HTML = """
<html><body>
<table class="list-table">
  <tr>
    <td></td>
    <td>Title Without Link</td>
    <td>01 Jan 2024</td>
    <td>Open</td>
    <td></td>
    <td></td>
    <td>REF003</td>
    <td>Open</td>
  </tr>
</table>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestCleanTextNew:
    """Additional _clean_text tests for zero-width and invisible characters."""

    def test_removes_zero_width_space_and_joiner(self, scraper):
        """Removes \\u200b (zero-width space) and \\u200c (zero-width non-joiner)."""
        result = scraper._clean_text("\u200bHello\u200cWorld")
        assert result == "HelloWorld"

    def test_collapses_whitespace(self, scraper):
        """Multiple spaces and tabs collapse to single space."""
        result = scraper._clean_text("  word1    word2\tword3  ")
        assert result == "word1 word2 word3"

    def test_handles_none_input(self, scraper):
        """None input returns empty string."""
        result = scraper._clean_text(None)
        assert result == ""

    def test_empty_string_returns_empty(self, scraper):
        """Empty string returns empty string."""
        result = scraper._clean_text("")
        assert result == ""


class TestExtractCellTextNew:
    """Additional _extract_cell_text tests."""

    def test_valid_column_index(self, scraper):
        """Valid column index extracts cleaned text."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 4)
        assert text == "Final report"

    def test_out_of_bounds_returns_empty(self, scraper):
        """Column index beyond available cells returns empty string."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        text = scraper._extract_cell_text(row, 50)
        assert text == ""

    def test_row_with_fewer_cells(self, scraper):
        """Row with only 2 cells, requesting column 5 returns empty."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(REVIEW_ROW_MISSING_CELLS_HTML, "lxml")
        row = soup.select("tr")[0]
        text = scraper._extract_cell_text(row, 5)
        assert text == ""


class TestParseReviewRowNew:
    """Additional _parse_review_row tests."""

    def test_complete_row_with_all_columns(self, scraper):
        """Complete row extracts all metadata fields."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(REVIEWS_TABLE_HTML, "lxml")
        row = soup.select("tr")[1]
        review = scraper._parse_review_row(row)
        assert review is not None
        assert review["title"] == "Review One Title"
        assert review["url"] == "https://www.aemc.gov.au/our-work/review-one"
        assert review["date_initiated"] == "15 Jan 2024"
        assert review["stage"] == "Final report"
        assert review["reference"] == "EMO0042"
        assert review["status"] == "Completed"

    def test_missing_title_cell_returns_none(self, scraper):
        """Row with no anchor in title column returns None."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(ROW_WITHOUT_URL_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is None

    def test_row_with_empty_date(self, scraper):
        """Row with empty date cell still parses successfully."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(ROW_EMPTY_DATE_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is not None
        assert review["title"] == "No Date Review"
        assert review["date_initiated"] == ""

    def test_row_without_href_returns_none(self, scraper):
        """Row with anchor but no href attribute returns None."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(REVIEW_ROW_NO_HREF_HTML, "lxml")
        row = soup.select("tr")[0]
        review = scraper._parse_review_row(row)
        assert review is None


class TestFindPdfsOnReviewPageNew:
    """Additional _find_pdfs_on_review_page tests."""

    def test_page_with_pdf_links(self, scraper):
        """Finds multiple PDF links on a review page."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/test-review", session
        )
        assert len(pdfs) >= 1
        assert all(p.url.endswith(".pdf") for p in pdfs)
        assert all(p.organization == "AEMC" for p in pdfs)

    def test_url_dedup_same_pdf_twice(self, scraper):
        """Duplicate PDF URLs are deduplicated."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_DUPLICATE_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/dedup-review", session
        )
        urls = [p.url for p in pdfs]
        assert len(urls) == len(set(urls)), "Duplicate URLs should be deduplicated"

    def test_no_pdfs_returns_empty(self, scraper):
        """Page with no PDF links returns empty list."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_NO_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/no-pdfs", session
        )
        assert pdfs == []

    def test_relative_url_resolved(self, scraper):
        """Relative PDF URLs are resolved to absolute."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = REVIEW_PAGE_RELATIVE_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=mock_resp)

        pdfs = scraper._find_pdfs_on_review_page(
            "https://www.aemc.gov.au/our-work/relative-review/", session
        )
        assert len(pdfs) == 1
        assert pdfs[0].url.startswith("https://")
        assert pdfs[0].url.endswith(".pdf")


class TestParseReviewsTableNew:
    """Additional _parse_reviews_table tests."""

    def test_valid_table_with_rows(self, scraper):
        """Table with data rows returns review dicts."""
        reviews = scraper._parse_reviews_table(REVIEWS_TABLE_HTML)
        assert len(reviews) == 2
        assert reviews[0]["title"] == "Review One Title"

    def test_empty_table_returns_empty(self, scraper):
        """Table with only header row returns empty list."""
        reviews = scraper._parse_reviews_table(TABLE_WITH_HEADER_ONLY_HTML)
        assert reviews == []

    def test_header_rows_skipped(self, scraper):
        """Header rows (th only) are filtered out, only data rows parsed."""
        reviews = scraper._parse_reviews_table(TABLE_HIDDEN_ROWS_HTML)
        assert len(reviews) == 1
        assert reviews[0]["title"] == "Visible Review"
