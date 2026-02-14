"""Tests for clean_article_html() in html_utils."""

from app.utils.html_utils import clean_article_html


class TestCleanArticleHtml:
    """Test universal HTML cleaning."""

    def test_removes_script_tags(self):
        html = '<p>Article</p><script>alert("xss")</script>'
        result = clean_article_html(html)
        assert "<script>" not in result
        assert "Article" in result

    def test_removes_style_tags(self):
        html = "<style>body{color:red}</style><p>Content</p>"
        result = clean_article_html(html)
        assert "<style>" not in result
        assert "Content" in result

    def test_removes_iframe_tags(self):
        html = '<p>Text</p><iframe src="https://ads.example.com"></iframe>'
        result = clean_article_html(html)
        assert "<iframe" not in result
        assert "Text" in result

    def test_removes_noscript_tags(self):
        html = "<noscript>Enable JS</noscript><p>Article</p>"
        result = clean_article_html(html)
        assert "<noscript>" not in result

    def test_removes_linkedin_share(self):
        html = '<p>Article</p><a href="https://linkedin.com/sharing/share?url=x">Share</a>'
        result = clean_article_html(html)
        assert "linkedin.com/sharing" not in result
        assert "Article" in result

    def test_removes_twitter_share(self):
        html = '<a href="https://twitter.com/intent/tweet?text=x">Tweet</a><p>Body</p>'
        result = clean_article_html(html)
        assert "twitter.com/intent" not in result

    def test_removes_x_share(self):
        html = '<a href="https://x.com/intent/post?text=x">Post</a><p>Body</p>'
        result = clean_article_html(html)
        assert "x.com/intent" not in result

    def test_removes_facebook_share(self):
        html = '<a href="https://facebook.com/sharer/sharer.php?u=x">Share</a><p>Body</p>'
        result = clean_article_html(html)
        assert "facebook.com/sharer" not in result

    def test_removes_subscribe_cta(self):
        html = '<a href="/subscribe">Subscribe to our newsletter</a><p>Article</p>'
        result = clean_article_html(html)
        assert "Subscribe" not in result
        assert "Article" in result

    def test_removes_newsletter_class(self):
        html = '<div class="newsletter-signup">Get updates</div><p>Article</p>'
        result = clean_article_html(html)
        assert "newsletter" not in result.lower()
        assert "Article" in result

    def test_removes_signup_class(self):
        html = '<div class="email-signup-form">Sign up</div><p>Content</p>'
        result = clean_article_html(html)
        assert "signup" not in result.lower()
        assert "Content" in result

    def test_removes_share_class(self):
        html = '<div class="share-buttons">Share this</div><p>Article text</p>'
        result = clean_article_html(html)
        assert "share-buttons" not in result
        assert "Article text" in result

    def test_preserves_article_content(self):
        html = (
            "<h1>Title</h1>"
            "<p>Paragraph text with <strong>bold</strong></p>"
            '<img src="photo.jpg">'
            "<blockquote>Quote</blockquote>"
        )
        result = clean_article_html(html)
        assert "<h1>Title</h1>" in result
        assert "Paragraph text" in result
        assert "<strong>bold</strong>" in result
        assert '<img src="photo.jpg"/>' in result or '<img src="photo.jpg">' in result
        assert "Quote" in result

    def test_does_not_remove_share_with_substantial_content(self):
        """Elements with 'share' class but >200 chars of text should be kept."""
        long_text = "A" * 250
        html = f'<div class="share-section"><p>{long_text}</p></div>'
        result = clean_article_html(html)
        assert long_text in result

    def test_extra_removals_selector(self):
        html = '<button class="copy-btn">Copy URL</button><p>Article</p>'
        result = clean_article_html(
            html, extra_removals=[{"selector": "button", "class_contains": "copy-btn"}]
        )
        assert "Copy URL" not in result
        assert "Article" in result

    def test_extra_removals_text_match(self):
        html = '<span>Share</span><span>Article info</span>'
        result = clean_article_html(
            html, extra_removals=[{"selector": "span", "text": "Share"}]
        )
        assert "Share" not in result
        assert "Article info" in result

    def test_extra_removals_parent_levels(self):
        html = '<div><div><span>Share</span></div></div><p>Keep</p>'
        result = clean_article_html(
            html,
            extra_removals=[
                {"selector": "span", "text": "Share", "remove_parent_levels": "2"}
            ],
        )
        assert "Share" not in result
        assert "Keep" in result

    def test_empty_html_returns_empty(self):
        assert clean_article_html("") == ""
        assert clean_article_html("   ") == "   "

    def test_none_returns_none(self):
        result = clean_article_html(None)  # type: ignore[arg-type]
        assert result is None

    def test_plain_text_preserved(self):
        """Non-HTML text should pass through."""
        result = clean_article_html("Just plain text")
        assert "Just plain text" in result

    def test_removes_share_parent_tooltip(self):
        """LinkedIn share link inside tooltip wrapper should remove wrapper."""
        html = (
            '<div class="hs-tooltip">'
            '<a href="https://linkedin.com/sharing/share?url=x">Share</a>'
            "</div><p>Content</p>"
        )
        result = clean_article_html(html)
        assert "hs-tooltip" not in result
        assert "Content" in result
