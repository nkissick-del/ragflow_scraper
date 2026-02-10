"""Unit tests for JSONLDDateExtractionMixin."""

from unittest.mock import MagicMock

from app.scrapers.jsonld_mixin import JSONLDDateExtractionMixin


def _make_mixin():
    """Create a mixin instance with a mock logger."""
    mixin = JSONLDDateExtractionMixin()
    mixin.logger = MagicMock()
    return mixin


def _wrap_jsonld(jsonld: str) -> str:
    return f'<html><head><script type="application/ld+json">{jsonld}</script></head><body></body></html>'


class TestExtractJsonldDates:
    def test_graph_array_article(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('''{
            "@graph": [
                {"@type": "WebPage"},
                {"@type": "Article", "datePublished": "2025-12-23T01:59:09+00:00", "dateModified": "2025-12-24T02:00:00+00:00"}
            ]
        }''')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-12-23"
        assert result["date_modified"] == "2025-12-24"

    def test_single_object_article(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@type": "Article", "datePublished": "2025-06-15T10:30:00Z"}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-06-15"

    def test_list_of_objects(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('[{"@type": "Article", "datePublished": "2025-01-01"}]')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-01-01"

    def test_date_created_extracted(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@type": "Article", "dateCreated": "2025-03-10T12:00:00+11:00"}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_created"] == "2025-03-10"

    def test_all_three_dates(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('''{
            "@type": "Article",
            "datePublished": "2025-01-01",
            "dateCreated": "2024-12-31",
            "dateModified": "2025-01-02"
        }''')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-01-01"
        assert result["date_created"] == "2024-12-31"
        assert result["date_modified"] == "2025-01-02"

    def test_missing_fields_return_none(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@type": "Article", "headline": "Test"}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None
        assert result["date_created"] is None
        assert result["date_modified"] is None

    def test_no_article_type(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@type": "WebPage", "datePublished": "2025-01-01"}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None

    def test_malformed_json(self):
        mixin = _make_mixin()
        html = _wrap_jsonld("{not valid json}")
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None

    def test_empty_script_tag(self):
        mixin = _make_mixin()
        html = '<html><head><script type="application/ld+json"></script></head><body></body></html>'
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None

    def test_no_jsonld_at_all(self):
        mixin = _make_mixin()
        html = "<html><body><p>No structured data</p></body></html>"
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None

    def test_multiple_script_tags_first_match_wins(self):
        mixin = _make_mixin()
        html = (
            '<html><head>'
            '<script type="application/ld+json">{"@type": "WebSite"}</script>'
            '<script type="application/ld+json">{"@type": "Article", "datePublished": "2025-07-04"}</script>'
            '</head><body></body></html>'
        )
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-07-04"

    def test_empty_date_string_ignored(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@type": "Article", "datePublished": ""}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] is None

    def test_non_dict_items_in_graph_skipped(self):
        mixin = _make_mixin()
        html = _wrap_jsonld('{"@graph": ["string", 42, {"@type": "Article", "datePublished": "2025-03-15"}]}')
        result = mixin._extract_jsonld_dates(html)
        assert result["date_published"] == "2025-03-15"


class TestParseIsoDate:
    def test_full_iso_with_timezone(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("2025-12-23T01:59:09+00:00") == "2025-12-23"

    def test_iso_with_z(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("2025-06-15T10:30:00Z") == "2025-06-15"

    def test_date_only(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("2025-01-01") == "2025-01-01"

    def test_empty_string(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("") is None

    def test_invalid_date(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("not-a-date") is None

    def test_positive_offset_timezone(self):
        mixin = _make_mixin()
        assert mixin._parse_iso_date("2025-12-24T07:30:00+11:00") == "2025-12-24"

    def test_negative_offset_timezone(self):
        mixin = _make_mixin()
        # Note: the split("+") approach means negative offsets keep the minus
        # The date portion is still extracted correctly
        assert mixin._parse_iso_date("2025-12-24T07:30:00-05:00") == "2025-12-24"
