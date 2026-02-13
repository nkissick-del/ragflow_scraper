"""Tests for Scheduler."""

from __future__ import annotations

import json
import time
from datetime import datetime
from unittest.mock import patch

import schedule as schedule_lib

from app.orchestrator.scheduler import Scheduler


class TestSchedulerRunLoop:
    """Test _run_loop exception handling."""

    def test_run_loop_survives_exception(self):
        """Scheduler thread should survive exceptions from schedule.run_pending()."""
        scheduler = Scheduler()
        call_count = 0

        def flaky_run_pending():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            # After first call, just return normally

        with patch("app.orchestrator.scheduler.schedule") as mock_schedule:
            mock_schedule.run_pending = flaky_run_pending

            scheduler.start()
            # Wait for at least 2 iterations
            time.sleep(2.5)
            scheduler.stop()

        # Should have been called more than once (survived the exception)
        assert call_count >= 2

    def test_run_loop_logs_exception(self):
        """Scheduler should log exceptions from run_pending."""
        scheduler = Scheduler()

        with patch("app.orchestrator.scheduler.schedule") as mock_schedule:
            mock_schedule.run_pending.side_effect = [
                RuntimeError("boom"),
                None,
                None,
                None,
                None,
            ]

            with patch("app.orchestrator.scheduler.log_exception") as mock_log:
                scheduler.start()
                time.sleep(1.5)
                scheduler.stop()

                mock_log.assert_called_once()
                args = mock_log.call_args[0]
                assert args[0] == scheduler.logger
                assert isinstance(args[1], RuntimeError)
                assert args[2] == "scheduler.run_pending.exception"


class TestAddScraperSchedule:
    """Tests for add_scraper_schedule()."""

    def setup_method(self):
        schedule_lib.clear()

    def teardown_method(self):
        schedule_lib.clear()

    def test_stores_job(self):
        """Job is stored in _jobs dict."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("my_scraper", "0 2 * * *")

        assert "my_scraper" in scheduler._jobs

    def test_replaces_existing_job(self):
        """Adding same scraper name replaces old job."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("my_scraper", "0 2 * * *")
        old_job = scheduler._jobs["my_scraper"]

        scheduler.add_scraper_schedule("my_scraper", "0 6 * * *")
        new_job = scheduler._jobs["my_scraper"]

        assert old_job is not new_job

    def test_logs_event(self):
        """Scheduling a job logs an event."""
        scheduler = Scheduler()
        with patch("app.orchestrator.scheduler.log_event") as mock_log:
            scheduler.add_scraper_schedule("test_scraper", "0 2 * * *")

            mock_log.assert_called()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["scraper"] == "test_scraper"
            assert call_kwargs["cron"] == "0 2 * * *"


class TestParseCronAndSchedule:
    """Tests for _parse_cron_and_schedule()."""

    def setup_method(self):
        schedule_lib.clear()

    def teardown_method(self):
        schedule_lib.clear()

    def test_every_n_minutes(self):
        """*/5 * * * * schedules every 5 minutes."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "*/5 * * * *")

        assert job is not None
        assert job.interval == 5
        assert job.unit == "minutes"

    def test_every_n_hours(self):
        """0 */6 * * * schedules every 6 hours."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "0 */6 * * *")

        assert job is not None
        assert job.interval == 6
        assert job.unit == "hours"

    def test_daily_at_time(self):
        """0 2 * * * schedules daily at 02:00."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "0 2 * * *")

        assert job is not None
        assert job.unit == "days"
        assert job.at_time is not None
        assert job.at_time.hour == 2
        assert job.at_time.minute == 0

    def test_weekly_on_sunday(self):
        """0 0 * * 0 schedules weekly on Sunday at 00:00."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "0 0 * * 0")

        assert job is not None
        # schedule library stores day-of-week jobs as weekly
        assert job.at_time is not None

    def test_monthly_on_day(self):
        """0 9 15 * * schedules daily check for day 15 at 09:00."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "0 9 15 * *")

        assert job is not None
        assert job.unit == "days"

    def test_invalid_cron_returns_none(self):
        """Malformed cron expression returns None."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "bad cron")

        assert job is None

    def test_too_few_parts_returns_none(self):
        """Cron with fewer than 5 parts returns None."""
        scheduler = Scheduler()
        job = scheduler._parse_cron_and_schedule("test", "* * *")

        assert job is None


