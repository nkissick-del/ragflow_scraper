"""
Lightweight job queue for scraper runs.

Provides single-worker sequencing, per-scraper exclusivity, and
cancel-aware execution without external dependencies.

Optionally persists job metadata to PostgreSQL via JobStore so that
job history survives container restarts.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, TYPE_CHECKING
import atexit
import sys
import traceback
import types
import weakref

if TYPE_CHECKING:
    from app.services.job_store import JobStore
    from app.services.redis_job_dispatch import RedisJobDispatch


def _safe_result_dict(result: Any) -> Any:
    """Convert a result to a JSON-serialisable dict if it has to_dict()."""
    if result is None:
        return None
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict()
        except Exception:
            pass
    if isinstance(result, dict):
        return result
    return None


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
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

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
            # run_callable() may return a generator (streaming scrapers)
            # or a plain value (pipeline). Consume generators to extract
            # the final ScraperResult from StopIteration.value.
            result_or_gen = self.run_callable()
            if isinstance(result_or_gen, types.GeneratorType):
                # It's a generator — consume it, discard yielded docs
                try:
                    while True:
                        next(result_or_gen)
                except StopIteration as e:
                    self.result = e.value
            else:
                self.result = result_or_gen

            with self._lock:
                # If cancellation was requested mid-run, mark accordingly
                if self._cancel_requested.is_set():
                    self.status = "cancelled"
                else:
                    self.status = "completed"
        except Exception:
            with self._lock:
                self.error = traceback.format_exc()
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

    Worker threads are lazily started on the first enqueue() call to avoid
    the "fork after thread" problem with gunicorn: threads created before
    fork are lost in the child process. Lazy init ensures threads always
    run in the process that actually handles HTTP requests.

    IMPORTANT: This queue uses a non-daemon worker thread. The process will
    block at exit until the queue is explicitly shut down (via shutdown() or
    the atexit handler). If shutdown() is never called, the process may hang.
    """

    def __init__(
        self,
        daemon: bool = False,
        max_workers: int = 1,
        job_store: Optional[JobStore] = None,
        redis_dispatch: Optional[RedisJobDispatch] = None,
    ):
        self._queue: queue.Queue[ScraperJob] = queue.Queue()
        self._jobs: dict[str, ScraperJob] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._workers: list[threading.Thread] = []
        self._daemon = daemon
        self._max_workers = max_workers
        self._started = False
        self._job_store = job_store
        self._redis_dispatch = redis_dispatch
        self._idle_cache: set[str] = set()  # scrapers confirmed idle in store

        try:
            _instances.add(self)
        except Exception:
            # If _instances isn't available for some reason (unlikely), ignore
            pass

    def _ensure_workers_started(self) -> None:
        """Lazily start worker threads on first use.

        Worker threads are NOT started in __init__ because gunicorn forks
        after module import — threads created before the fork are lost in
        the child process. By deferring thread creation to the first
        enqueue() call, the threads are guaranteed to run in the actual
        worker process that handles HTTP requests.
        """
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            for i in range(self._max_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    daemon=self._daemon,
                    name=f"ScraperWorker-{i}",
                )
                t.start()
                self._workers.append(t)
            self._started = True

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
        self._ensure_workers_started()

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
            self._idle_cache.discard(scraper_name)
            self._queue.put(job)

        # Persist to store (outside lock — I/O should not hold the mutex)
        if self._job_store is not None:
            try:
                self._job_store.upsert(
                    job_id=scraper_name,
                    scraper_name=scraper_name,
                    preview=preview,
                    dry_run=dry_run,
                    max_pages=max_pages,
                )
            except Exception:
                pass  # best-effort persistence

        # Publish enqueue event via Redis
        if self._redis_dispatch is not None:
            try:
                self._redis_dispatch.publish_event(
                    "queued", scraper_name,
                    {"preview": preview, "dry_run": dry_run,
                     "max_pages": max_pages},
                )
            except Exception:
                pass

        return job

    def cancel(self, scraper_name: str) -> bool:
        """Request cancellation for a scraper job."""
        with self._lock:
            job = self._jobs.get(scraper_name)
            if not job:
                return False
            job.cancel()

        if self._job_store is not None:
            try:
                self._job_store.update_status(scraper_name, "cancelling")
            except Exception:
                pass

        if self._redis_dispatch is not None:
            try:
                self._redis_dispatch.request_cancel(scraper_name)
                self._redis_dispatch.publish_event("cancelling", scraper_name)
            except Exception:
                pass

        return True

    def status(self, scraper_name: str) -> str:
        with self._lock:
            job = self._jobs.get(scraper_name)
            if job:
                return job.status

        # Skip DB lookup for scrapers already confirmed idle
        if scraper_name in self._idle_cache:
            return "idle"

        # Fall back to persistent store
        if self._job_store is not None:
            try:
                row = self._job_store.get(scraper_name)
                if row:
                    return row["status"]
            except Exception:
                pass

        # Cache the idle result to avoid repeated DB lookups
        self._idle_cache.add(scraper_name)
        return "idle"

    def get(self, scraper_name: str) -> Optional[ScraperJob]:
        with self._lock:
            return self._jobs.get(scraper_name)

    def get_stored(self, scraper_name: str) -> Optional[dict[str, Any]]:
        """Get job data from persistent store (for history after restart)."""
        if self._job_store is None:
            return None
        try:
            return self._job_store.get(scraper_name)
        except Exception:
            return None

    def drop(self, scraper_name: str) -> None:
        """Remove a completed job from the registry."""
        with self._lock:
            job = self._jobs.get(scraper_name)
            if job and job.is_finished:
                self._jobs.pop(scraper_name, None)

        if self._job_store is not None:
            try:
                self._job_store.delete(scraper_name)
            except Exception:
                pass

    def _persist_job_state(self, job: ScraperJob) -> None:
        """Persist current job state to the store (best-effort)."""
        if self._job_store is None:
            return
        try:
            result_dict = _safe_result_dict(job.result)
            self._job_store.update_status(
                job_id=job.scraper_name,
                status=job.status,
                error=job.error,
                result=result_dict,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )
        except Exception:
            pass

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                # Use timeout to allow periodic shutdown checks
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Persist "running" status before execution
            if self._job_store is not None:
                try:
                    self._job_store.update_status(
                        job.scraper_name, "running",
                        started_at=job.started_at or datetime.now().isoformat(),
                    )
                except Exception:
                    pass

            if self._redis_dispatch is not None:
                try:
                    self._redis_dispatch.publish_event("running", job.scraper_name)
                except Exception:
                    pass

            job.execute()

            # Persist final state after execution
            self._persist_job_state(job)

            # Publish completion event + clear cancel flag
            if self._redis_dispatch is not None:
                try:
                    self._redis_dispatch.clear_cancel(job.scraper_name)
                    result_dict = _safe_result_dict(job.result)
                    self._redis_dispatch.publish_event(
                        job.status, job.scraper_name,
                        {"error": job.error, "result": result_dict},
                    )
                except Exception:
                    pass

            # Keep finished jobs in _jobs so the UI/API can poll the
            # result.  They are evicted lazily: either when the same
            # scraper is re-enqueued (the existing check in enqueue),
            # or via explicit drop() calls from preview_status.
            self._queue.task_done()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Gracefully shutdown the worker threads.

        CRITICAL: This must be called before process exit unless you're relying
        on the atexit handler. Without this, the process will block indefinitely
        waiting for the worker threads to terminate.

        Args:
            wait: If True, wait for the queue to be drained before returning.
            timeout: Maximum time to wait for thread completion (in seconds).
                   If timeout expires and thread is still alive, process may hang
                   at exit since this is a non-daemon thread.
        """
        if wait:
            self._queue.join()
        self._shutdown.set()

        for worker in self._workers:
            worker.join(timeout)


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

    During testing (PYTEST_CURRENT_TEST), this handler is a no-op because:
    - Daemon threads auto-cleanup
    - dump_threads() can hang during pytest shutdown
    """
    import os

    # Skip during testing - daemon threads will auto-cleanup
    if os.getenv("PYTEST_CURRENT_TEST"):
        return

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
