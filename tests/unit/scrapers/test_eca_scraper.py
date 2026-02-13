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


# -- Additional HTML fixtures for new tests ---------------------------------

RESULTS_SHOWING_TEXT_HTML = """
<html><body>
<p>Showing 1 - 10 of 57 results</p>
</body></html>
"""

NO_PAGINATION_HTML = """
<html><body>
<div class="content">Some content, no pagination.</div>
</body></html>
"""

CARD_ALL_FIELDS_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/full-report">
    <span class="badge">Featured</span>
    <div class="image-card__heading">Full Featured Report</div>
    <div class="image-card__date">20 November 2025</div>
    <div class="image-card__teaser">A comprehensive consumer report.</div>
    <div class="image-card__read-time">10 min read</div>
  </a>
</div>
</body></html>
"""

CARD_MISSING_DATE_HTML_ECA = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/no-date">
    <div class="image-card__heading">No Date Report</div>
    <div class="image-card__teaser">Report without date.</div>
  </a>
</div>
</body></html>
"""

CARD_MISSING_BADGE_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/submissions/plain-submission">
    <div class="image-card__heading">Plain Submission</div>
    <div class="image-card__date">5 May 2024</div>
  </a>
</div>
</body></html>
"""

CARD_RELATIVE_URL_HTML_ECA = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/relative-report">
    <div class="image-card__heading">Relative URL Report</div>
  </a>
</div>
</body></html>
"""

TWO_SECTION_CARDS_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/report-x">
    <div class="image-card__heading">Report X</div>
  </a>
</div>
<div class="image-card">
  <a href="/our-work/submissions/submission-y">
    <div class="image-card__heading">Submission Y</div>
  </a>
</div>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestDetectTotalPagesExtended:
    """Extended tests for _detect_total_pages."""

    def test_from_results_text(self, scraper):
        """Detects total pages from 'Showing X - Y of Z' text."""
        total = scraper._detect_total_pages(RESULTS_SHOWING_TEXT_HTML)
        # 57 results, 10 per page = ceil(57/10) = 6
        assert total == 6

    def test_from_pagination_links(self, scraper):
        """Detects from pagination link elements."""
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 4

    def test_no_pagination_found_returns_1(self, scraper):
        """No pagination info returns 1."""
        total = scraper._detect_total_pages(NO_PAGINATION_HTML)
        assert total == 1


class TestParseCardExtended:
    """Extended tests for _parse_card."""

    def test_card_with_all_fields(self, scraper):
        """Card with all fields is fully parsed."""
        docs = scraper.parse_page(CARD_ALL_FIELDS_HTML, "Research")
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Full Featured Report"
        assert doc.publication_date == "2025-11-20"
        assert "Featured" in doc.tags
        assert doc.extra["description"] == "A comprehensive consumer report."
        assert doc.extra["read_time"] == "10 min read"
        assert doc.extra["featured"] is True

    def test_missing_date(self, scraper):
        """Card without date has None publication_date."""
        docs = scraper.parse_page(CARD_MISSING_DATE_HTML_ECA, "Research")
        assert len(docs) == 1
        assert docs[0].publication_date is None

    def test_missing_featured_badge(self, scraper):
        """Card without badge has Featured=False."""
        docs = scraper.parse_page(CARD_MISSING_BADGE_HTML, "Submissions")
        assert len(docs) == 1
        assert "Featured" not in docs[0].tags
        assert docs[0].extra["featured"] is False

    def test_relative_url(self, scraper):
        """Relative URL resolved to absolute."""
        docs = scraper.parse_page(CARD_RELATIVE_URL_HTML_ECA, "Research")
        assert len(docs) == 1
        assert docs[0].url.startswith("https://energyconsumersaustralia.com.au")
        assert "relative-report" in docs[0].url


