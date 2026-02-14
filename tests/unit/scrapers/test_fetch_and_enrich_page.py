"""Tests for MetadataIOMixin._fetch_and_enrich_page()."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from app.scrapers.common_mixins import MetadataIOMixin
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def mixin():
    """Create a MetadataIOMixin instance with logger."""
    m = MetadataIOMixin()
    m.logger = Mock()
    return m


@pytest.fixture
def metadata():
    """Create a minimal DocumentMetadata."""
    return DocumentMetadata(
        url="https://example.com/article",
        title="Test Article",
        filename="test-article.html",
    )


SAMPLE_HTML = "<html><head><title>Test</title></head><body>Content</body></html>"


class TestFetchAndEnrichPage:
    def test_success(self, mixin, metadata):
        """Mock _session.get() returns HTML, verify _enrich called and HTML returned."""
        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.text = SAMPLE_HTML

        mock_session = Mock()
        mock_session.get.return_value = mock_resp
        mixin._session = mock_session

        with patch.object(mixin, "_enrich_metadata_from_html") as mock_enrich:
            result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)

        assert result == SAMPLE_HTML
        mock_session.get.assert_called_once_with("https://example.com/article", timeout=30)
        mock_enrich.assert_called_once_with(SAMPLE_HTML, metadata)

    def test_no_session(self, mixin, metadata):
        """_session is None, returns None, no crash."""
        # No _session attribute at all
        result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)

        assert result is None

    def test_http_error(self, mixin, metadata):
        """page_resp.ok is False, returns None."""
        mock_resp = Mock()
        mock_resp.ok = False

        mock_session = Mock()
        mock_session.get.return_value = mock_resp
        mixin._session = mock_session

        with patch.object(mixin, "_enrich_metadata_from_html") as mock_enrich:
            result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)

        assert result is None
        mock_enrich.assert_not_called()

    def test_exception(self, mixin, metadata):
        """_session.get() raises, returns None, logs debug."""
        mock_session = Mock()
        mock_session.get.side_effect = ConnectionError("timeout")
        mixin._session = mock_session

        result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)

        assert result is None
        mixin.logger.debug.assert_called_once()
        assert "Page metadata extraction failed" in mixin.logger.debug.call_args[0][0]

    def test_returns_html(self, mixin, metadata):
        """Verify HTML string is returned for reuse."""
        custom_html = "<html><body><article>Full article content here</article></body></html>"
        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.text = custom_html

        mock_session = Mock()
        mock_session.get.return_value = mock_resp
        mixin._session = mock_session

        with patch.object(mixin, "_enrich_metadata_from_html"):
            result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)

        assert result == custom_html

    def test_no_logger(self, metadata):
        """Exception with logger=None does not crash."""
        mixin = MetadataIOMixin()
        mixin.logger = None

        mock_session = Mock()
        mock_session.get.side_effect = RuntimeError("fail")
        mixin._session = mock_session

        result = mixin._fetch_and_enrich_page("https://example.com/article", metadata)
        assert result is None
