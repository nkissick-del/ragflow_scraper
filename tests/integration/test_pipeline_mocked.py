from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry


class DummyScraperResult:
    def __init__(self):
        self.scraped_count = 2
        self.downloaded_count = 1
        self.errors = []
        self.status = "completed"

    def to_dict(self):
        return {
            "scraped_count": self.scraped_count,
            "downloaded_count": self.downloaded_count,
            "errors": self.errors,
            "status": self.status,
        }


class DummyScraper:
    def run(self):
        return DummyScraperResult()


class DummyContainer:
    pass


def test_pipeline_with_mocked_dependencies(monkeypatch):
    # Monkeypatch registry to return dummy scraper
    monkeypatch.setattr(
        ScraperRegistry, "get_scraper", lambda *args, **kwargs: DummyScraper()
    )

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds",
        upload_to_ragflow=True,
        verify_document_timeout=5,
        container=DummyContainer(),
    )

    # We need to mock _process_document because it calls real backend tools
    monkeypatch.setattr(
        Pipeline,
        "_process_document",
        lambda self, meta, path: {
            "parsed": True,
            "archived": True,
            "verified": True,
            "rag_indexed": True,
            "error": None,
        },
    )

    result = pipeline.run()
    assert isinstance(result, PipelineResult)
    assert result.status == "completed"
    assert result.uploaded_count == 1
    assert result.parsed_count == 1
    assert result.failed_count == 0
