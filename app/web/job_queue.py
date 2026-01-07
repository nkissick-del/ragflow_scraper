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
import atexit
import sys
import traceback
import weakref


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
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def cancel(self) -> None:
        """Request cancellation; ask scraper to stop if supported."""
        self._cancel_requested.set()
        if hasattr(self.scraper, "cancel"):
            try:
                self.scraper.cancel()
            except Exception:
                # Cancellation best-effort; failures should not crash the queue
                pass
        with self._lock:
            if self.status in {"queued", "running"}:
                self.status = "cancelling"

    def execute(self) -> None:
        """Run the job, honoring cancellation requests."""
        with self._lock:
            if self._cancel_requested.is_set():
                self.status = "cancelled"
                self.completed_at = datetime.now().isoformat()
                return

            self.status = "running"
            self.started_at = datetime.now().isoformat()

        try:
            self.result = self.run_callable()
            with self._lock:
                # If cancellation was requested mid-run, mark accordingly
                if self._cancel_requested.is_set():
                    self.status = "cancelled"
                else:
                    self.status = "completed"
        except Exception as exc:  # pragma: no cover - exceptions recorded in error field
            with self._lock:
                self.error = str(exc)
                self.status = "failed"
        finally:
            with self._lock:
                self.completed_at = datetime.now().isoformat()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self.status in {"queued", "running", "cancelling"}

    @property
    def is_finished(self) -> bool:
        with self._lock:
            return self.status in {"completed", "failed", "cancelled"}


class JobQueue:
    """Single-worker job queue with per-scraper exclusivity.
    
    IMPORTANT: This queue uses a non-daemon worker thread. The process will
    block at exit until the queue is explicitly shut down (via shutdown() or
    the atexit handler). If shutdown() is never called, the process may hang.
    
    The atexit handler provides automatic cleanup for most code paths, but
    explicit shutdown() calls are still recommended for:
    - Web applications (call during app shutdown/teardown)
    - Scripts that need predictable exit timing
    - Testing (via conftest.py fixture)
    """

    def __init__(self):
        self._queue: queue.Queue[ScraperJob] = queue.Queue()
        self._jobs: dict[str, ScraperJob] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        # Worker thread set to daemon=False to ensure graceful shutdown:
        # - Process will block at exit until this thread terminates
        # - atexit handler calls shutdown() to orderly wind down
        # - DO NOT remove this unless shutdown() is guaranteed by callers
        self._worker = threading.Thread(target=self._worker_loop, daemon=False)
        self._worker.start()
        try:
            _instances.add(self)
        except Exception:
            # If _instances isn't available for some reason (unlikely), ignore
            pass

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
        # Validate that scraper has a callable run attribute
        run_callable = getattr(scraper, "run", None)
        if not callable(run_callable):
            raise ValueError(
                f"Scraper {scraper_name} is missing or has non-callable run attribute"
            )
        
        with self._lock:
            existing = self._jobs.get(scraper_name)
            if existing and existing.is_active:
                raise ValueError(f"Scraper {scraper_name} already has an active job")

            job = ScraperJob(
                scraper_name=scraper_name,
                run_callable=run_callable,
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
        while not self._shutdown.is_set():
            try:
                # Use timeout to allow periodic shutdown checks
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            job.execute()
            # Drop completed non-preview jobs immediately; previews are cleaned up by callers
            with job._lock:
                if not job.preview and job.is_finished:
                    with self._lock:
                        self._jobs.pop(job.scraper_name, None)
            self._queue.task_done()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Gracefully shutdown the worker thread.
        
        CRITICAL: This must be called before process exit unless you're relying
        on the atexit handler. Without this, the process will block indefinitely
        waiting for the worker thread to terminate.
        
        Args:
            wait: If True, wait for the queue to be drained before returning.
            timeout: Maximum time to wait for thread completion (in seconds).
                   If timeout expires and thread is still alive, process may hang
                   at exit since this is a non-daemon thread.
        """
        if wait:
            self._queue.join()
        self._shutdown.set()
        self._worker.join(timeout)


# Keep a weak set of JobQueue instances so we can attempt orderly shutdown
# at process exit if callers forget to call `shutdown()`.
_instances: "weakref.WeakSet[JobQueue]" = weakref.WeakSet()


def dump_threads(file=None) -> None:
    """Write a brief thread dump to `file` (defaults to sys.stderr).
    
    Uses sys._current_frames() for stack traces; this is CPython-specific
    and best-effort diagnostics.
    """
    out = file if file is not None else sys.stderr
    try:
        print("--- Thread dump start ---", file=out)
        for t in threading.enumerate():
            print(f"Thread: {t.name} (daemon={t.daemon})", file=out)
        frames = sys._current_frames()
        for tid, frame in frames.items():
            print(f"\nThread id: {tid}", file=out)
            traceback.print_stack(frame, file=out)
        print("--- Thread dump end ---", file=out)
    except Exception:
        # Best-effort diagnostics; never raise from dump
        try:
            traceback.print_exc(file=out)
        except Exception:
            pass


def _shutdown_all_queues() -> None:
    """Attempt orderly shutdown of all known JobQueue instances on process exit.

    This will join worker threads with a short timeout and dump thread
    information for diagnostics if any threads remain.
    """
    try:
        for q in list(_instances):
            try:
                q.shutdown(wait=False, timeout=1.0)
            except Exception:
                pass

        # Dump thread info only if worker threads are still alive
        alive_workers = [
            t for t in threading.enumerate()
            if t.name != 'MainThread' and not t.daemon
        ]
        if alive_workers:
            try:
                dump_threads()
            except Exception:
                pass
    except Exception:
        pass


# Register shutdown handler at process exit
atexit.register(_shutdown_all_queues)
