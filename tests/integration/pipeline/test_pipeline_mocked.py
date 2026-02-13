"""Test Pipeline with mocked dependencies (smoke test)."""

from unittest.mock import Mock

from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry


class DummyScraperResult:
    def __init__(self):
        self.scraped_count = 2
        self.downloaded_count = 1
        self.errors = []
        self.status = "completed"
        self.documents = []  # empty — pipeline skips processing loop


class DummyScraper:
    def run(self):
        result = DummyScraperResult()
        yield from result.documents
        return result


def test_pipeline_with_mocked_dependencies(monkeypatch):
    """Pipeline completes successfully with zero documents to process."""
    monkeypatch.setattr(
        ScraperRegistry, "get_scraper", lambda *args, **kwargs: DummyScraper()
    )

    container = Mock()
    # Pipeline __init__ accesses ragflow_client when upload_to_ragflow=True
    container.ragflow_client = Mock()
    # Pipeline reads settings overrides
    container.settings.get.return_value = ""

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds",
        upload_to_ragflow=True,
        verify_document_timeout=5,
        container=container,
    )

    result = pipeline.run()
    assert isinstance(result, PipelineResult)
    # No documents yielded → downloaded_count is 0, scraped_count from scraper
    assert result.status == "completed"
    assert result.downloaded_count == 0
    assert result.scraped_count == 2
    assert result.parsed_count == 0
    assert result.failed_count == 0
