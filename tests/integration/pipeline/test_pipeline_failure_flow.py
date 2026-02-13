"""Test Pipeline partial failure flow."""

from unittest.mock import Mock

from app.backends.parsers.base import ParserResult
from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry


def test_pipeline_marks_partial_on_failed_upload(monkeypatch, tmp_path):
    """Pipeline reports 'partial' status when a document fails processing."""
    # Create a real PDF file that exists on disk
    pdf_file = tmp_path / "test_doc_1.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\nTest PDF content")

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
    md_file = tmp_path / "test_doc_1.md"
    md_file.write_text("# Test Doc\n\nContent.")
    container.parser_backend.parse_document.return_value = ParserResult(
        success=True,
        markdown_path=md_file,
        metadata={"title": "Test Doc"},
        parser_name="docling",
    )

    # Archive fails — this causes pipeline to count the document as failed
    from app.backends.archives.base import ArchiveResult

    container.archive_backend.archive_document.return_value = ArchiveResult(
        success=False,
        error="Upload rejected",
        archive_name="paperless",
    )

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds-123",
        upload_to_ragflow=False,
        upload_to_paperless=True,
        container=container,
    )

    result = pipeline.run()

    assert isinstance(result, PipelineResult)
    assert result.status == "partial"
    assert result.failed_count == 1
    assert result.archived_count == 0
    assert result.parsed_count == 0  # caught by outer handler before counter
