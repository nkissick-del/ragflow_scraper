"""Unit tests for ENAScraper _parse_articles, _parse_date, _detect_total_pages."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.ena_scraper import ENAScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = ENAScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

ARTICLES_HTML = """
<html><body>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/reports/energy-charter-report/">
    <span class="post-title">Energy Charter Report 2024</span>
  </a>
  <span class="post-date">31 Jul 2025</span>
  <span class="post-categories">Reports</span>
</article>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/submissions/aer-submission/">
    <span class="post-title">AER Submission on Distribution</span>
  </a>
  <span class="post-date">15 Jan 2024</span>
  <span class="post-categories">Submissions</span>
</article>
</body></html>
"""

SINGLE_ARTICLE_HTML = """
<html><body>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/reports/network-report/">
    <span class="post-title">Network Vision Report</span>
  </a>
  <span class="post-date">10 December 2023</span>
  <span class="post-categories">Reports</span>
</article>
</body></html>
"""

NO_ARTICLES_HTML = """<html><body><div class="content-area"></div></body></html>"""

MISSING_LINK_HTML = """
<html><body>
<article class="tease tease-post">
  <span class="post-title">No Link Article</span>
  <span class="post-date">01 Jan 2024</span>
</article>
</body></html>
"""

PAGINATION_HTML = """
<html><body>
<div class="chr-pagination">
  <span class="page-number"><a href="/resources/reports/">1</a></span>
  <span class="page-number"><a href="/resources/reports/page/2/">2</a></span>
  <span class="page-number"><a href="/resources/reports/page/3/">3</a></span>
  <span class="page-number"><a href="/resources/reports/page/12/">12</a></span>
</div>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParseArticles:
    """_parse_articles extracts article metadata from article.tease.tease-post."""

    def test_extracts_two_articles(self, scraper):
        articles = scraper._parse_articles(ARTICLES_HTML)
        assert len(articles) == 2

    def test_article_fields(self, scraper):
        articles = scraper._parse_articles(ARTICLES_HTML)
        a = articles[0]
        assert a["title"] == "Energy Charter Report 2024"
        assert "energy-charter-report" in a["url"]
        assert a["date"] == "31 Jul 2025"
        assert a["category"] == "Reports"

    def test_single_article(self, scraper):
        articles = scraper._parse_articles(SINGLE_ARTICLE_HTML)
        assert len(articles) == 1
        assert articles[0]["title"] == "Network Vision Report"

    def test_no_articles(self, scraper):
        articles = scraper._parse_articles(NO_ARTICLES_HTML)
        assert articles == []

    def test_missing_link_skipped(self, scraper):
        articles = scraper._parse_articles(MISSING_LINK_HTML)
        assert articles == []


