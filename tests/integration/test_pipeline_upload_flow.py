from pathlib import Path

from app.config import Config
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


class DummyUploadResult:
    def __init__(self, success: bool):
        self.success = success


class DummyRagflowClient:
    def __init__(self):
        self.upload_calls = []

    def upload_documents(self, dataset_id: str, files: list[Path]):
        self.upload_calls.append((dataset_id, [f.name for f in files]))
        return [DummyUploadResult(True) for _ in files]


class DummyContainer:
    def __init__(self, ragflow_client: DummyRagflowClient):
        self.ragflow_client = ragflow_client

    @property
    def settings(self):
        raise RuntimeError("not needed in this test")

    def state_tracker(self, scraper_name: str):
        raise RuntimeError("not needed in this test")


def test_pipeline_uploads_and_marks_parsed(monkeypatch, tmp_path):
    # Arrange: create a dummy downloaded PDF in a temp download dir
    download_dir = tmp_path / "dummy"
    download_dir.mkdir()
    (download_dir / "doc.pdf").write_bytes(b"pdf-bytes")

    # Redirect Config.DOWNLOAD_DIR to the temp path
    monkeypatch.setattr(Config, "DOWNLOAD_DIR", tmp_path)

    # Scraper returns completed result with a download
    monkeypatch.setattr(ScraperRegistry, "get_scraper", lambda *_, **__: DummyScraper())

    ragflow_client = DummyRagflowClient()
    container = DummyContainer(ragflow_client)

    # Keep upload logic intact but bypass parsing wait
    monkeypatch.setattr(Pipeline, "_trigger_parsing", lambda self: True)
    monkeypatch.setattr(Pipeline, "_wait_for_parsing", lambda self: True)

    pipeline = Pipeline(
        scraper_name="dummy",
        dataset_id="ds-123",
        upload_to_ragflow=True,
        wait_for_parsing=True,
        container=container,
    )

    # Act
    result = pipeline.run()

    # Assert
    assert isinstance(result, PipelineResult)
    assert result.status == "completed"
    assert result.uploaded_count == 1
    assert result.parsed_count == 1
    assert result.failed_count == 0
    assert ragflow_client.upload_calls == [("ds-123", ["doc.pdf"])]
