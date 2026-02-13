"""Tests for JobQueue generator consumption in ScraperJob.execute()."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.web.job_queue import ScraperJob


def _make_gen(docs, return_value):
    """Helper to create a generator yielding docs and returning a value."""
    for doc in docs:
        yield doc
    return return_value


class TestScraperJobExecuteGenerator:
    def test_consumes_generator(self):
        """execute() consumes generator and extracts return value."""
        result_obj = MagicMock()
        result_obj.status = "completed"
        gen = _make_gen([{"title": "A"}, {"title": "B"}], result_obj)

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: gen,
            scraper=MagicMock(),
        )
        job.execute()

        assert job.status == "completed"
        assert job.result is result_obj

    def test_handles_plain_return(self):
        """execute() still works when run_callable returns a plain value."""
        result_obj = {"status": "completed", "count": 5}

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: result_obj,
            scraper=MagicMock(),
        )
        job.execute()

        assert job.status == "completed"
        assert job.result is result_obj

    def test_generator_with_no_docs(self):
        """execute() handles a generator that yields nothing."""
        result_obj = MagicMock()
        result_obj.status = "completed"
        gen = _make_gen([], result_obj)

        job = ScraperJob(
            scraper_name="test",
            run_callable=lambda: gen,
            scraper=MagicMock(),
        )
        job.execute()

        assert job.status == "completed"
        assert job.result is result_obj

    def test_generator_error_marks_failed(self):
        """execute() marks job as failed if generator raises."""
        def bad_gen():
            yield {"title": "Ok"}
            raise RuntimeError("boom")

        job = ScraperJob(
            scraper_name="test",
            run_callable=bad_gen,
            scraper=MagicMock(),
        )
        job.execute()

        assert job.status == "failed"
        assert "RuntimeError" in job.error

    def test_cancel_before_execute(self):
        """Job cancelled before execute() never runs the callable."""
        called = False

        def track():
            nonlocal called
            called = True
            return MagicMock()

        job = ScraperJob(
            scraper_name="test",
            run_callable=track,
            scraper=MagicMock(),
        )
        job.cancel()
        job.execute()

        assert job.status == "cancelled"
        assert not called
