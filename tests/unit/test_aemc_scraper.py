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
