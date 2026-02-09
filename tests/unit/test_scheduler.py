"""Tests for Scheduler resilience."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

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
