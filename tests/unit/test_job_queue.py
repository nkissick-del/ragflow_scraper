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