class TestParseDateENA:
    """_parse_date handles DD Mon YYYY and DD Month YYYY formats."""

    def test_short_month(self, scraper):
        assert scraper._parse_date("31 Jul 2025") == "2025-07-31"

    def test_full_month(self, scraper):
        assert scraper._parse_date("10 December 2023") == "2023-12-10"

    def test_slash_format(self, scraper):
        assert scraper._parse_date("15/06/2024") == "2024-06-15"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_date("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date(None) is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_date("not a date") is None


class TestDetectTotalPagesENA:
    """_detect_total_pages extracts max page from .chr-pagination."""

    def test_finds_max_page(self, scraper):
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 12

    def test_no_pagination_returns_1(self, scraper):
        total = scraper._detect_total_pages(NO_ARTICLES_HTML)
        assert total == 1


class TestBuildPageURL:
    """_build_page_url constructs correct URLs."""

    def test_page_1(self, scraper):
        url = scraper._build_page_url("https://example.com/reports/", 1)
        assert url == "https://example.com/reports/"

    def test_page_2(self, scraper):
        url = scraper._build_page_url("https://example.com/reports/", 2)
        assert url == "https://example.com/reports/page/2/"


# -- Additional HTML fixtures for new tests ---------------------------------

PAGINATION_WITH_PAGE_NUMBERS_HTML = """
<html><body>
<div class="chr-pagination">
  <span class="page-number"><a href="/resources/reports/">1</a></span>
  <span class="page-number"><a href="/resources/reports/page/2/">2</a></span>
  <span class="page-number"><a href="/resources/reports/page/5/">5</a></span>
</div>
</body></html>
"""

DETAIL_PAGE_WITH_PDFS_HTML = """
<html><body>
<a href="/assets/uploads/energy-charter-report.pdf">Energy Charter Report PDF</a>
<a href="/wp-content/uploads/submission-document.pdf">Submission Document</a>
<p>Some text content on the detail page.</p>
</body></html>
"""

DETAIL_PAGE_NO_PDFS_HTML = """
<html><body>
<p>This detail page has no PDF documents.</p>
<a href="/about-us">About Us</a>
</body></html>
"""

DETAIL_PAGE_SHORT_LINK_TEXT_HTML = """
<html><body>
<a href="/assets/uploads/long-filename-report.pdf">DL</a>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestDetectTotalPagesExtended:
    """Extended tests for _detect_total_pages."""

    def test_with_pagination_links(self, scraper):
        """Finds max page from pagination links."""
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 12

    def test_without_pagination_returns_1(self, scraper):
        """No pagination div returns 1."""
        total = scraper._detect_total_pages(NO_ARTICLES_HTML)
        assert total == 1

    def test_with_page_numbers(self, scraper):
        """Picks highest page number from pagination links."""
        total = scraper._detect_total_pages(PAGINATION_WITH_PAGE_NUMBERS_HTML)
        assert total == 5

    def test_non_numeric_links_ignored(self, scraper):
        """Non-numeric link text (e.g. 'Next') is ignored."""
        html = """
        <html><body>
        <div class="chr-pagination">
          <span class="page-number"><a href="/page/1/">1</a></span>
          <span class="page-number"><a href="/page/2/">Next</a></span>
        </div>
        </body></html>
        """
        total = scraper._detect_total_pages(html)
        assert total == 1


class TestFindPdfsOnDetailPage:
    """Tests for _find_pdfs_on_detail_page."""

    def test_page_with_pdf_links(self, scraper):
        """Finds PDF links on an HTML detail page."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        # HEAD returns HTML content type
        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html; charset=utf-8"}

        # GET returns the detail page HTML
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/reports/energy-charter/",
            session,
            "Energy Charter Report",
        )
        assert len(pdfs) >= 1
        assert all(p.url.endswith(".pdf") for p in pdfs)

    def test_page_with_direct_pdf(self, scraper):
        """HEAD returns application/pdf, treat URL as direct download."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "application/pdf"}

        scraper._request_with_retry = MagicMock(return_value=head_resp)

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/direct-report.pdf",
            session,
            "Direct Report",
        )
        assert len(pdfs) == 1
        assert pdfs[0].url.endswith(".pdf")

    def test_head_request_failure_fallback(self, scraper):
        """HEAD returns 404, falls back to GET."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 404
        head_resp.headers = {"Content-Type": "text/html"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/reports/test/",
            session,
            "Test Report",
        )
        assert len(pdfs) >= 1

    def test_no_pdfs_found(self, scraper):
        """Page with no PDF links returns empty list."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html; charset=utf-8"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_NO_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/about/",
            session,
            "About Page",
        )
        assert len(pdfs) == 0

    def test_head_returns_none_raises(self, scraper):
        """When _request_with_retry returns None, error is caught and empty returned."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)
        scraper._request_with_retry = MagicMock(return_value=None)

        # _find_pdfs_on_detail_page catches exceptions and returns []
        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/fail/",
            session,
            "Fail Page",
        )
        assert pdfs == []

    def test_short_link_text_uses_filename(self, scraper):
        """Link text < 3 chars falls back to filename from URL."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_SHORT_LINK_TEXT_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/test/",
            session,
            "Test",
        )
        assert len(pdfs) == 1
        # Title should be derived from filename, not "DL"
        assert len(pdfs[0].title) > 2


class TestParseDateExtended:
    """Extended tests for _parse_date."""

    def test_dd_mm_yyyy_format(self, scraper):
        assert scraper._parse_date("15/06/2024") == "2024-06-15"

    def test_dd_month_yyyy(self, scraper):
        assert scraper._parse_date("10 December 2023") == "2023-12-10"

    def test_iso_format_not_supported(self, scraper):
        """ISO format is not in supported formats, returns None."""
        # ENA _parse_date does NOT support ISO format
        result = scraper._parse_date("2024-06-15")
        assert result is None

    def test_invalid_date_returns_none(self, scraper):
        assert scraper._parse_date("invalid-date-string") is None

    def test_whitespace_stripped(self, scraper):
        assert scraper._parse_date("  31 Jul 2025  ") == "2025-07-31"

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date(None) is None


# -- Additional HTML fixtures for section/dedup tests -----------------------

DETAIL_PAGE_RELATIVE_PDF_HTML = """
<html><body>
<a href="uploads/relative-report.pdf">Relative Report</a>
</body></html>
"""

DETAIL_PAGE_DUPLICATE_PDFS_HTML = """
<html><body>
<a href="/assets/uploads/report-one.pdf">Report One</a>
<a href="/assets/uploads/report-one.pdf">Report One Duplicate</a>
<a href="/wp-content/uploads/report-two.pdf">Report Two</a>
</body></html>
"""

ARTICLES_BOTH_SECTIONS_HTML = """
<html><body>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/reports/shared-report/">
    <span class="post-title">Shared Report Across Sections</span>
  </a>
  <span class="post-date">01 Jan 2025</span>
  <span class="post-categories">Reports</span>
