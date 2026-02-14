"""Tests for paperless_client utility functions."""

from __future__ import annotations

from app.services.paperless_client import (
    build_paperless_native_fields,
    flatten_metadata_extras,
)


class TestFlattenMetadataExtras:
    def test_basic(self):
        """Extra dict keys promoted to top level."""
        metadata = {
            "title": "Test",
            "extra": {
                "llm_summary": "A summary of the article",
                "llm_keywords": "energy, solar",
            },
        }
        result = flatten_metadata_extras(metadata)

        assert result["llm_summary"] == "A summary of the article"
        assert result["llm_keywords"] == "energy, solar"
        assert result["title"] == "Test"

    def test_no_overwrite(self):
        """Existing top-level keys are preserved."""
        metadata = {
            "author": "Jane Doe",
            "extra": {
                "author": "LLM Author",
                "llm_summary": "Summary",
            },
        }
        result = flatten_metadata_extras(metadata)

        # Top-level author should NOT be overwritten by extra.author
        assert result["author"] == "Jane Doe"
        # llm_summary should be promoted
        assert result["llm_summary"] == "Summary"

    def test_no_extra(self):
        """Dict without 'extra' returns a copy."""
        metadata = {"title": "Test", "author": "Bob"}
        result = flatten_metadata_extras(metadata)

        assert result == metadata
        # Must be a copy, not the same object
        assert result is not metadata

    def test_only_mapped_keys(self):
        """Non-CUSTOM_FIELD_MAPPING keys in extra stay in extra only."""
        metadata = {
            "title": "Test",
            "extra": {
                "llm_summary": "Summary",
                "some_random_key": "random value",
                "categories": ["Energy"],
            },
        }
        result = flatten_metadata_extras(metadata)

        # llm_summary is in CUSTOM_FIELD_MAPPING -> promoted
        assert result["llm_summary"] == "Summary"
        # some_random_key is NOT in CUSTOM_FIELD_MAPPING -> not promoted
        assert "some_random_key" not in result
        # categories is NOT in CUSTOM_FIELD_MAPPING -> not promoted
        assert "categories" not in result

    def test_empty_extra(self):
        """Empty extra dict returns copy of metadata."""
        metadata = {"title": "Test", "extra": {}}
        result = flatten_metadata_extras(metadata)

        assert result["title"] == "Test"
        assert result["extra"] == {}

    def test_extra_not_dict(self):
        """Non-dict extra is ignored."""
        metadata = {"title": "Test", "extra": "not a dict"}
        result = flatten_metadata_extras(metadata)

        assert result["title"] == "Test"
        assert result["extra"] == "not a dict"


class TestBuildPaperlessNativeFields:
    def test_author_as_correspondent(self):
        """Author used as correspondent."""
        metadata = {
            "title": "Test Article",
            "publication_date": "2025-01-15",
            "author": "Jane Doe",
            "organization": "Test Org",
            "document_type": "Article",
            "tags": ["Energy", "Solar"],
        }
        result = build_paperless_native_fields(metadata)

        assert result["title"] == "Test Article"
        assert result["created"] == "2025-01-15"
        assert result["correspondent"] == "Jane Doe"
        assert result["document_type"] == "Article"
        assert result["tags"] == ["Energy", "Solar"]

    def test_org_fallback(self):
        """No author, organization used as correspondent."""
        metadata = {
            "title": "Test Article",
            "publication_date": "2025-01-15",
            "author": None,
            "organization": "Test Org",
            "document_type": "Article",
            "tags": ["Energy"],
        }
        result = build_paperless_native_fields(metadata)

        assert result["correspondent"] == "Test Org"

    def test_empty_author_falls_back(self):
        """Empty string author falls back to organization."""
        metadata = {
            "title": "Test",
            "author": "",
            "organization": "Fallback Org",
        }
        result = build_paperless_native_fields(metadata)

        assert result["correspondent"] == "Fallback Org"

    def test_empty_metadata(self):
        """All None/empty when metadata has no relevant keys."""
        metadata = {}
        result = build_paperless_native_fields(metadata)

        assert result["title"] is None
        assert result["created"] is None
        assert result["correspondent"] is None
        assert result["document_type"] is None
        assert result["tags"] == []