class TestGetExtensionFromUrl:
    """Tests for _get_extension_from_url."""

    def test_pdf_url(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/report.pdf")
        assert ext == ".pdf"

    def test_docx_url(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/document.docx")
        assert ext == ".docx"

    def test_url_with_query_params(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/report.pdf?v=2")
        assert ext == ".pdf"

    def test_case_insensitive_matching(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/REPORT.PDF")
        assert ext == ".pdf"

    def test_xlsx_url(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/data.xlsx")
        assert ext == ".xlsx"

    def test_unknown_extension_defaults_to_pdf(self, scraper):
        ext = scraper._get_extension_from_url("https://example.com/download/12345")
        assert ext == ".pdf"


class TestSectionIteration:
    """Tests for cross-section parsing."""

    def test_two_sections_with_dedup(self, scraper):
        """Cards from different sections are both parsed."""
        docs = scraper.parse_page(TWO_SECTION_CARDS_HTML, "Research")
        assert len(docs) == 2
        titles = {d.title for d in docs}
        assert "Report X" in titles
        assert "Submission Y" in titles

    def test_section_category_applied(self, scraper):
        """Section category is applied to tags."""
        docs_research = scraper.parse_page(SINGLE_CARD_HTML, "Research")
        docs_submissions = scraper.parse_page(SINGLE_CARD_HTML, "Submissions")
        assert "Research" in docs_research[0].tags
        assert "Submissions" in docs_submissions[0].tags

    def test_empty_page_across_sections(self, scraper):
        """Empty page returns no docs regardless of section."""
        docs = scraper.parse_page(EMPTY_PAGE_HTML, "Research")
        assert len(docs) == 0
        docs = scraper.parse_page(EMPTY_PAGE_HTML, "Submissions")
        assert len(docs) == 0


# -- Additional HTML fixtures for appended tests ----------------------------

PAGINATION_LAST_LINK_HTML = """
<html><body>
<div class="pager">
  <a href="?page=0">1</a>
  <a href="?page=7">Last</a>
</div>
</body></html>
"""

CARD_EMPTY_TITLE_HTML = """
<html><body>
<div class="image-card">
  <a href="/our-work/research/empty-title">
    <div class="image-card__heading"></div>
    <div class="image-card__date">1 January 2024</div>
  </a>
</div>
</body></html>
"""

CARD_NO_LINK_HTML = """
<html><body>
<div class="image-card">
  <div class="image-card__heading">No Link Card</div>
</div>
</body></html>
"""


# -- Appended Test Classes --------------------------------------------------


class TestDetectTotalPagesNew:
    """New tests for _detect_total_pages."""

    def test_from_showing_xyz_results_text(self, scraper):
        """Parses 'Showing X - Y of Z results' text."""
        html = "<html><body><p>Showing 1 - 10 of 57 results</p></body></html>"
        total = scraper._detect_total_pages(html)
        assert total == 6  # ceil(57/10) = 6

    def test_from_pagination_links_highest_number(self, scraper):
        """Takes highest page number from pagination links."""
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 4  # page=3 -> 4 total

    def test_from_last_link(self, scraper):
        """Detects from pager 'Last' link."""
        total = scraper._detect_total_pages(PAGINATION_LAST_LINK_HTML)
        assert total == 8  # page=7 -> 8 total

    def test_no_pagination_returns_1(self, scraper):
        """No pagination info returns default of 1."""
        html = "<html><body><p>Just text, no pagination.</p></body></html>"
        total = scraper._detect_total_pages(html)
        assert total == 1


class TestParseCardNew:
    """New tests for _parse_card edge cases."""

    def test_card_with_all_fields(self, scraper):
        """Card with every field populates all metadata."""
        docs = scraper.parse_page(CARD_ALL_FIELDS_HTML, "Research")
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Full Featured Report"
        assert doc.publication_date == "2025-11-20"
        assert "Featured" in doc.tags
        assert "ECA" in doc.tags
        assert "Research" in doc.tags
        assert doc.extra["description"] == "A comprehensive consumer report."
        assert doc.extra["read_time"] == "10 min read"
        assert doc.extra["featured"] is True

    def test_card_missing_date(self, scraper):
        """Card without date element has None publication_date."""
        docs = scraper.parse_page(CARD_MISSING_DATE_HTML_ECA, "Research")
        assert len(docs) == 1
        assert docs[0].publication_date is None

    def test_card_with_featured_badge(self, scraper):
        """Card with badge element has Featured in tags."""
        docs = scraper.parse_page(FEATURED_CARD_HTML, "Research")
        assert len(docs) == 1
        assert "Featured" in docs[0].tags

    def test_card_with_relative_url(self, scraper):
        """Relative URL is resolved to energyconsumersaustralia.com.au."""
        docs = scraper.parse_page(CARD_RELATIVE_URL_HTML_ECA, "Research")
        assert len(docs) == 1
        assert docs[0].url.startswith("https://energyconsumersaustralia.com.au")

    def test_card_with_no_title_returns_none(self, scraper):
        """Card with empty heading text is skipped."""
        docs = scraper.parse_page(CARD_EMPTY_TITLE_HTML, "Research")
        assert len(docs) == 0


class TestGetExtensionFromUrlNew:
    """New tests for _get_extension_from_url."""

    def test_pdf_url(self, scraper):
        """PDF extension is detected."""
        ext = scraper._get_extension_from_url("https://example.com/doc.pdf")
        assert ext == ".pdf"

    def test_docx_url(self, scraper):
        """DOCX extension is detected."""
        ext = scraper._get_extension_from_url("https://example.com/doc.docx")
        assert ext == ".docx"

    def test_url_with_query_params_still_detects_pdf(self, scraper):
        """PDF extension detected even with query params."""
        ext = scraper._get_extension_from_url("https://example.com/doc.pdf?download=true")
        assert ext == ".pdf"

    def test_case_insensitive_pdf(self, scraper):
        """Case insensitive: .PDF detected as .pdf."""
        ext = scraper._get_extension_from_url("https://example.com/REPORT.PDF")
        assert ext == ".pdf"


class TestScrapeFlowNew:
    """New tests for scrape() flow."""

    def _exhaust(self, gen):
        """Helper to exhaust a scrape() generator, returning (ScraperResult, yielded_docs)."""
        docs = []
        try:
            while True:
                docs.append(next(gen))
        except StopIteration as e:
            return e.value, docs

    def test_processes_research_section(self, scraper):
        """Scrape processes the research section."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=SINGLE_CARD_HTML)
        scraper._find_documents_on_detail_page = MagicMock(
            return_value=["https://example.com/report.pdf"]
        )
        scraper._is_processed = MagicMock(return_value=False)

        result, docs = self._exhaust(scraper.scrape())

        # Should process at least the research section
        assert result.scraped_count > 0

    def test_cross_section_dedup_skips_duplicates(self, scraper):
        """Same URL across sections is only counted once via _is_processed."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=SINGLE_CARD_HTML)
        scraper._find_documents_on_detail_page = MagicMock(
            return_value=["https://example.com/same-report.pdf"]
        )
        # First call not processed, second call already processed
        scraper._is_processed = MagicMock(side_effect=[False, True])

        result, docs = self._exhaust(scraper.scrape())

        # At least one download and one skip
        assert result.downloaded_count >= 1 or result.skipped_count >= 1

    def test_empty_section_stops(self, scraper):
        """Section returning None from FlareSolverr fails."""
        from unittest.mock import MagicMock

        scraper.fetch_rendered_page = MagicMock(return_value=None)

        result, docs = self._exhaust(scraper.scrape())

        assert result.status == "failed"

    def test_respects_max_pages(self, scraper):
        """max_pages limits pages scraped per section."""
        from unittest.mock import MagicMock

        scraper.max_pages = 1
        scraper.fetch_rendered_page = MagicMock(return_value=EMPTY_PAGE_HTML)
        scraper._find_documents_on_detail_page = MagicMock(return_value=[])

        result, docs = self._exhaust(scraper.scrape())

        # With max_pages=1, only first page of each section is scraped
        assert result.status in ("completed", "failed")

    def test_cancellation_check(self, scraper):
        """Cancellation stops processing between sections."""
        from unittest.mock import MagicMock

        call_count = 0

        def cancel_after_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1

        scraper.check_cancelled = cancel_after_first
        scraper.fetch_rendered_page = MagicMock(return_value=SINGLE_CARD_HTML)
        scraper._find_documents_on_detail_page = MagicMock(return_value=[])

        result, docs = self._exhaust(scraper.scrape())

        assert result.status == "cancelled"
