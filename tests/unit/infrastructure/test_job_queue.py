"""Tests for JobQueue."""

from __future__ import annotations

import pytest
from unittest.mock import Mock

from app.web.job_queue import JobQueue


class TestJobQueue:
    """JobQueue unit tests."""

    def setup_method(self):
        """Create a fresh JobQueue for each test with daemon=True for easy cleanup."""
        self.queue = JobQueue(daemon=True)

    def test_enqueue_success(self):
        """Enqueuing a job should store it and mark as queued."""
        scraper = Mock()
        scraper.name = "test_scraper"

        self.queue.enqueue("test_scraper", scraper, dry_run=True, max_pages=5)

        job = self.queue.get("test_scraper")
        assert job is not None
        assert job.scraper_name == "test_scraper"
        assert job.dry_run is True
        assert job.max_pages == 5

    def test_enqueue_prevents_duplicate(self):
        """Enqueuing when already running should raise ValueError."""
        import time
        
        scraper = Mock()
        scraper.name = "test_scraper"
        
        # Make scraper.run() sleep to keep job active
        def slow_run():
            time.sleep(0.5)
            return None
        scraper.run = slow_run

        self.queue.enqueue("test_scraper", scraper)

        # Try to enqueue before first job finishes
        with pytest.raises(ValueError, match="already has an active job"):
            self.queue.enqueue("test_scraper", scraper)

    def test_status_queued_when_enqueued(self):
        """Status should be 'queued' when enqueued."""
        scraper = Mock()
        scraper.name = "test_scraper"
        self.queue.enqueue("test_scraper", scraper)

        status = self.queue.status("test_scraper")
        assert status == "queued"

    def test_status_idle_when_no_job(self):
        """Status should be 'idle' when no job exists."""
        status = self.queue.status("nonexistent")
        assert status == "idle"

    def test_get_nonexistent_returns_none(self):
        """Getting a nonexistent job should return None."""
        job = self.queue.get("nonexistent")
        assert job is None

    def test_cancel_running_job(self):
        """Cancelling a running job should mark it as cancelling."""
        scraper = Mock()
        scraper.name = "test_scraper"
        self.queue.enqueue("test_scraper", scraper)

        job = self.queue.get("test_scraper")

        result = self.queue.cancel("test_scraper")
        assert result is True
        assert job.status in ("cancelling", "cancelled")

    def test_cancel_nonexistent_job_returns_false(self):
        """Cancelling a nonexistent job should return False."""
        result = self.queue.cancel("nonexistent")
        assert result is False

    def test_drop_removes_job(self):
        """Dropping a job should remove it from queue if finished."""
        scraper = Mock()
        scraper.name = "test_scraper"
        scraper.run = Mock(return_value=None)  # Mock run to return quickly
        self.queue.enqueue("test_scraper", scraper)

        job = self.queue.get("test_scraper")
        assert job is not None

        # Manually mark job as finished (simulate execution completion)
        job.status = "completed"
        job.completed_at = "2024-01-01T00:00:00"

        self.queue.drop("test_scraper")

        assert self.queue.get("test_scraper") is None

    def test_multiple_jobs_isolated(self):
        """Multiple jobs should not interfere with each other."""
        scraper1 = Mock()
        scraper1.name = "scraper1"

        scraper2 = Mock()
        scraper2.name = "scraper2"

        self.queue.enqueue("scraper1", scraper1)
        self.queue.enqueue("scraper2", scraper2)

        job1 = self.queue.get("scraper1")
        job2 = self.queue.get("scraper2")

        assert job1.scraper_name == "scraper1"
        assert job2.scraper_name == "scraper2"
        assert self.queue.status("scraper1") == "queued"
        assert self.queue.status("scraper2") == "queued"

    def test_job_preview_flag(self):
        """Preview flag should be stored and accessible."""
        scraper = Mock()
        scraper.name = "test_scraper"

        self.queue.enqueue("test_scraper", scraper, preview=True, dry_run=True)

        job = self.queue.get("test_scraper")
        assert job.preview is True

    def test_job_error_tracking(self):
        """Jobs should track errors."""
        scraper = Mock()
        scraper.name = "test_scraper"

        self.queue.enqueue("test_scraper", scraper)
        job = self.queue.get("test_scraper")

        assert job.error is None

        job.error = "Test error"

        assert job.error == "Test error"

    def test_execute_captures_full_traceback(self):
        """Failed job should capture full traceback, not just str(exc)."""
        import time

        def failing_run():
            raise RuntimeError("something broke")

        scraper = Mock()
        scraper.name = "fail_scraper"
        scraper.run = failing_run

        job = self.queue.enqueue("fail_scraper", scraper)

        # Wait for execution
        time.sleep(1.0)

        assert job.status == "failed"
        assert job.error is not None
        assert "Traceback" in job.error
        assert "RuntimeError" in job.error
        assert "something broke" in job.error

    def test_job_result_tracking(self):
        """Jobs should track results."""
        scraper = Mock()
        scraper.name = "test_scraper"

        self.queue.enqueue("test_scraper", scraper)
        job = self.queue.get("test_scraper")

        assert job.result is None

        mock_result = Mock()
        job.result = mock_result

        assert job.result == mock_result


