"""Test Pipeline archive flow."""

from unittest.mock import Mock

from app.backends.archives.base import ArchiveResult
from app.backends.parsers.base import ParserResult
from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry


def test_pipeline_uploads_and_marks_parsed(monkeypatch, tmp_path):
    """Pipeline archives document and marks it as parsed/archived."""
    # Create real files on disk
    pdf_file = tmp_path / "test_doc_1.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\nTest PDF content")
    md_file = tmp_path / "test_doc_1.md"
    md_file.write_text("# Test\n\nContent.")

    class DummyScraperResult:
        def __init__(self):
            self.scraped_count = 1
            self.downloaded_count = 1
            self.errors = []
            self.status = "completed"
            self.documents = [
                {
                    "title": "Test Doc",
                    "url": "http://example.com/doc1",
                    "filename": "test_doc_1.pdf",
                    "pdf_path": str(pdf_file),
                }
            ]

    class DummyScraper:
        def run(self):
            result = DummyScraperResult()
            yield from result.documents
            return result

    monkeypatch.setattr(
        ScraperRegistry, "get_scraper", lambda *_, **__: DummyScraper()
    )

    container = Mock()
    container.settings.get.return_value = ""

    # Parser succeeds
    container.parser_backend.parse_document.return_value = ParserResult(
        success=True,
        markdown_path=md_file,
        metadata={"title": "Test Doc"},
        parser_name="docling",
    )

    # Archive succeeds
    container.archive_backend.archive_document.return_value = ArchiveResult(
        success=True,
        document_id="doc-123",
        archive_name="paperless",
    )
    container.archive_backend.verify_document.return_value = True

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds-123",
        upload_to_ragflow=False,
        upload_to_paperless=True,
        verify_document_timeout=5,
        container=container,
    )

    result = pipeline.run()

    assert isinstance(result, PipelineResult)
    assert result.status == "completed"
    assert result.parsed_count == 1
    assert result.archived_count == 1
    assert result.verified_count == 1
    assert result.failed_count == 0

    # Verify archive was called
    container.archive_backend.archive_document.assert_called_once()
    container.archive_backend.verify_document.assert_called_once_with("doc-123", timeout=5)
