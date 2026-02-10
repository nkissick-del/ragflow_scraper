"""Unit tests for CardListPaginationMixin."""

from unittest.mock import MagicMock

from app.scrapers.card_pagination_mixin import CardListPaginationMixin


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
