"""Tests for MetadataIOMixin._enrich_metadata_from_html."""

import pytest
from unittest.mock import MagicMock, patch

from app.scrapers.common_mixins import MetadataIOMixin
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def mixin():
    """Create a MetadataIOMixin instance with a logger."""
    m = MetadataIOMixin()
    m.logger = MagicMock()
    return m


@pytest.fixture
def metadata():
    """Create a basic DocumentMetadata."""
    return DocumentMetadata(
        url="https://example.com/article",
        title="Test Article",
        filename="test-article.html",
        organization="Test Org",
    )


def _article_html(
    author: str = "",
    description: str = "",
    language: str = "",
    image: str = "",
    keywords: str = "",
) -> str:
    """Build HTML with JSON-LD structured data."""
    parts = ['"@type": "Article"']
    if author:
        parts.append(f'"author": "{author}"')
    if description:
        parts.append(f'"description": "{description}"')
    if language:
        parts.append(f'"inLanguage": "{language}"')
    if image:
        parts.append(f'"image": "{image}"')
    if keywords:
        parts.append(f'"keywords": "{keywords}"')

    jsonld = "{" + ", ".join(parts) + "}"
    return (
        f'<html><head><script type="application/ld+json">{jsonld}</script></head>'
        "<body></body></html>"
    )


class TestEnrichMetadataFromHTML:
    """Test _enrich_metadata_from_html fill-gaps behavior."""

    def test_fills_empty_author(self, mixin, metadata):
        """Should set author when metadata.author is None."""
        assert metadata.author is None
        html = _article_html(author="Jane Doe")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.author == "Jane Doe"

    def test_fills_empty_description(self, mixin, metadata):
        """Should set description when metadata.description is None."""
        assert metadata.description is None
        html = _article_html(description="A great article")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.description == "A great article"

    def test_fills_empty_language(self, mixin, metadata):
        """Should set language when metadata.language is None."""
        assert metadata.language is None
        html = _article_html(language="en")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.language == "en"

    def test_fills_empty_image_url(self, mixin, metadata):
        """Should set image_url when metadata.image_url is None."""
        assert metadata.image_url is None
        html = _article_html(image="https://example.com/img.jpg")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.image_url == "https://example.com/img.jpg"

    def test_does_not_overwrite_existing_author(self, mixin, metadata):
        """Should NOT overwrite existing author."""
        metadata.author = "Existing Author"
        html = _article_html(author="New Author")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.author == "Existing Author"

    def test_does_not_overwrite_existing_description(self, mixin, metadata):
        """Should NOT overwrite existing description."""
        metadata.description = "Existing description"
        html = _article_html(description="New description")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.description == "Existing description"

    def test_does_not_overwrite_existing_language(self, mixin, metadata):
        """Should NOT overwrite existing language."""
        metadata.language = "fr"
        html = _article_html(language="en")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.language == "fr"

    def test_does_not_overwrite_existing_image_url(self, mixin, metadata):
        """Should NOT overwrite existing image_url."""
        metadata.image_url = "https://example.com/existing.jpg"
        html = _article_html(image="https://example.com/new.jpg")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.image_url == "https://example.com/existing.jpg"

    def test_merges_keywords_deduped(self, mixin, metadata):
        """Should merge keywords with case-insensitive deduplication."""
        metadata.keywords = ["Solar"]
        html = _article_html(keywords="solar, wind, hydro")
        mixin._enrich_metadata_from_html(html, metadata)
        # "solar" should not be duplicated (case-insensitive)
        assert len(metadata.keywords) == 3
        keyword_lower = [k.lower() for k in metadata.keywords]
        assert "solar" in keyword_lower
        assert "wind" in keyword_lower
        assert "hydro" in keyword_lower

    def test_merges_keywords_when_empty(self, mixin, metadata):
        """Should add keywords when metadata has none."""
        assert metadata.keywords == []
        html = _article_html(keywords="energy, policy")
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.keywords == ["energy", "policy"]

    def test_empty_html_no_change(self, mixin, metadata):
        """Should not modify metadata on empty HTML."""
        original_author = metadata.author
        mixin._enrich_metadata_from_html("", metadata)
        assert metadata.author == original_author

    def test_no_structured_data_no_change(self, mixin, metadata):
        """Should not modify metadata when HTML has no structured data."""
        html = "<html><head><title>No data</title></head><body>Plain</body></html>"
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.author is None
        assert metadata.description is None

    def test_error_handling_nonfatal(self, mixin, metadata):
        """Should handle extraction errors gracefully."""
        with patch(
            "app.utils.metadata_extractor.extract_structured_metadata",
            side_effect=Exception("parse error"),
        ):
            # Should not raise
            mixin._enrich_metadata_from_html("<html></html>", metadata)

        mixin.logger.debug.assert_called()

    def test_fills_publication_date(self, mixin, metadata):
        """Should fill publication_date when not set."""
        metadata.publication_date = None
        html = (
            '<html><head><script type="application/ld+json">'
            '{"@type": "Article", "datePublished": "2025-06-15T10:00:00+10:00"}'
            "</script></head><body></body></html>"
        )
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.publication_date == "2025-06-15"

    def test_does_not_overwrite_existing_publication_date(self, mixin, metadata):
        """Should NOT overwrite existing publication_date."""
        metadata.publication_date = "2024-01-01"
        html = (
            '<html><head><script type="application/ld+json">'
            '{"@type": "Article", "datePublished": "2025-06-15T10:00:00+10:00"}'
            "</script></head><body></body></html>"
        )
        mixin._enrich_metadata_from_html(html, metadata)
        assert metadata.publication_date == "2024-01-01"
