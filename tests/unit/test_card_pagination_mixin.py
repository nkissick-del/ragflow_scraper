"""Unit tests for CardListPaginationMixin."""

from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.card_pagination_mixin import CardListPaginationMixin
from app.utils.errors import ScraperError


def _make_mixin():
    """Create a mixin instance with a mock logger and driver."""
    mixin = CardListPaginationMixin()
    mixin.logger = MagicMock()
    mixin.driver = None
    return mixin


class TestParseDateDmy:
    def test_valid_date(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("24 December 2025") == "2025-12-24"

    def test_valid_date_single_digit_day(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("3 January 2020") == "2020-01-03"

    def test_empty_string(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("") is None

    def test_none_returns_none(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("") is None

    def test_invalid_format(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("2025-12-24") is None

    def test_whitespace_stripped(self):
        mixin = _make_mixin()
        assert mixin._parse_date_dmy("  15 March 2024  ") == "2024-03-15"


class TestFindDocumentsOnDetailPage:
    def test_no_driver_returns_empty(self):
        mixin = _make_mixin()
        mixin.driver = None
        result = mixin._find_documents_on_detail_page("http://example.com/page")
        assert result == []

    def test_finds_pdf_by_extension(self):
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '<html><body><a href="/files/report.pdf">Download</a></body></html>'
        mock_driver.page_source = html
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )
        assert len(result) == 1
        assert result[0] == "http://example.com/files/report.pdf"

    def test_finds_multiple_extensions(self):
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/files/report.pdf">PDF</a>
            <a href="/files/data.xlsx">Excel</a>
            <a href="/files/memo.docx">Word</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf", ".xlsx", ".docx"),
        )
        assert len(result) == 3

    def test_deduplicates_urls(self):
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/files/report.pdf">Link 1</a>
            <a href="/files/report.pdf">Link 2</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )
        assert len(result) == 1

    def test_path_patterns(self):
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '<html><body><a href="/sites/default/files/doc.pdf">Doc</a></body></html>'
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
            path_patterns=["/sites/default/files/"],
        )
        assert len(result) == 1

    def test_exception_returns_empty(self):
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mock_driver.get.side_effect = Exception("Connection error")
        mixin.driver = mock_driver

        result = mixin._find_documents_on_detail_page("http://example.com/page")
        assert result == []


# ---------------------------------------------------------------------------
# HTTP session fallback tests
# ---------------------------------------------------------------------------


class TestFindDocumentsHttpSessionFallback:
    """Test _find_documents_on_detail_page() HTTP session fallback branch."""

    def test_http_session_fallback_finds_pdfs(self):
        """When no FlareSolverr and no driver, should use _session."""
        mixin = _make_mixin()
        mixin.driver = None

        html = '<html><body><a href="/files/report.pdf">Download</a></body></html>'
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mixin._session = mock_session

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert len(result) == 1
        assert result[0] == "http://example.com/files/report.pdf"
        mock_session.get.assert_called_once_with("http://example.com/page", timeout=30)

    def test_http_session_error_returns_empty(self):
        """HTTP session exception should return empty list."""
        mixin = _make_mixin()
        mixin.driver = None

        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection refused")
        mixin._session = mock_session

        result = mixin._find_documents_on_detail_page("http://example.com/page")

        assert result == []
        mixin.logger.warning.assert_called()

    def test_no_driver_no_session_no_flaresolverr_returns_empty(self):
        """No fetch method at all should return empty list (ScraperError caught)."""
        mixin = _make_mixin()
        mixin.driver = None
        # Ensure no _session and no fetch_rendered_page
        assert not hasattr(mixin, "_session") or mixin._session is None

        result = mixin._find_documents_on_detail_page("http://example.com/page")

        assert result == []


# ---------------------------------------------------------------------------
# FlareSolverr path tests
# ---------------------------------------------------------------------------


class TestFindDocumentsFlareSolverr:
    """Test _find_documents_on_detail_page() FlareSolverr path."""

    def test_flaresolverr_finds_pdfs(self):
        """Should use fetch_rendered_page when available and no driver."""
        mixin = _make_mixin()
        mixin.driver = None

        html = '<html><body><a href="/files/report.pdf">PDF</a></body></html>'
        mixin.fetch_rendered_page = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert len(result) == 1
        assert result[0] == "http://example.com/files/report.pdf"
        mixin.fetch_rendered_page.assert_called_once_with("http://example.com/page")

    def test_flaresolverr_empty_response(self):
        """Should return empty when FlareSolverr returns empty string."""
        mixin = _make_mixin()
        mixin.driver = None
        mixin.fetch_rendered_page = MagicMock(return_value="")

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert result == []
        mixin.logger.warning.assert_called()

    def test_flaresolverr_skipped_when_driver_present(self):
        """Should NOT use FlareSolverr when driver is present."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '<html><body><a href="/files/report.pdf">PDF</a></body></html>'
        mixin.fetch_rendered_page = MagicMock(return_value="<html>FS page</html>")
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        # Should use driver, not FlareSolverr
        mock_driver.get.assert_called_once_with("http://example.com/page")
        mixin.fetch_rendered_page.assert_not_called()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Empty / no-documents detail page tests
# ---------------------------------------------------------------------------


class TestFindDocumentsEmptyResults:
    """Test detail pages that return no documents."""

    def test_no_matching_links(self):
        """Page with links but no matching extensions should return empty."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/page/about">About</a>
            <a href="/page/contact">Contact</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert result == []

    def test_empty_page_no_links(self):
        """Page with no links at all should return empty."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = "<html><body><p>No documents here.</p></body></html>"
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert result == []

    def test_link_with_empty_href(self):
        """Links with empty href should be skipped."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '<html><body><a href="">Empty</a></body></html>'
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert result == []


# ---------------------------------------------------------------------------
# Extension filtering tests
# ---------------------------------------------------------------------------


class TestFindDocumentsExtensionFiltering:
    """Test document URL filtering by file extension."""

    def test_filters_only_pdf(self):
        """When extensions=('.pdf',), should only find PDF links."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/files/report.pdf">PDF</a>
            <a href="/files/data.xlsx">Excel</a>
            <a href="/files/notes.docx">Word</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert len(result) == 1
        assert result[0].endswith(".pdf")

    def test_filters_docx_and_doc(self):
        """Should find .docx and .doc files when requested."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/files/report.pdf">PDF</a>
            <a href="/files/memo.docx">Word New</a>
            <a href="/files/old_memo.doc">Word Old</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".docx", ".doc"),
        )

        assert len(result) == 2
        urls_str = " ".join(result)
        assert ".docx" in urls_str
        assert ".doc" in urls_str

    def test_extension_matching_case_insensitive(self):
        """Extension matching should be case-insensitive."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '<html><body><a href="/files/REPORT.PDF">PDF</a></body></html>'
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
        )

        assert len(result) == 1

    def test_link_selectors_only_match_requested_extensions(self):
        """Custom CSS selectors should still respect extension filtering."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <div class="docs">
                <a href="/files/report.pdf">PDF</a>
                <a href="/page/info">Info Page</a>
            </div>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
            link_selectors=[".docs a"],
        )

        # Only the PDF should be returned (info page doesn't end with .pdf)
        pdf_urls = [u for u in result if u.endswith(".pdf")]
        assert len(pdf_urls) >= 1

    def test_path_patterns_with_non_matching_extension(self):
        """Path pattern matches but wrong extension should be filtered out."""
        mixin = _make_mixin()
        mock_driver = MagicMock()
        mixin.driver = mock_driver

        html = '''<html><body>
            <a href="/sites/default/files/image.png">Image</a>
            <a href="/sites/default/files/doc.pdf">PDF</a>
        </body></html>'''
        mixin.get_page_source = MagicMock(return_value=html)

        result = mixin._find_documents_on_detail_page(
            "http://example.com/page",
            extensions=(".pdf",),
            path_patterns=["/sites/default/files/"],
        )

        # Only PDF should appear, not PNG
        assert len(result) == 1
        assert result[0].endswith(".pdf")
