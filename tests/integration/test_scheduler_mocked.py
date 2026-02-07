"""Test Scheduler run_now triggers scraper via pipeline."""

from unittest.mock import patch, Mock

from app.orchestrator.pipeline import PipelineResult
from app.orchestrator.scheduler import Scheduler


def test_scheduler_run_now_triggers_scraper():
    """Scheduler.run_now should invoke run_pipeline for the given scraper."""
    mock_result = PipelineResult(
        status="completed",
        scraper_name="dummy",
        downloaded_count=1,
    )

    # run_pipeline is imported locally inside _run_scraper, so patch at source
    with patch("app.orchestrator.pipeline.run_pipeline", return_value=mock_result) as mock_run:
        scheduler = Scheduler()
        thread = scheduler.run_now("dummy")
        thread.join(timeout=5)

        if thread.is_alive():
            raise AssertionError("Scheduler thread did not complete within 5 seconds")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["scraper_name"] == "dummy"
