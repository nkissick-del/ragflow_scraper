"""Unit tests for ECAScraper parse_page and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.eca_scraper import ECAScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = ECAScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

SINGLE_CARD_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/energy-report">
    <div class="image-card__heading">Energy Consumer Sentiment Survey</div>
    <div class="image-card__date">15 July 2025</div>
    <div class="image-card__teaser">Quarterly survey of energy consumers.</div>
    <div class="image-card__read-time">5 min read</div>
  </a>
</div>
</body></html>
"""

TWO_CARDS_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/report-a">
    <div class="image-card__heading">Report A</div>
    <div class="image-card__date">1 January 2024</div>
  </a>
</div>
<div class="image-card">
  <a href="/our-work/submissions/submission-b">
    <div class="image-card__heading">Submission B</div>
    <div class="image-card__date">20 March 2024</div>
  </a>
</div>
</body></html>
"""

FEATURED_CARD_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/featured-report">
    <span class="badge">Featured</span>
    <div class="image-card__heading">Featured Report</div>
    <div class="image-card__date">10 August 2025</div>
  </a>
</div>
</body></html>
"""

EMPTY_PAGE_HTML = """<html><body><div class="main-content"></div></body></html>"""

PAGINATION_HTML = """
<html><body>
<div class="pagination">
  <a href="?page=0">1</a>
  <a href="?page=1">2</a>
  <a href="?page=2">3</a>
  <a href="?page=3">4</a>
</div>
</body></html>
"""

RESULTS_COUNT_HTML = """
<html><body>
<p>Showing 1 - 12 of 45 results</p>
</body></html>
"""

NO_HEADING_CARD_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/no-heading">
    <div class="image-card__date">10 August 2025</div>
  </a>
</div>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParsePageECA:
    """parse_page extracts documents from .image-card."""

    def test_single_card(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML, "Research")
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Energy Consumer Sentiment Survey"
        assert "energyconsumersaustralia.com.au" in doc.url
        assert doc.organization == "ECA"

    def test_multiple_cards(self, scraper):
        docs = scraper.parse_page(TWO_CARDS_HTML, "Research")
        assert len(docs) == 2
        assert docs[0].title == "Report A"
        assert docs[1].title == "Submission B"

    def test_empty_page(self, scraper):
        docs = scraper.parse_page(EMPTY_PAGE_HTML)
        assert len(docs) == 0

    def test_featured_badge_tag(self, scraper):
        docs = scraper.parse_page(FEATURED_CARD_HTML, "Research")
        assert len(docs) == 1
        assert "Featured" in docs[0].tags

    def test_card_without_heading_skipped(self, scraper):
        docs = scraper.parse_page(NO_HEADING_CARD_HTML, "Research")
        assert len(docs) == 0


class TestParseDateECA:
    """_parse_date_dmy handles DD Month YYYY format."""

    def test_valid_date(self, scraper):
        assert scraper._parse_date_dmy("15 July 2025") == "2025-07-15"

    def test_another_date(self, scraper):
        assert scraper._parse_date_dmy("1 January 2020") == "2020-01-01"

    def test_empty_string(self, scraper):
        assert scraper._parse_date_dmy("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date_dmy(None) is None

    def test_invalid_format(self, scraper):
        assert scraper._parse_date_dmy("07/15/2025") is None


class TestDetectTotalPagesECA:
    """_detect_total_pages parses pagination and results text."""

    def test_detects_from_pagination_links(self, scraper):
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 4  # page=3 is 0-indexed => 4 total

    def test_detects_from_results_text(self, scraper):
        total = scraper._detect_total_pages(RESULTS_COUNT_HTML)
        # 45 results / 12 per page = 4 pages (ceil)
        assert total == 4

    def test_default_when_no_pagination(self, scraper):
        total = scraper._detect_total_pages(EMPTY_PAGE_HTML)
        assert total == 1


class TestCardMetadataExtraction:
    """parse_page extracts extra metadata fields from cards."""

    def test_extracts_teaser(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML, "Research")
        assert docs[0].extra["description"] == "Quarterly survey of energy consumers."

    def test_extracts_read_time(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML, "Research")
        assert docs[0].extra["read_time"] == "5 min read"

    def test_section_category_in_tags(self, scraper):
        docs = scraper.parse_page(SINGLE_CARD_HTML, "Submissions")
        assert "Submissions" in docs[0].tags
        assert "ECA" in docs[0].tags