# ── Additional coverage tests ─────────────────────────────────────────


class TestJobQueueEdgeCases:
    """Additional edge case tests for JobQueue."""

    def setup_method(self):
        self.queue = JobQueue(daemon=True)

    def test_enqueue_scraper_without_run_raises(self):
        """Should raise ValueError when scraper has no run attribute."""
        scraper = Mock(spec=[])  # no 'run' attribute
        del scraper.run  # ensure it's truly absent

        with pytest.raises(ValueError, match="missing or has non-callable run"):
            self.queue.enqueue("bad_scraper", scraper)

    def test_enqueue_scraper_with_non_callable_run(self):
        """Should raise ValueError when scraper.run is not callable."""
        scraper = Mock()
        scraper.run = "not a function"

        with pytest.raises(ValueError, match="missing or has non-callable run"):
            self.queue.enqueue("bad_scraper", scraper)

    def test_cancel_when_not_running_returns_false(self):
        """Should return False when cancelling non-existent job."""
        result = self.queue.cancel("nonexistent_scraper")
        assert result is False

    def test_drop_active_job_does_nothing(self):
        """Should not remove active (non-finished) job."""
        import time

        scraper = Mock()
        scraper.name = "active_scraper"

        def slow_run():
            time.sleep(2.0)

        scraper.run = slow_run

        self.queue.enqueue("active_scraper", scraper)
        # Job is still queued/running
        self.queue.drop("active_scraper")

        # Job should still be in the queue
        job = self.queue.get("active_scraper")
        assert job is not None

    def test_drop_nonexistent_job_is_noop(self):
        """Should handle drop of nonexistent job gracefully."""
        self.queue.drop("nonexistent")  # Should not raise
        assert self.queue.get("nonexistent") is None

    def test_status_completed_after_execution(self):
        """Job should persist with 'completed' status after execution."""
        import time

        scraper = Mock()
        scraper.name = "fast_scraper"
        scraper.run = Mock(return_value={"docs": 5})

        self.queue.enqueue("fast_scraper", scraper)

        # Wait for execution
        time.sleep(1.0)

        # Finished jobs persist so the UI/API can poll the result
        job = self.queue.get("fast_scraper")
        assert job is not None
        assert job.status == "completed"
        assert job.result == {"docs": 5}

    def test_preview_job_not_auto_dropped(self):
        """Preview jobs should NOT be auto-dropped after completion."""
        import time

        scraper = Mock()
        scraper.name = "preview_scraper"
        scraper.run = Mock(return_value={"preview": True})

        self.queue.enqueue("preview_scraper", scraper, preview=True)

        time.sleep(1.0)

        job = self.queue.get("preview_scraper")
        # Preview job should still be accessible
        assert job is not None
        assert job.status == "completed"
        assert job.result == {"preview": True}

    def test_job_timestamps_set_on_completion(self):
        """Job should have started_at and completed_at after execution."""
        import time

        scraper = Mock()
        scraper.name = "timed_scraper"
        scraper.run = Mock(return_value=None)

        job = self.queue.enqueue("timed_scraper", scraper, preview=True)

        time.sleep(1.0)

        assert job.started_at is not None
        assert job.completed_at is not None

    def test_shutdown_waits_for_completion(self):
        """Shutdown with wait=True should drain the queue."""

        scraper = Mock()
        scraper.name = "shutdown_test"
        scraper.run = Mock(return_value="done")

        self.queue.enqueue("shutdown_test", scraper, preview=True)
        self.queue.shutdown(wait=True, timeout=5.0)

        job = self.queue.get("shutdown_test")
        assert job is not None
        assert job.is_finished


