from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry


class DummyScraperResult:
    def __init__(self):
        self.scraped_count = 1
        self.downloaded_count = 1
        self.errors = []
        self.status = "completed"


class DummyScraper:
    def run(self):
        return DummyScraperResult()


class DummyContainer:
    def get_ragflow_client(self):
        class _Dummy:
            ...

        return _Dummy()

    def get_settings_manager(self):
        class _Dummy:
            ...

        return _Dummy()

    def get_state_tracker(self, scraper_name: str):
        class _Dummy:
            ...

        return _Dummy()


def test_pipeline_marks_partial_on_failed_upload(monkeypatch):
    # Return a dummy scraper instance
    monkeypatch.setattr(ScraperRegistry, "get_scraper", lambda *_, **__: DummyScraper())

    # Force upload step to report a failure
    monkeypatch.setattr(Pipeline, "_upload_to_ragflow", lambda self: {"uploaded": 0, "failed": 1})
    monkeypatch.setattr(Pipeline, "_trigger_parsing", lambda self: False)
    monkeypatch.setattr(Pipeline, "_wait_for_parsing", lambda self: False)

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds-123",
        upload_to_ragflow=True,
        wait_for_parsing=True,
        container=DummyContainer(),
    )

    result = pipeline.run()

    assert isinstance(result, PipelineResult)
    assert result.status == "partial"
    assert result.uploaded_count == 0
    assert result.failed_count == 1
    assert result.parsed_count == 0
