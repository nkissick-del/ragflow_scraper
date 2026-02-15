"""Unit tests for app.utils.html_utils — build_article_html, inline_images, inject_metadata_stamp."""

from unittest.mock import Mock, patch

from app.utils.html_utils import (
    _strip_duplicate_title,
    build_article_html,
    inline_images,
    inject_metadata_stamp,
)


# ── build_article_html ──────────────────────────────────────────────────


class TestBuildArticleHtml:
    """Tests for build_article_html()."""

    def test_complete_fields(self):
        """All metadata fields produce correct HTML structure."""
        html = build_article_html(
            body_html="<p>Article body</p>",
            title="Test Title",
            base_url="https://example.com",
        )

        assert "<!DOCTYPE html>" in html
        assert "<h1>Test Title</h1>" in html
        assert '<base href="https://example.com">' in html
        assert "<p>Article body</p>" in html
        # article-meta removed — metadata stamp handles it now
        assert "article-meta" not in html

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

    def test_no_article_meta_rendered(self):
        """article-meta div is no longer generated (replaced by metadata stamp)."""
        html = build_article_html(
            body_html="<p>Test</p>",
            date="2026-01-01",
            organization="Org",
            source_url="https://example.com",
        )
        assert "article-meta" not in html
        assert "&middot;" not in html

    def test_strips_duplicate_title_from_body(self):
        """Leading <h1> matching the title is removed from body."""
        html = build_article_html(
            body_html="<h1>My Title</h1><p>Content</p>",
            title="My Title",
        )
        # Should have exactly one h1
        assert html.count("<h1>") == 1
        assert "<h1>My Title</h1>" in html
        assert "<p>Content</p>" in html

    def test_keeps_non_matching_h1(self):
        """Leading <h1> with different text is preserved."""
        html = build_article_html(
            body_html="<h1>Different Heading</h1><p>Content</p>",
            title="Article Title",
        )
        # Both should be present
        assert "<h1>Article Title</h1>" in html
        assert "Different Heading" in html


# ── _strip_duplicate_title ─────────────────────────────────────────────


class TestStripDuplicateTitle:
    """Tests for _strip_duplicate_title()."""

    def test_exact_match(self):
        """Matching h1 is stripped."""
        result = _strip_duplicate_title("<h1>My Title</h1><p>Body</p>", "My Title")
        assert "<h1>" not in result
        assert "<p>Body</p>" in result

    def test_case_insensitive(self):
        """Match is case-insensitive."""
        result = _strip_duplicate_title("<h1>my title</h1><p>Body</p>", "My Title")
        assert "<h1>" not in result

    def test_no_match_preserved(self):
        """Non-matching h1 is left intact."""
        body = "<h1>Other Heading</h1><p>Body</p>"
        result = _strip_duplicate_title(body, "My Title")
        assert result == body

    def test_h1_with_attributes(self):
        """h1 with class/id attributes is still matched."""
        result = _strip_duplicate_title(
            '<h1 class="entry-title">My Title</h1><p>Body</p>', "My Title"
        )
        assert "<h1" not in result

    def test_h1_with_inner_tags(self):
        """h1 containing inline tags (e.g. <a>, <span>) is matched on text."""
        result = _strip_duplicate_title(
            '<h1><a href="#">My Title</a></h1><p>Body</p>', "My Title"
        )
        assert "<h1>" not in result

    def test_empty_title_noop(self):
        """Empty title skips stripping."""
        body = "<h1>Something</h1><p>Body</p>"
        assert _strip_duplicate_title(body, "") == body

    def test_empty_body_noop(self):
        """Empty body returns empty string."""
        assert _strip_duplicate_title("", "Title") == ""

    def test_non_leading_h1_ignored(self):
        """h1 that is NOT the first element is not stripped."""
        body = "<p>Intro</p><h1>My Title</h1><p>Body</p>"
        assert _strip_duplicate_title(body, "My Title") == body

    def test_whitespace_before_h1(self):
        """Leading whitespace before h1 is handled."""
        result = _strip_duplicate_title("  \n<h1>My Title</h1><p>Body</p>", "My Title")
        assert "<h1>" not in result


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


# ── inject_metadata_stamp ──────────────────────────────────────────────


class TestInjectMetadataStamp:
    """Tests for inject_metadata_stamp()."""

    MINIMAL_HTML = "<html><body><p>Content</p></body></html>"

    def test_all_fields(self):
        """All core fields render in the stamp."""
        result = inject_metadata_stamp(
            self.MINIMAL_HTML,
            author="Jane Doe",
            date="2026-02-15",
            organization="AEMO",
            document_type="Article",
            tags=["energy", "climate"],
            source_url="https://example.com/article",
        )
        assert 'class="metadata-stamp"' in result
        assert "Jane Doe" in result
        assert "2026-02-15" in result
        assert "AEMO" in result
        assert "Article" in result
        assert "<span>energy</span>" in result
        assert "<span>climate</span>" in result
        assert "https://example.com/article" in result

    def test_no_fields_returns_original(self):
        """Empty metadata produces no stamp."""
        result = inject_metadata_stamp(self.MINIMAL_HTML)
        assert result == self.MINIMAL_HTML

    def test_partial_fields(self):
        """Only provided fields appear in the stamp."""
        result = inject_metadata_stamp(
            self.MINIMAL_HTML,
            author="John",
            date="2026-01-01",
        )
        assert "John" in result
        assert "2026-01-01" in result
        assert "Organisation" not in result
        assert "Tags" not in result

    def test_stamp_before_content(self):
        """Stamp is inserted after <body>, before article content."""
        result = inject_metadata_stamp(
            self.MINIMAL_HTML,
            author="Test",
        )
        body_pos = result.index("<body>")
        stamp_pos = result.index("metadata-stamp")
        content_pos = result.index("<p>Content</p>")
        assert body_pos < stamp_pos < content_pos

    def test_html_escaping(self):
        """Special characters in metadata values are HTML-escaped."""
        result = inject_metadata_stamp(
            self.MINIMAL_HTML,
            author='O\'Brien & "Partners"',
            organization="Org <script>alert(1)</script>",
        )
        assert "&amp;" in result
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_no_body_tag_returns_original(self):
        """HTML without <body> is returned unchanged."""
        no_body = "<div>No body tag</div>"
        result = inject_metadata_stamp(no_body, author="Test")
        assert result == no_body

    def test_empty_tags_list_omitted(self):
        """Empty tags list does not render a Tags row."""
        result = inject_metadata_stamp(
            self.MINIMAL_HTML,
            author="Test",
            tags=[],
        )
        assert "Tags" not in result

    def test_stamp_heading(self):
        """Stamp contains the Document Metadata heading."""
        result = inject_metadata_stamp(self.MINIMAL_HTML, author="X")
        assert "Document Metadata" in result

    def test_works_with_build_article_html(self):
        """Stamp integrates with build_article_html output."""
        html = build_article_html(
            body_html="<p>Article body</p>",
            title="Test Title",
            date="2026-02-15",
        )
        result = inject_metadata_stamp(
            html,
            author="Author Name",
            date="2026-02-15",
            tags=["policy"],
        )
        assert "metadata-stamp" in result
        assert "Author Name" in result
        assert "<h1>Test Title</h1>" in result