class TestScraperJobDirectly:
    """Test ScraperJob class directly."""

    def test_is_active_queued(self):
        """Queued job should be active."""
        from app.web.job_queue import ScraperJob

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=Mock(),
        )
        assert job.is_active is True
        assert job.is_finished is False

    def test_is_finished_completed(self):
        """Completed job should be finished."""
        from app.web.job_queue import ScraperJob

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=Mock(),
        )
        job.status = "completed"
        assert job.is_finished is True
        assert job.is_active is False

    def test_is_finished_failed(self):
        """Failed job should be finished."""
        from app.web.job_queue import ScraperJob

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=Mock(),
        )
        job.status = "failed"
        assert job.is_finished is True

    def test_is_finished_cancelled(self):
        """Cancelled job should be finished."""
        from app.web.job_queue import ScraperJob

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=Mock(),
        )
        job.status = "cancelled"
        assert job.is_finished is True

    def test_cancel_calls_scraper_cancel(self):
        """Cancel should call scraper.cancel() if available."""
        from app.web.job_queue import ScraperJob

        scraper = Mock()
        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=scraper,
        )
        job.cancel()
        scraper.cancel.assert_called_once()
        assert job._cancel_requested.is_set()

    def test_cancel_handles_scraper_cancel_exception(self):
        """Cancel should handle exceptions from scraper.cancel()."""
        from app.web.job_queue import ScraperJob

        scraper = Mock()
        scraper.cancel.side_effect = Exception("cancel failed")

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: None,
            scraper=scraper,
        )
        job.cancel()  # Should not raise
        assert job._cancel_requested.is_set()

    def test_execute_cancelled_before_run(self):
        """Execute should skip run if cancelled before start."""
        from app.web.job_queue import ScraperJob

        scraper = Mock()
        run_mock = Mock()

        job = ScraperJob(
            scraper_name="test",
            run_callable=run_mock,
            scraper=scraper,
        )
        job._cancel_requested.set()
        job.execute()

        assert job.status == "cancelled"
        run_mock.assert_not_called()
        assert job.completed_at is not None

    def test_execute_successful_run(self):
        """Execute should run callable and set completed."""
        from app.web.job_queue import ScraperJob

        result_value = {"docs": 5}
        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: result_value,
            scraper=Mock(),
        )
        job.execute()

        assert job.status == "completed"
        assert job.result == result_value
        assert job.started_at is not None
        assert job.completed_at is not None

    def test_execute_failed_run(self):
        """Execute should capture error on exception."""
        from app.web.job_queue import ScraperJob

        def failing():
            raise ValueError("test error")

        job = ScraperJob(
            scraper_name="test",
            run_callable=failing,
            scraper=Mock(),
        )
        job.execute()

        assert job.status == "failed"
        assert job.error is not None
        assert "ValueError" in job.error
        assert "test error" in job.error


class TestJobQueueConcurrency:
    """Test concurrent access patterns."""

    def setup_method(self):
        self.queue = JobQueue(daemon=True)

    def test_different_scrapers_can_run_concurrently(self):
        """Different scrapers should be able to be enqueued."""
        scraper1 = Mock()
        scraper1.name = "s1"

        scraper2 = Mock()
        scraper2.name = "s2"

        self.queue.enqueue("s1", scraper1)
        self.queue.enqueue("s2", scraper2)

        assert self.queue.get("s1") is not None
        assert self.queue.get("s2") is not None

    def test_re_enqueue_after_completion(self):
        """Should allow re-enqueue after job completes."""
        import time

        scraper = Mock()
        scraper.name = "rerun"
        scraper.run = Mock(return_value=None)

        self.queue.enqueue("rerun", scraper, preview=True)
        time.sleep(1.0)

        job = self.queue.get("rerun")
        assert job is not None
        assert job.is_finished

        # Drop the finished job
        self.queue.drop("rerun")

        # Should be able to enqueue again
        self.queue.enqueue("rerun", scraper, preview=True)
        job2 = self.queue.get("rerun")
        assert job2 is not None