class TestRemoveAndClear:
    """Tests for remove_schedule() and clear_all()."""

    def setup_method(self):
        schedule_lib.clear()

    def teardown_method(self):
        schedule_lib.clear()

    def test_remove_existing(self):
        """Removing an existing schedule clears it."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("test", "0 2 * * *")
        assert "test" in scheduler._jobs

        scheduler.remove_schedule("test")

        assert "test" not in scheduler._jobs

    def test_remove_nonexistent_is_noop(self):
        """Removing a nonexistent schedule doesn't raise."""
        scheduler = Scheduler()
        scheduler.remove_schedule("nonexistent")
        # Should not raise

    def test_clear_all_empties_jobs(self):
        """clear_all() removes all jobs."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("scraper_a", "0 1 * * *")
        scheduler.add_scraper_schedule("scraper_b", "0 2 * * *")
        assert len(scheduler._jobs) == 2

        scheduler.clear_all()

        assert len(scheduler._jobs) == 0


class TestStartStop:
    """Tests for start() and stop()."""

    def test_start_creates_daemon_thread(self):
        """start() creates a daemon thread."""
        scheduler = Scheduler()

        with patch("app.orchestrator.scheduler.schedule"):
            scheduler.start()
            try:
                assert scheduler._running is True
                assert scheduler._thread is not None
                assert scheduler._thread.daemon is True
            finally:
                scheduler.stop()

    def test_stop_joins_thread(self):
        """stop() sets _running=False and joins thread."""
        scheduler = Scheduler()

        with patch("app.orchestrator.scheduler.schedule"):
            scheduler.start()
            scheduler.stop()

            assert scheduler._running is False
            assert scheduler._thread is None

    def test_start_when_already_running_warns(self):
        """Calling start() when running logs a warning."""
        scheduler = Scheduler()

        with patch("app.orchestrator.scheduler.schedule"):
            scheduler.start()
            try:
                with patch.object(scheduler.logger, "warning") as mock_warn:
                    scheduler.start()
                    mock_warn.assert_called_once()
            finally:
                scheduler.stop()


class TestGetStatusAndNextRuns:
    """Tests for get_status() and get_next_runs()."""

    def setup_method(self):
        schedule_lib.clear()

    def teardown_method(self):
        schedule_lib.clear()

    def test_status_returns_running_and_job_count(self):
        """get_status() includes running state and job count."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("test", "0 2 * * *")

        status = scheduler.get_status()

        assert status["running"] is False
        assert status["job_count"] == 1
        assert len(status["jobs"]) == 1

    def test_next_runs_returns_datetime_dict(self):
        """get_next_runs() returns dict of scraper → datetime."""
        scheduler = Scheduler()
        scheduler.add_scraper_schedule("scraper_a", "0 2 * * *")

        next_runs = scheduler.get_next_runs()

        assert "scraper_a" in next_runs
        assert isinstance(next_runs["scraper_a"], datetime)


class TestLoadSchedules:
    """Tests for load_schedules()."""

    def setup_method(self):
        schedule_lib.clear()

    def teardown_method(self):
        schedule_lib.clear()

    @patch("app.orchestrator.scheduler.Config")
    def test_loads_from_config_files(self, mock_config, tmp_path):
        """Loads enabled schedules from JSON config files."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path

        config_data = {
            "name": "test_scraper",
            "schedule": {"enabled": True, "cron": "0 3 * * *"},
        }
        (tmp_path / "test_scraper.json").write_text(json.dumps(config_data))

        scheduler = Scheduler()
        scheduler.load_schedules()

        assert "test_scraper" in scheduler._jobs

    @patch("app.orchestrator.scheduler.Config")
    def test_skips_template_json(self, mock_config, tmp_path):
        """template.json is always skipped."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path

        (tmp_path / "template.json").write_text(json.dumps({
            "name": "template",
            "schedule": {"enabled": True, "cron": "0 0 * * *"},
        }))

        scheduler = Scheduler()
        scheduler.load_schedules()

        assert "template" not in scheduler._jobs

    @patch("app.orchestrator.scheduler.Config")
    def test_handles_invalid_json(self, mock_config, tmp_path):
        """Invalid JSON files are skipped gracefully."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path

        (tmp_path / "broken.json").write_text("{invalid json")

        scheduler = Scheduler()
        # Should not raise
        scheduler.load_schedules()

        assert len(scheduler._jobs) == 0

    @patch("app.orchestrator.scheduler.Config")
    def test_skips_disabled_schedules(self, mock_config, tmp_path):
        """Schedules with enabled=False are skipped."""
        mock_config.SCRAPERS_CONFIG_DIR = tmp_path

        (tmp_path / "disabled.json").write_text(json.dumps({
            "name": "disabled_scraper",
            "schedule": {"enabled": False, "cron": "0 0 * * *"},
        }))

        scheduler = Scheduler()
        scheduler.load_schedules()

        assert "disabled_scraper" not in scheduler._jobs
