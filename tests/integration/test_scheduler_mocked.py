"""Test Scheduler run_now triggers scraper via JobQueue."""

from unittest.mock import MagicMock, patch

from app.orchestrator.scheduler import Scheduler


def test_scheduler_run_now_triggers_scraper():
    """Scheduler.run_now should enqueue a Pipeline into the shared JobQueue."""
    mock_pipeline = MagicMock()
    mock_job_queue = MagicMock()

    with (
        patch("app.orchestrator.pipeline.Pipeline", return_value=mock_pipeline) as mock_cls,
        patch("app.web.runtime.job_queue", mock_job_queue),
        patch("app.orchestrator.scheduler.Config") as mock_config,
    ):
        mock_config.DATABASE_URL = ""
        mock_config.get_scraper_config_path.return_value = MagicMock(exists=lambda: False)

        scheduler = Scheduler()
        scheduler.run_now("dummy")

        mock_cls.assert_called_once()
        assert mock_cls.call_args[1]["scraper_name"] == "dummy"
        mock_job_queue.enqueue.assert_called_once_with("dummy", mock_pipeline)
