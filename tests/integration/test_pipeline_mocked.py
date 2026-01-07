import types

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
    @property
    def ragflow_client(self):
        class _DummyRagflow:
            def trigger_parsing(self, dataset_id):
                return True

            def wait_for_parsing(self, dataset_id):
                return True

        return _DummyRagflow()


def test_pipeline_with_mocked_dependencies(monkeypatch):
    # Monkeypatch registry to return dummy scraper
    monkeypatch.setattr(ScraperRegistry, "get_scraper", lambda *args, **kwargs: DummyScraper())

    # Bypass real upload/parsing side effects
    monkeypatch.setattr(Pipeline, "_upload_to_ragflow", lambda self: {"uploaded": 1, "failed": 0})
    monkeypatch.setattr(Pipeline, "_trigger_parsing", lambda self: True)
    monkeypatch.setattr(Pipeline, "_wait_for_parsing", lambda self: True)

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds",
        upload_to_ragflow=True,
        wait_for_parsing=True,
        container=DummyContainer(),
    )

    result = pipeline.run()
    assert isinstance(result, PipelineResult)
    assert result.status == "completed"
    assert result.uploaded_count == 1
    assert result.parsed_count == 1
    assert result.failed_count == 0
