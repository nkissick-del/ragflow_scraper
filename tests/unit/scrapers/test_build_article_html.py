"""Unit tests for MetadataIOMixin._build_article_html()."""

from unittest.mock import Mock, patch

import pytest

from app.scrapers.common_mixins import MetadataIOMixin
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def mixin():
    """Create a MetadataIOMixin instance with logger."""
    m = MetadataIOMixin()
    m.logger = Mock()
    m.name = "test_scraper"
    return m


@pytest.fixture
def metadata():
    """Create a DocumentMetadata with typical fields."""
    return DocumentMetadata(
        url="https://example.com/article/1",
        title="Test Article Title",
        filename="test-article",
        publication_date="2026-01-15",
        organization="Test Org",
    )


class TestBuildArticleHtml:
    """Tests for _build_article_html mixin method."""

    def test_basic_wrapping(self, mixin, metadata):
        """Body HTML is wrapped in full document with title."""
        result = mixin._build_article_html("<p>Hello world</p>", metadata)

        assert "<!DOCTYPE html>" in result
        assert "<h1>Test Article Title</h1>" in result
        assert "<p>Hello world</p>" in result
        # article-meta removed — metadata stamp handles date/org now
        assert "article-meta" not in result

    def test_uses_base_url_attribute(self, mixin, metadata):
        """base_url from scraper attribute is passed to build_article_html."""
        mixin.base_url = "https://example.com"
        result = mixin._build_article_html("<p>Test</p>", metadata)

        assert '<base href="https://example.com">' in result

    def test_no_base_url_attribute(self, mixin, metadata):
        """Works without base_url attribute on mixin."""
        # No base_url set — getattr returns ""
        result = mixin._build_article_html("<p>Test</p>", metadata)

        assert "<!DOCTYPE html>" in result
        assert "<base" not in result

    @patch("app.utils.html_utils.inline_images")
    @patch("app.utils.html_utils.build_article_html")
    def test_calls_inline_images_with_session(
        self, mock_build, mock_inline, mixin, metadata
    ):
        """Session from scraper is passed to inline_images."""
        mock_session = Mock()
        mixin._session = mock_session
        mixin.base_url = "https://example.com"

        mock_build.return_value = "<html>built</html>"
        mock_inline.return_value = "<html>inlined</html>"

        result = mixin._build_article_html("<p>Test</p>", metadata)

        mock_inline.assert_called_once_with(
            "<html>built</html>",
            session=mock_session,
            base_url="https://example.com",
        )
        assert result == "<html>inlined</html>"

    @patch("app.utils.html_utils.inline_images")
    @patch("app.utils.html_utils.build_article_html")
    def test_calls_inline_images_without_session(
        self, mock_build, mock_inline, mixin, metadata
    ):
        """None session when scraper has no _session attribute."""
        mock_build.return_value = "<html>built</html>"
        mock_inline.return_value = "<html>inlined</html>"

        mixin._build_article_html("<p>Test</p>", metadata)

        mock_inline.assert_called_once_with(
            "<html>built</html>",
            session=None,
            base_url="",
        )

    @patch("app.utils.html_utils.build_article_html", side_effect=Exception("boom"))
    def test_build_error_returns_original(self, mock_build, mixin, metadata):
        """Build failure returns the original body_html."""
        result = mixin._build_article_html("<p>Original</p>", metadata)

        assert result == "<p>Original</p>"
        mixin.logger.warning.assert_called()

    @patch("app.utils.html_utils.inline_images", side_effect=Exception("network"))
    @patch("app.utils.html_utils.build_article_html", return_value="<html>built</html>")
    def test_inline_error_returns_built_html(
        self, mock_build, mock_inline, mixin, metadata
    ):
        """Inline failure returns the built (but un-inlined) HTML."""
        result = mixin._build_article_html("<p>Test</p>", metadata)

        assert result == "<html>built</html>"
        mixin.logger.warning.assert_called()

    def test_empty_metadata_fields(self, mixin):
        """Handles metadata with None/empty fields gracefully."""
        meta = DocumentMetadata(
            url="",
            title="",
            filename="empty",
        )

        result = mixin._build_article_html("<p>Content</p>", meta)

        assert "<!DOCTYPE html>" in result
        assert "<p>Content</p>" in result
