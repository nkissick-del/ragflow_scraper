"""
Lightweight job queue for scraper runs.

Provides single-worker sequencing, per-scraper exclusivity, and
cancel-aware execution without external dependencies.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


@dataclass
class ScraperJob:
    """Represents a queued scraper task."""

    scraper_name: str
    run_callable: Callable[[], Any]
    scraper: Any
    preview: bool = False
    dry_run: bool = False
    max_pages: Optional[int] = None
    status: str = "queued"
    error: Optional[str] = None
    result: Any = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    _cancel_requested: threading.Event = field(default_factory=threading.Event, init=False)

    def cancel(self) -> None:
        """Request cancellation; ask scraper to stop if supported."""
        self._cancel_requested.set()
        if hasattr(self.scraper, "cancel"):
            try:
                self.scraper.cancel()
            except Exception:
                # Cancellation best-effort; failures should not crash the queue
                pass
        if self.status in {"queued", "running"}:
            self.status = "cancelling"

    def execute(self) -> None:
        """Run the job, honoring cancellation requests."""
        if self._cancel_requested.is_set():
            self.status = "cancelled"
            self.completed_at = datetime.now().isoformat()
            return

        self.status = "running"
        self.started_at = datetime.now().isoformat()

        try:
            self.result = self.run_callable()
            # If cancellation was requested mid-run, mark accordingly
            if self._cancel_requested.is_set():
                self.status = "cancelled"
            else:
                self.status = "completed"
        except Exception as exc:  # pragma: no cover - passthrough for caller logging
            self.error = str(exc)
            self.status = "failed"
        finally:
            self.completed_at = datetime.now().isoformat()

    @property
    def is_active(self) -> bool:
        return self.status in {"queued", "running", "cancelling"}

    @property
    def is_finished(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}


class JobQueue:
    """Single-worker job queue with per-scraper exclusivity."""

    def __init__(self):
        self._queue: queue.Queue[ScraperJob] = queue.Queue()
        self._jobs: dict[str, ScraperJob] = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def enqueue(
        self,
        scraper_name: str,
        scraper: Any,
        *,
        preview: bool = False,
        dry_run: bool = False,
        max_pages: Optional[int] = None,
    ) -> ScraperJob:
        """Queue a scraper job; refuses if one is already active for that scraper."""
        with self._lock:
            existing = self._jobs.get(scraper_name)
            if existing and existing.is_active:
                raise ValueError(f"Scraper {scraper_name} already has an active job")

            job = ScraperJob(
                scraper_name=scraper_name,
                run_callable=scraper.run,
                scraper=scraper,
                preview=preview,
                dry_run=dry_run,
                max_pages=max_pages,
            )
            self._jobs[scraper_name] = job
            self._queue.put(job)
            return job

    def cancel(self, scraper_name: str) -> bool:
        """Request cancellation for a scraper job."""
        with self._lock:
            job = self._jobs.get(scraper_name)
            if not job:
                return False
            job.cancel()
            return True

    def status(self, scraper_name: str) -> str:
        with self._lock:
            job = self._jobs.get(scraper_name)
            return job.status if job else "idle"

    def get(self, scraper_name: str) -> Optional[ScraperJob]:
        with self._lock:
            return self._jobs.get(scraper_name)

    def drop(self, scraper_name: str) -> None:
        """Remove a completed job from the registry."""
        with self._lock:
            job = self._jobs.get(scraper_name)
            if job and job.is_finished:
                self._jobs.pop(scraper_name, None)

    def _worker_loop(self) -> None:
        while True:
            job = self._queue.get()
            job.execute()
            # Drop completed non-preview jobs immediately; previews are cleaned up by callers
            if not job.preview and job.is_finished:
                with self._lock:
                    self._jobs.pop(job.scraper_name, None)
            self._queue.task_done()
