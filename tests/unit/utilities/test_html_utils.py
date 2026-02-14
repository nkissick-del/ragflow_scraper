"""Unit tests for app.utils.html_utils — build_article_html and inline_images."""

from unittest.mock import Mock, patch

from app.utils.html_utils import build_article_html, inline_images


# ── build_article_html ──────────────────────────────────────────────────


class TestBuildArticleHtml:
    """Tests for build_article_html()."""

    def test_complete_fields(self):
        """All metadata fields produce correct HTML structure."""
        html = build_article_html(
            body_html="<p>Article body</p>",
            title="Test Title",
            date="2026-01-15",
            organization="Test Org",
            source_url="https://example.com/article",
            base_url="https://example.com",
        )

        assert "<!DOCTYPE html>" in html
        assert "<h1>Test Title</h1>" in html
        assert "2026-01-15" in html
        assert "Test Org" in html
        assert 'href="https://example.com/article"' in html
        assert "Original article" in html
        assert '<base href="https://example.com">' in html
        assert "<p>Article body</p>" in html

    def test_minimal_fields(self):
        """Only body_html provided — no title/meta header, still valid HTML."""
        html = build_article_html(body_html="<p>Just content</p>")

        assert "<!DOCTYPE html>" in html
        assert "<p>Just content</p>" in html
        # No title element content
        assert "<title></title>" in html
        # No h1 since title is empty
        assert "<h1>" not in html

    def test_html_escaping(self):
        """Special characters in metadata are escaped."""
        html = build_article_html(
            body_html="<p>Body</p>",
            title='Title with "quotes" & <brackets>',
            organization="Org & Co.",
        )

        assert "&quot;" in html or "&#34;" in html
        assert "&amp;" in html
        assert "&lt;" in html

    def test_base_tag_present(self):
        """base_url produces a <base> tag."""
        html = build_article_html(
            body_html="<p>Test</p>",
            base_url="https://cdn.example.com",
        )
        assert '<base href="https://cdn.example.com">' in html

    def test_base_tag_absent_when_empty(self):
        """No <base> tag when base_url is empty."""
        html = build_article_html(body_html="<p>Test</p>", base_url="")
        assert "<base" not in html

    def test_css_present(self):
        """Article CSS is included in <style> tag."""
        html = build_article_html(body_html="<p>Test</p>")
        assert "<style>" in html
        assert "font-family" in html
        assert "max-width: 800px" in html

    def test_metadata_header_with_all_parts(self):
        """Date, org, and source link joined by middot."""
        html = build_article_html(
            body_html="<p>Test</p>",
            date="2026-01-01",
            organization="Org",
            source_url="https://example.com",
        )
        assert "article-meta" in html
        assert "&middot;" in html

    def test_metadata_header_single_field(self):
        """Single metadata field renders without separators."""
        html = build_article_html(
            body_html="<p>Test</p>",
            date="2026-01-01",
        )
        assert "article-meta" in html
        assert "2026-01-01" in html
        assert "&middot;" not in html


# ── inline_images ───────────────────────────────────────────────────────


class TestInlineImages:
    """Tests for inline_images()."""

    def test_successful_download(self):
        """Image is downloaded and replaced with base64 data URI."""
        html = '<img src="https://example.com/photo.jpg">'
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.content = b"\xff\xd8\xff\xe0test-jpeg-data"
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.raise_for_status = Mock()
        mock_session.get.return_value = mock_resp

        result = inline_images(html, session=mock_session)

        assert "data:image/jpeg;base64," in result
        mock_session.get.assert_called_once_with(
            "https://example.com/photo.jpg", timeout=15
        )

    def test_skip_data_uris(self):
        """Already-inlined data: URIs are not re-processed."""
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        html = f'<img src="{data_uri}">'
        mock_session = Mock()

        result = inline_images(html, session=mock_session)

        mock_session.get.assert_not_called()
        assert data_uri in result

    def test_relative_url_resolution(self):
        """Relative src is resolved against base_url."""
        html = '<img src="/images/photo.png">'
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.content = b"png-data"
        mock_resp.headers = {"Content-Type": "image/png"}
        mock_resp.raise_for_status = Mock()
        mock_session.get.return_value = mock_resp

        inline_images(html, session=mock_session, base_url="https://example.com")

        mock_session.get.assert_called_once_with(
            "https://example.com/images/photo.png", timeout=15
        )

    def test_404_handling(self):
        """HTTP error logs warning but doesn't raise."""
        html = '<img src="https://example.com/missing.jpg"><p>Text</p>'
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_session.get.return_value = mock_resp

        result = inline_images(html, session=mock_session)

        # Original src should remain (not converted)
        assert "https://example.com/missing.jpg" in result
        assert "<p>Text</p>" in result

    def test_size_limit(self):
        """Images exceeding max_size are skipped."""
        html = '<img src="https://example.com/huge.jpg">'
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.content = b"x" * 100  # 100 bytes
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.raise_for_status = Mock()
        mock_session.get.return_value = mock_resp

        result = inline_images(html, session=mock_session, max_size=50)

        # Image src should remain unchanged (too large)
        assert "https://example.com/huge.jpg" in result

    def test_mime_detection_from_extension(self):
        """MIME type is guessed from file extension when Content-Type is missing."""
        html = '<img src="https://example.com/photo.webp">'
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.content = b"webp-data"
        mock_resp.headers = {"Content-Type": ""}
        mock_resp.raise_for_status = Mock()
        mock_session.get.return_value = mock_resp

        result = inline_images(html, session=mock_session)

        assert "data:image/webp;base64," in result

    def test_non_image_tags_untouched(self):
        """Non-<img> elements are not affected."""
        html = '<p>Hello</p><a href="https://example.com">Link</a>'
        result = inline_images(html)
        assert "<p>Hello</p>" in result
        assert "Link" in result

    def test_no_images_returns_original(self):
        """HTML without images returns the original string."""
        html = "<p>No images here</p>"
        result = inline_images(html)
        assert result == html

    def test_no_session_uses_requests(self):
        """When session is None, uses requests.get directly."""
        html = '<img src="https://example.com/photo.jpg">'

        with patch("app.utils.html_utils.requests") as mock_requests:
            mock_resp = Mock()
            mock_resp.content = b"image-data"
            mock_resp.headers = {"Content-Type": "image/jpeg"}
            mock_resp.raise_for_status = Mock()
            mock_requests.get.return_value = mock_resp

            result = inline_images(html, session=None)

            mock_requests.get.assert_called_once()
            assert "data:image/jpeg;base64," in result

    def test_multiple_images(self):
        """Multiple images are all processed."""
        html = (
            '<img src="https://example.com/a.jpg">'
            '<img src="https://example.com/b.png">'
        )
        mock_session = Mock()
        mock_resp = Mock()
        mock_resp.content = b"image-data"
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.raise_for_status = Mock()
        mock_session.get.return_value = mock_resp

        result = inline_images(html, session=mock_session)

        assert mock_session.get.call_count == 2
        assert result.count("data:image/jpeg;base64,") == 2