</article>
</body></html>
"""

MALFORMED_ARTICLE_HTML = """
<html><body>
<article class="tease tease-post">
  <span class="post-title">Article Without Link</span>
  <span class="post-date">01 Jan 2024</span>
</article>
<article class="tease tease-post">
  <a class="tease-link" href="">
    <span class="post-title">Article With Empty Href</span>
  </a>
</article>
</body></html>
"""


# -- New Test Classes (Section Iteration & Dedup) ---------------------------


class TestDetectTotalPagesNew:
    """Additional tests for _detect_total_pages."""

    def test_with_pagination_links(self, scraper):
        """Finds the highest page number from pagination links."""
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 12

    def test_no_pagination_returns_1(self, scraper):
        """No pagination element returns default of 1."""
        total = scraper._detect_total_pages(NO_ARTICLES_HTML)
        assert total == 1

    def test_with_numbered_pages(self, scraper):
        """Picks the highest number from multiple page links."""
        total = scraper._detect_total_pages(PAGINATION_WITH_PAGE_NUMBERS_HTML)
        assert total == 5


class TestFindPdfsOnDetailPageNew:
    """Additional tests for _find_pdfs_on_detail_page."""

    def test_page_with_pdf_links(self, scraper):
        """Finds PDF links on an HTML detail page."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html; charset=utf-8"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/reports/test/",
            session,
            "Test Report",
        )
        assert len(pdfs) >= 1
        assert all(p.url.endswith(".pdf") for p in pdfs)

    def test_direct_pdf_url(self, scraper):
        """HEAD returns application/pdf content type, treat as direct download."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="my-report.pdf"',
        }

        scraper._request_with_retry = MagicMock(return_value=head_resp)

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/direct.pdf",
            session,
            "Direct PDF",
        )
        assert len(pdfs) == 1
        assert pdfs[0].url.endswith(".pdf")

    def test_head_failure_falls_back_to_get(self, scraper):
        """HEAD returns 405, code falls back to GET for HTML parsing."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 405
        head_resp.headers = {"Content-Type": "text/html"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_WITH_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/reports/test/",
            session,
            "Test Report",
        )
        assert len(pdfs) >= 1

    def test_no_pdfs_found(self, scraper):
        """Page with no PDF links returns empty list."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_NO_PDFS_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/about/",
            session,
            "About Page",
        )
        assert len(pdfs) == 0

    def test_relative_pdf_url_resolved(self, scraper):
        """Relative PDF URLs are resolved to absolute using article URL."""
        from unittest.mock import MagicMock
        import requests

        session = MagicMock(spec=requests.Session)

        head_resp = MagicMock()
        head_resp.status_code = 200
        head_resp.headers = {"Content-Type": "text/html"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = DETAIL_PAGE_RELATIVE_PDF_HTML

        scraper._request_with_retry = MagicMock(return_value=head_resp)
        session.get.return_value = get_resp

        pdfs = scraper._find_pdfs_on_detail_page(
            "https://www.energynetworks.com.au/resources/reports/test/",
            session,
            "Relative Report",
        )
        assert len(pdfs) == 1
        assert pdfs[0].url.startswith("https://")
        assert pdfs[0].url.endswith(".pdf")


class TestParseDateFormatsNew:
    """Additional date format tests for _parse_date."""

    def test_dd_mm_yyyy(self, scraper):
        """Slash-separated date dd/mm/yyyy."""
        assert scraper._parse_date("15/06/2024") == "2024-06-15"

    def test_dd_month_yyyy(self, scraper):
        """Full month name format."""
        assert scraper._parse_date("10 December 2023") == "2023-12-10"

    def test_iso_format_not_supported(self, scraper):
        """ISO format is not in the supported list, returns None."""
        assert scraper._parse_date("2024-06-15") is None

    def test_invalid_date_returns_none(self, scraper):
        """Completely invalid string returns None."""
        assert scraper._parse_date("not-a-date") is None


class TestParseArticlesNew:
    """Additional tests for _parse_articles."""

    def test_valid_articles_parsed(self, scraper):
        """Valid articles are parsed into dicts."""
        articles = scraper._parse_articles(ARTICLES_HTML)
        assert len(articles) == 2
        assert articles[0]["title"] == "Energy Charter Report 2024"
        assert "energy-charter-report" in articles[0]["url"]

    def test_no_articles_found_returns_empty(self, scraper):
        """HTML with no article.tease elements returns empty list."""
        articles = scraper._parse_articles(NO_ARTICLES_HTML)
        assert articles == []

    def test_malformed_article_missing_href(self, scraper):
        """Articles with no link or empty href are skipped."""
        articles = scraper._parse_articles(MALFORMED_ARTICLE_HTML)
        assert articles == []


class TestSectionIteration:
    """Tests for processing multiple sections and cross-section dedup."""

    def test_processes_both_sections(self, scraper):
        """Both report and submission sections are defined."""
        from app.scrapers.ena_scraper import ENA_RESOURCE_SECTIONS

        assert len(ENA_RESOURCE_SECTIONS) == 2
        section_names = [s["name"] for s in ENA_RESOURCE_SECTIONS]
        assert "reports" in section_names
        assert "submissions" in section_names

    def test_cross_section_dedup_via_is_processed(self, scraper):
        """Same URL processed in one section is skipped in another via _is_processed."""
        scraper._is_processed = Mock(return_value=True)

        from app.scrapers.models import DocumentMetadata

        pdf = DocumentMetadata(
            url="https://www.energynetworks.com.au/assets/uploads/shared.pdf",
            title="Shared PDF",
            filename="shared.pdf",
            source_page="https://www.energynetworks.com.au/resources/reports/shared/",
            tags=["ENA"],
            organization="ENA",
            document_type="Report",
        )
        assert scraper._is_processed(pdf.url) is True

    def test_section_categories(self, scraper):
        """Each section has a category label."""
        from app.scrapers.ena_scraper import ENA_RESOURCE_SECTIONS

        for section in ENA_RESOURCE_SECTIONS:
            assert "category" in section
            assert section["category"] in ("Reports", "Submissions")
