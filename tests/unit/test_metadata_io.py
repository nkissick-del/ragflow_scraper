import pytest
import json
import hashlib
from pathlib import Path
from unittest.mock import Mock
from app.scrapers.mixins import MetadataIOMixin
from app.scrapers.models import DocumentMetadata

class TestMetadataIOMixin:
    def setup_method(self):
        class TestScraper(MetadataIOMixin):
            name = "test_scraper"
            dry_run = False
            logger = Mock()

        self.scraper = TestScraper()

    def test_save_article_saves_files_and_calculates_hash(self, tmp_path):
        article = DocumentMetadata(
            title="Test Article",
            url="http://example.com/test",
            filename="test_article.pdf",
            publication_date="2024-01-01"
        )
        content = "Test content for hashing"

        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.config.Config.DOWNLOAD_DIR", tmp_path)

            saved_path = self.scraper._save_article(article, content)

            assert saved_path is not None

            # Check files exist
            md_path = Path(saved_path)
            json_path = md_path.with_suffix(".json")

            assert md_path.exists()
            assert json_path.exists()

            # Verify content
            assert md_path.read_text(encoding="utf-8") == content

            # Verify JSON metadata
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["filename"] == "test_article.pdf"
            assert data["file_size"] == len(content.encode("utf-8"))

            # Verify hash is present and correct
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert data["hash"] == expected_hash

            # Verify object was updated
            assert article.hash == expected_hash
            assert article.file_size == len(content.encode("utf-8"))
            assert article.local_path == str(md_path)
