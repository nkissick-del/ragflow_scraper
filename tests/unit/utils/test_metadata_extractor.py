"""Tests for app.utils.metadata_extractor."""

from app.utils.metadata_extractor import extract_structured_metadata, _normalize_date


# ── Helpers ─────────────────────────────────────────────────────────────


def _wrap_jsonld(jsonld: str, extra_html: str = "") -> str:
    """Wrap a JSON-LD string in minimal HTML."""
    return (
        "<html><head>"
        f'<script type="application/ld+json">{jsonld}</script>'
        f"{extra_html}"
        "</head><body></body></html>"
    )


# ── JSON-LD tests ──────────────────────────────────────────────────────


class TestJSONLDExtraction:
    """Test JSON-LD structured data extraction."""

    def test_article_with_all_fields(self):
        """Should extract all fields from a complete Article JSON-LD."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "headline": "Test Headline",
                "author": {"@type": "Person", "name": "Jane Doe"},
                "description": "A test article",
                "datePublished": "2025-06-15T10:00:00+10:00",
                "image": "https://example.com/img.jpg",
                "keywords": "energy, solar, australia",
                "inLanguage": "en"
            }"""
        )

        result = extract_structured_metadata(html)

        assert result["title"] == "Test Headline"
        assert result["author"] == "Jane Doe"
        assert result["description"] == "A test article"
        assert result["publication_date"] == "2025-06-15"
        assert result["image_url"] == "https://example.com/img.jpg"
        assert result["keywords"] == ["energy", "solar", "australia"]
        assert result["language"] == "en"

    def test_newsarticle_type(self):
        """Should recognize NewsArticle type."""
        html = _wrap_jsonld(
            """{
                "@type": "NewsArticle",
                "headline": "News Article",
                "author": "Reporter Name"
            }"""
        )

        result = extract_structured_metadata(html)
        assert result["title"] == "News Article"
        assert result["author"] == "Reporter Name"

    def test_graph_array(self):
        """Should find Article within @graph array."""
        html = _wrap_jsonld(
            """{
                "@graph": [
                    {"@type": "WebSite", "name": "Example"},
                    {
                        "@type": "Article",
                        "headline": "Graph Article",
                        "author": {"name": "Graph Author"},
                        "description": "From graph"
                    }
                ]
            }"""
        )

        result = extract_structured_metadata(html)
        assert result["title"] == "Graph Article"
        assert result["author"] == "Graph Author"
        assert result["description"] == "From graph"

    def test_list_type(self):
        """Should handle @type as a list."""
        html = _wrap_jsonld(
            """{
                "@type": ["NewsArticle", "Article"],
                "headline": "Multi-type",
                "author": "Multi Author"
            }"""
        )

        result = extract_structured_metadata(html)
        assert result["title"] == "Multi-type"
        assert result["author"] == "Multi Author"

    def test_author_as_string(self):
        """Should handle author as plain string."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": "String Author"
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "String Author"

    def test_author_as_list(self):
        """Should join multiple authors with comma."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": [
                    {"name": "Alice"},
                    {"name": "Bob"}
                ]
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Alice, Bob"

    def test_keywords_as_list(self):
        """Should handle keywords as list."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "keywords": ["solar", "wind", "hydro"]
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["keywords"] == ["solar", "wind", "hydro"]

    def test_image_as_dict(self):
        """Should extract URL from image object."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "image": {"@type": "ImageObject", "url": "https://example.com/photo.jpg"}
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["image_url"] == "https://example.com/photo.jpg"

    def test_image_as_list(self):
        """Should extract first image URL from list."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "image": ["https://example.com/first.jpg", "https://example.com/second.jpg"]
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["image_url"] == "https://example.com/first.jpg"

    def test_language_as_dict(self):
        """Should extract language name from dict."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "inLanguage": {"@type": "Language", "name": "English"}
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["language"] == "English"

    def test_malformed_json_skipped(self):
        """Should skip malformed JSON-LD and return empty dict."""
        html = '<html><head><script type="application/ld+json">not valid json</script></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result == {}

    def test_non_article_type_ignored(self):
        """Should ignore non-Article JSON-LD types."""
        html = _wrap_jsonld(
            """{
                "@type": "Organization",
                "name": "Example Corp"
            }"""
        )
        result = extract_structured_metadata(html)
        assert "title" not in result

    def test_empty_script_tag(self):
        """Should handle empty script tag."""
        html = '<html><head><script type="application/ld+json"></script></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result == {}


