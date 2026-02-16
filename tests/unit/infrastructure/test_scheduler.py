"""Tests for APScheduler-based Scheduler."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.orchestrator.scheduler import Scheduler


class TestAddScraperSchedule:
    """Tests for add_scraper_schedule()."""

    @patch("app.orchestrator.scheduler.Config")
    def test_adds_job(self, mock_config):
        """Job is added to the APScheduler."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        scheduler.add_scraper_schedule("my_scraper", "0 2 * * *")
        ap = scheduler._get_scheduler()
        job = ap.get_job("scraper_my_scraper")

        assert job is not None

    @patch("app.orchestrator.scheduler.Config")
    def test_replaces_existing_job(self, mock_config):
        """Adding same scraper name replaces old job."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        scheduler.add_scraper_schedule("my_scraper", "0 2 * * *")
        scheduler.add_scraper_schedule("my_scraper", "0 6 * * *")

        ap = scheduler._get_scheduler()
        jobs = ap.get_jobs()
        matching = [j for j in jobs if j.id == "scraper_my_scraper"]
        assert len(matching) == 1

    @patch("app.orchestrator.scheduler.Config")
    def test_logs_event(self, mock_config):
        """Scheduling a job logs an event."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        with patch("app.orchestrator.scheduler.log_event") as mock_log:
            scheduler.add_scraper_schedule("test_scraper", "0 2 * * *")

            mock_log.assert_called()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["scraper"] == "test_scraper"
            assert call_kwargs["cron"] == "0 2 * * *"

    @patch("app.orchestrator.scheduler.Config")
    def test_invalid_cron_logs_error(self, mock_config):
        """Malformed cron with wrong part count logs error."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        with patch.object(scheduler.logger, "error") as mock_error:
            scheduler.add_scraper_schedule("test", "bad cron")
            mock_error.assert_called()

    @patch("app.orchestrator.scheduler.Config")
    def test_too_few_parts_logs_error(self, mock_config):
        """Cron with fewer than 5 parts logs error."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        with patch.object(scheduler.logger, "error") as mock_error:
            scheduler.add_scraper_schedule("test", "* * *")
            mock_error.assert_called()


class TestRemoveAndClear:
    """Tests for remove_schedule() and clear_all()."""

    @patch("app.orchestrator.scheduler.Config")
    def test_remove_existing(self, mock_config):
        """Removing an existing schedule clears it."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("test", "0 2 * * *")

        scheduler.remove_schedule("test")

        ap = scheduler._get_scheduler()
        assert ap.get_job("scraper_test") is None

    @patch("app.orchestrator.scheduler.Config")
    def test_remove_nonexistent_is_noop(self, mock_config):
        """Removing a nonexistent schedule doesn't raise."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()
        scheduler.remove_schedule("nonexistent")

    @patch("app.orchestrator.scheduler.Config")
    def test_clear_all_empties_jobs(self, mock_config):
        """clear_all() removes all jobs."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("scraper_a", "0 1 * * *")
        scheduler.add_scraper_schedule("scraper_b", "0 2 * * *")

        scheduler.clear_all()

        ap = scheduler._get_scheduler()
        assert len(ap.get_jobs()) == 0


class TestStartStop:
    """Tests for start() and stop()."""

    @patch("app.orchestrator.scheduler.Config")
    def test_start_and_stop(self, mock_config):
        """start() starts scheduler, stop() shuts it down."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        scheduler.start()
        try:
            ap = scheduler._get_scheduler()
            assert ap.running is True
        finally:
            scheduler.stop()

    @patch("app.orchestrator.scheduler.Config")
    def test_start_when_already_running_warns(self, mock_config):
        """Calling start() when running logs a warning."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()

        scheduler.start()
        try:
            with patch.object(scheduler.logger, "warning") as mock_warn:
                scheduler.start()
                mock_warn.assert_called_once()
        finally:
            scheduler.stop()


class TestGetStatusAndNextRuns:
    """Tests for get_status() and get_next_runs()."""

    @patch("app.orchestrator.scheduler.Config")
    def test_status_returns_job_count(self, mock_config):
        """get_status() includes running state and job count."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("test", "0 2 * * *")

        status = scheduler.get_status()

        assert status["running"] is False
        assert status["job_count"] == 1
        assert len(status["jobs"]) == 1

    @patch("app.orchestrator.scheduler.Config")
    def test_next_runs_returns_dict(self, mock_config):
        """get_next_runs() returns dict of scraper → datetime or None."""
        mock_config.DATABASE_URL = ""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("scraper_a", "0 2 * * *")

        next_runs = scheduler.get_next_runs()

        assert "scraper_a" in next_runs


class TestLoadSchedules:
    """Tests for load_schedules()."""

    @patch("app.orchestrator.scheduler.Config")
    def test_loads_from_config_files(self, mock_config, tmp_path):
        """Loads enabled schedules from JSON config files."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path
        mock_config.DATABASE_URL = ""

        config_data = {
            "name": "test_scraper",
            "schedule": {"enabled": True, "cron": "0 3 * * *"},
        }
        (tmp_path / "test_scraper.json").write_text(json.dumps(config_data))

        scheduler = Scheduler()
        scheduler.load_schedules()

        ap = scheduler._get_scheduler()
        assert ap.get_job("scraper_test_scraper") is not None

    @patch("app.orchestrator.scheduler.Config")
    def test_skips_template_json(self, mock_config, tmp_path):
        """template.json is always skipped."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path
        mock_config.DATABASE_URL = ""

        (tmp_path / "template.json").write_text(json.dumps({
            "name": "template",
            "schedule": {"enabled": True, "cron": "0 0 * * *"},
        }))

        scheduler = Scheduler()
        scheduler.load_schedules()

        ap = scheduler._get_scheduler()
        assert ap.get_job("scraper_template") is None

    @patch("app.orchestrator.scheduler.Config")
    def test_handles_invalid_json(self, mock_config, tmp_path):
        """Invalid JSON files are skipped gracefully."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path
        mock_config.DATABASE_URL = ""

        (tmp_path / "broken.json").write_text("{invalid json")

        scheduler = Scheduler()
        scheduler.load_schedules()

        ap = scheduler._get_scheduler()
        assert len(ap.get_jobs()) == 0

    @patch("app.orchestrator.scheduler.Config")
    def test_skips_disabled_schedules(self, mock_config, tmp_path):
        """Schedules with enabled=False are skipped."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path
        mock_config.DATABASE_URL = ""

        (tmp_path / "disabled.json").write_text(json.dumps({
            "name": "disabled_scraper",
            "schedule": {"enabled": False, "cron": "0 0 * * *"},
        }))

        scheduler = Scheduler()
        scheduler.load_schedules()

        ap = scheduler._get_scheduler()
        assert ap.get_job("scraper_disabled_scraper") is None
