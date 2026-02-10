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
    """_parse_date handles DD Month YYYY format."""

    def test_valid_date(self, scraper):
        assert scraper._parse_date("24 December 2025") == "2025-12-24"

    def test_another_date(self, scraper):
        assert scraper._parse_date("1 January 2020") == "2020-01-01"

    def test_empty_string(self, scraper):
        assert scraper._parse_date("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date(None) is None

    def test_invalid_format(self, scraper):
        assert scraper._parse_date("2025-12-24") is None


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