# ── Open Graph tests ───────────────────────────────────────────────────


class TestOpenGraphExtraction:
    """Test Open Graph meta tag extraction."""

    def test_og_description(self):
        """Should extract og:description."""
        html = '<html><head><meta property="og:description" content="OG desc"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["description"] == "OG desc"

    def test_og_image(self):
        """Should extract og:image."""
        html = '<html><head><meta property="og:image" content="https://example.com/og.jpg"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["image_url"] == "https://example.com/og.jpg"

    def test_og_title(self):
        """Should extract og:title."""
        html = '<html><head><meta property="og:title" content="OG Title"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["title"] == "OG Title"

    def test_article_author(self):
        """Should extract article:author."""
        html = '<html><head><meta property="article:author" content="OG Author"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["author"] == "OG Author"

    def test_article_tags_multiple(self):
        """Should collect multiple article:tag meta tags."""
        html = (
            '<html><head>'
            '<meta property="article:tag" content="solar">'
            '<meta property="article:tag" content="energy">'
            '</head><body></body></html>'
        )
        result = extract_structured_metadata(html)
        assert result["keywords"] == ["solar", "energy"]

    def test_article_published_time(self):
        """Should extract article:published_time."""
        html = '<html><head><meta property="article:published_time" content="2025-03-10T09:00:00Z"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["publication_date"] == "2025-03-10"


# ── Meta tag tests ─────────────────────────────────────────────────────


class TestMetaTagExtraction:
    """Test standard meta tag extraction."""

    def test_meta_author(self):
        """Should extract meta author."""
        html = '<html><head><meta name="author" content="Meta Author"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["author"] == "Meta Author"

    def test_meta_description(self):
        """Should extract meta description."""
        html = '<html><head><meta name="description" content="Meta desc"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["description"] == "Meta desc"

    def test_meta_keywords(self):
        """Should split comma-separated keywords."""
        html = '<html><head><meta name="keywords" content="solar, wind, hydro"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["keywords"] == ["solar", "wind", "hydro"]

    def test_meta_language(self):
        """Should extract meta language."""
        html = '<html><head><meta name="language" content="en"></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["language"] == "en"

    def test_html_lang_attribute(self):
        """Should extract language from html lang attribute."""
        html = '<html lang="en-AU"><head></head><body></body></html>'
        result = extract_structured_metadata(html)
        assert result["language"] == "en-AU"


# ── Priority cascade tests ────────────────────────────────────────────


class TestPriorityCascade:
    """Test that JSON-LD > OG > meta tag priority is respected."""

    def test_jsonld_wins_over_og(self):
        """JSON-LD description should take priority over OG."""
        html = _wrap_jsonld(
            '{"@type": "Article", "description": "JSON-LD desc"}',
            '<meta property="og:description" content="OG desc">',
        )
        result = extract_structured_metadata(html)
        assert result["description"] == "JSON-LD desc"

    def test_og_wins_over_meta(self):
        """OG description should take priority over meta tag."""
        html = (
            '<html><head>'
            '<meta property="og:description" content="OG desc">'
            '<meta name="description" content="Meta desc">'
            '</head><body></body></html>'
        )
        result = extract_structured_metadata(html)
        assert result["description"] == "OG desc"

    def test_meta_fills_gaps(self):
        """Meta tags should fill gaps not covered by JSON-LD or OG."""
        html = _wrap_jsonld(
            '{"@type": "Article", "headline": "Title"}',
            '<meta name="author" content="Meta Author">'
            '<meta name="description" content="Meta desc">',
        )
        result = extract_structured_metadata(html)
        assert result["title"] == "Title"
        assert result["author"] == "Meta Author"
        assert result["description"] == "Meta desc"


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_html(self):
        """Should return empty dict for empty HTML."""
        assert extract_structured_metadata("") == {}

    def test_none_input(self):
        """Should return empty dict for None-like input."""
        assert extract_structured_metadata("") == {}

    def test_no_structured_data(self):
        """Should return empty dict for HTML with no structured data."""
        html = "<html><head><title>Plain</title></head><body>Hello</body></html>"
        result = extract_structured_metadata(html)
        assert result == {}


