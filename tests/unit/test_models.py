"""Unit tests for scraper data models (DocumentMetadata, ScraperResult)."""

from __future__ import annotations

import json

from app.scrapers.models import DocumentMetadata, ScraperResult


# ── TestDocumentMetadata ────────────────────────────────────────────────


class TestDocumentMetadata:
    """Tests for DocumentMetadata dataclass."""

    def test_required_fields(self):
        """Minimal construction with required fields."""
        doc = DocumentMetadata(url="http://x.com/doc.pdf", title="Test", filename="doc.pdf")
        assert doc.url == "http://x.com/doc.pdf"
        assert doc.title == "Test"
        assert doc.filename == "doc.pdf"

    def test_optional_defaults(self):
        """Optional fields default to None/empty."""
        doc = DocumentMetadata(url="http://x.com", title="T", filename="f.pdf")
        assert doc.file_size is None
        assert doc.page_count is None
        assert doc.publication_date is None
        assert doc.tags == []
        assert doc.extra == {}
        assert doc.paperless_id is None

    def test_to_dict(self):
        """to_dict() returns all fields."""
        doc = DocumentMetadata(
            url="http://x.com",
            title="My Doc",
            filename="doc.pdf",
            tags=["energy"],
            organization="AEMO",
        )
        d = doc.to_dict()
        assert d["url"] == "http://x.com"
        assert d["title"] == "My Doc"
        assert d["tags"] == ["energy"]
        assert d["organization"] == "AEMO"
        assert "scraped_at" in d

    def test_merge_smart_strategy(self):
        """Smart merge: parser wins title, scraper wins URL/date/org."""
        scraper_doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Scraper Title",
            filename="doc.pdf",
            publication_date="2024-01-15",
            organization="AEMO",
        )
        parser_meta = {"title": "Parser Title", "author": "John Doe", "page_count": 42}

        merged = scraper_doc.merge_parser_metadata(parser_meta, strategy="smart")

        assert merged.title == "Parser Title"  # parser wins
        assert merged.url == "http://example.com/doc.pdf"  # scraper wins
        assert merged.publication_date == "2024-01-15"  # scraper wins
        assert merged.organization == "AEMO"  # scraper wins
        assert merged.extra.get("author") == "John Doe"
        assert merged.page_count == 42

    def test_merge_parser_wins_strategy(self):
        """Parser wins: parser overwrites matching fields."""
        scraper_doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Scraper Title",
            filename="doc.pdf",
        )
        parser_meta = {"title": "Parser Title"}

        merged = scraper_doc.merge_parser_metadata(parser_meta, strategy="parser_wins")

        assert merged.title == "Parser Title"

    def test_merge_scraper_wins_strategy(self):
        """Scraper wins: only adds new fields from parser."""
        scraper_doc = DocumentMetadata(
            url="http://example.com/doc.pdf",
            title="Scraper Title",
            filename="doc.pdf",
        )
        parser_meta = {"title": "Parser Title", "page_count": 10}

        merged = scraper_doc.merge_parser_metadata(parser_meta, strategy="scraper_wins")

        assert merged.title == "Scraper Title"  # kept
        assert merged.page_count == 10  # added (was None)


# ── TestScraperResult ───────────────────────────────────────────────────


class TestScraperResult:
    """Tests for ScraperResult dataclass."""

    def test_defaults(self):
        """Default values for counters and lists."""
        result = ScraperResult(status="completed", scraper="test")
        assert result.scraped_count == 0
        assert result.downloaded_count == 0
        assert result.failed_count == 0
        assert result.documents == []
        assert result.errors == []
        assert result.completed_at is None

    def test_to_dict(self):
        """to_dict() returns complete dict."""
        result = ScraperResult(
            status="partial",
            scraper="aemo",
            scraped_count=10,
            downloaded_count=8,
            failed_count=2,
        )
        d = result.to_dict()
        assert d["status"] == "partial"
        assert d["scraper"] == "aemo"
        assert d["scraped_count"] == 10

    def test_to_json(self):
        """to_json() returns valid JSON string."""
        result = ScraperResult(status="completed", scraper="test")
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["status"] == "completed"
        assert parsed["scraper"] == "test"
