from unittest.mock import Mock, patch
from pathlib import Path
from app.scrapers.models import DocumentMetadata
from app.scrapers.mixins import (
    HttpDownloadMixin,
    CloudflareBypassMixin,
    MetadataIOMixin,
)


class TestScraperFixes:
    """Verification for specific fixes in mixins and models."""

    def test_pdf_path_assignment_post_success(self, tmp_path):
        """Verify extra.html_path is only assigned after successful file operations."""

        class TestScraper(MetadataIOMixin):
            name = "test"
            dry_run = False
            logger = Mock()

        scraper = TestScraper()
        article = DocumentMetadata(url="u", title="t", filename="f.md")

        # Mock file writing to fail (write_bytes for the markdown temp file)
        with patch(
            "pathlib.Path.write_bytes", side_effect=Exception("Write failed")
        ):
            with patch("app.scrapers.mixins.ensure_dir", return_value=tmp_path):
                scraper._save_article(article, "content", html_content="<html>")

            # extra.html_path should NOT be set because we failed before the mutation block
            assert article.extra.get("html_path") is None

    def test_mixin_super_init_calls(self):
        """Verify mixins call super().__init__()."""

        class Parent:
            def __init__(self):
                self.parent_init_called = True

        class TestHttpMixin(HttpDownloadMixin, Parent):
            pass

        class TestCloudflareMixin(CloudflareBypassMixin, Parent):
            pass

        h = TestHttpMixin()
        assert getattr(h, "parent_init_called", False) is True
        assert hasattr(h, "_errors")

        c = TestCloudflareMixin()
        assert getattr(c, "parent_init_called", False) is True
        assert hasattr(c, "_cloudflare_cookies")

    def test_smart_merge_page_count_mapping(self):
        """Verify page_count is correctly mapped to top-level DocumentMetadata."""
        doc = DocumentMetadata(url="u", title="t", filename="f")
        parser_meta = {"page_count": 5, "author": "Me"}

        merged = doc.merge_parser_metadata(parser_meta, strategy="smart")

        assert merged.page_count == 5
        assert merged.extra.get("author") == "Me"
        assert "page_count" not in merged.extra

    def test_extra_clobber_protection(self):
        """Verify extra field is merged, not overwritten."""
        doc = DocumentMetadata(
            url="u", title="t", filename="f", extra={"existing": "val"}
        )

        # Parser wins
        parser_meta = {"extra": {"new": "val"}, "other": "val"}
        merged = doc.merge_parser_metadata(parser_meta, strategy="parser_wins")
        assert merged.extra["existing"] == "val"
        assert merged.extra["new"] == "val"
        assert merged.extra["other"] == "val"

        # Scraper wins
        merged_sw = doc.merge_parser_metadata(parser_meta, strategy="scraper_wins")
        assert merged_sw.extra["existing"] == "val"
        assert merged_sw.extra["new"] == "val"
        assert merged_sw.extra["other"] == "val"

    def test_metadata_type_validation_coercion(self):
        """Verify type validation and coercion for standard fields."""
        doc = DocumentMetadata(url="u", title="t", filename="f")

        # Valid int coercion
        parser_meta = {"file_size": "100", "title": 123}
        merged = doc.merge_parser_metadata(parser_meta, strategy="parser_wins")

        assert merged.file_size == 100
        assert merged.title == "123"  # Coerced to string

        # Failed int coercion - moves to extra
        parser_meta_fail = {"file_size": "not-an-int"}
        merged_fail = doc.merge_parser_metadata(
            parser_meta_fail, strategy="parser_wins"
        )
        assert merged_fail.file_size is None
        assert merged_fail.extra["file_size"] == "not-an-int"