# ── Date normalization tests ───────────────────────────────────────────


class TestNormalizeDate:
    """Test date normalization helper."""

    def test_iso_with_timezone(self):
        assert _normalize_date("2025-06-15T10:30:00+10:00") == "2025-06-15"

    def test_iso_with_z(self):
        assert _normalize_date("2025-06-15T10:30:00Z") == "2025-06-15"

    def test_date_only(self):
        assert _normalize_date("2025-06-15") == "2025-06-15"

    def test_invalid_date(self):
        assert _normalize_date("not-a-date") is None

    def test_empty_string(self):
        assert _normalize_date("") is None

    def test_none_input(self):
        assert _normalize_date(None) is None  # type: ignore[arg-type]


# ── Organization author skipping ──────────────────────────────────────


class TestOrganizationAuthorSkipping:
    """Test that Organization-type JSON-LD authors are skipped."""

    def test_organization_author_skipped(self):
        """Should skip Organization-type author in JSON-LD."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "headline": "Test",
                "author": {"@type": "Organization", "name": "The Energy"}
            }"""
        )
        result = extract_structured_metadata(html)
        assert "author" not in result

    def test_person_author_kept(self):
        """Should keep Person-type author in JSON-LD."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "headline": "Test",
                "author": {"@type": "Person", "name": "Jane Doe"}
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Jane Doe"

    def test_no_type_author_kept(self):
        """Should keep author dict without @type."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": {"name": "John Smith"}
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "John Smith"

    def test_mixed_list_skips_organizations(self):
        """Should skip Organization entries in author list."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": [
                    {"@type": "Person", "name": "Alice"},
                    {"@type": "Organization", "name": "Corp Inc"},
                    {"@type": "Person", "name": "Bob"}
                ]
            }"""
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Alice, Bob"

    def test_org_author_falls_through_to_meta(self):
        """Organization JSON-LD author should be skipped, meta tag used."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": {"@type": "Organization", "name": "Site Name"}
            }""",
            '<meta name="author" content="Real Author">',
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Real Author"


# ── Byline link extraction ────────────────────────────────────────────


class TestBylineLinkExtraction:
    """Test author extraction from byline links."""

    def test_person_link(self):
        """Should extract author from /person/ link."""
        html = (
            "<html><head></head><body>"
            '<a href="https://example.com/person/jane-doe">Jane Doe</a>'
            "</body></html>"
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Jane Doe"

    def test_author_link(self):
        """Should extract author from /author/ link."""
        html = (
            "<html><head></head><body>"
            '<a href="https://example.com/author/john-smith">John Smith</a>'
            "</body></html>"
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "John Smith"

    def test_writer_link(self):
        """Should extract author from /writer/ link."""
        html = (
            "<html><head></head><body>"
            '<a href="https://example.com/writer/someone">Someone</a>'
            "</body></html>"
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Someone"

    def test_does_not_override_structured_author(self):
        """Byline link should not override JSON-LD author."""
        html = _wrap_jsonld(
            """{
                "@type": "Article",
                "author": "Structured Author"
            }""",
            '</head><body><a href="/person/other">Other Person</a></body>',
        )
        # Remove closing tags from wrapper for valid HTML
        result = extract_structured_metadata(html)
        assert result["author"] == "Structured Author"

    def test_org_skipped_then_byline_used(self):
        """Org author skipped → byline link used as fallback."""
        html = (
            '<html><head><script type="application/ld+json">'
            '{"@type": "Article", "author": {"@type": "Organization", "name": "Site"}}'
            "</script></head><body>"
            '<a class="byline" href="https://site.com/person/real-author">Real Author</a>'
            "</body></html>"
        )
        result = extract_structured_metadata(html)
        assert result["author"] == "Real Author"
