"""
Scheduler for running scrapers on a schedule using APScheduler.

Uses CronTrigger for real cron expressions and optional SQLAlchemy job store
for persistent jobs across restarts.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED  # type: ignore[import-untyped]

from app.config import Config
from app.utils import get_logger
from app.utils.logging_config import log_exception, log_event


class Scheduler:
    """
    APScheduler-based scheduler for running scrapers.

    Uses CronTrigger for real cron expressions.
    Optionally persists jobs to PostgreSQL via SQLAlchemyJobStore.
    """

    def __init__(self):
        """Initialize the scheduler."""
        self.logger = get_logger("scheduler")
        self._scheduler: Optional[BackgroundScheduler] = None
        self._init_lock = threading.Lock()

    def _get_scheduler(self) -> BackgroundScheduler:
        """Get or create the APScheduler instance (lazy, thread-safe)."""
        if self._scheduler is not None:
            return self._scheduler

        with self._init_lock:
            if self._scheduler is not None:
                return self._scheduler

            jobstores = {}
            # Use SQLAlchemy job store when DATABASE_URL is configured
            if Config.DATABASE_URL:
                try:
                    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore[import-untyped]
                    jobstores["default"] = SQLAlchemyJobStore(
                        url=Config.DATABASE_URL,
                        tablename="apscheduler_jobs",
                    )
                    self.logger.info("Using SQLAlchemy job store (persistent)")
                except Exception as e:
                    self.logger.warning(
                        f"SQLAlchemy job store unavailable, using memory: {e}"
                    )

            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 3600,
                },
            )
            self._scheduler.add_listener(
                self._job_event_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
            )
            return self._scheduler

    def _job_event_listener(self, event):
        """Log job execution events."""
        if event.exception:
            self.logger.error(
                f"Scheduled job failed: {event.job_id} — {event.exception}"
            )
        else:
            self.logger.info(f"Scheduled job completed: {event.job_id}")

    def load_schedules(self):
        """Load schedules from scraper configuration files."""
        log_event(self.logger, "info", "scheduler.load.start")

        for config_file in Config.SCRAPERS_CONFIG_DIR.glob("*.json"):
            if config_file.name == "template.json":
                continue

            try:
                with open(config_file) as f:
                    config = json.load(f)

                scraper_name = config.get("name")
                schedule_config = config.get("schedule", {})

                if schedule_config.get("enabled"):
                    cron = schedule_config.get("cron", "0 0 * * *")
                    self.add_scraper_schedule(scraper_name, cron)

            except Exception as e:
                log_exception(
                    self.logger,
                    e,
                    "scheduler.load.error",
                    config=str(config_file),
                )

    def add_scraper_schedule(self, scraper_name: str, cron: str):
        """
        Add a schedule for a scraper using a real cron expression.

        Args:
            scraper_name: Name of the scraper
            cron: Standard 5-field cron expression (minute hour day month weekday)
        """
        # Remove existing schedule if any
        self.remove_schedule(scraper_name)

        parts = cron.split()
        if len(parts) != 5:
            self.logger.error(f"Invalid cron expression: {cron}")
            return

        try:
            trigger = CronTrigger.from_crontab(cron)
            scheduler = self._get_scheduler()
            scheduler.add_job(
                self._run_scraper,
                trigger=trigger,
                args=[scraper_name],
                id=f"scraper_{scraper_name}",
                name=f"Scraper: {scraper_name}",
                replace_existing=True,
            )
            log_event(
                self.logger,
                "info",
                "scheduler.job.scheduled",
                scraper=scraper_name,
                cron=cron,
            )
        except Exception as e:
            self.logger.error(f"Failed to schedule '{scraper_name}' with cron '{cron}': {e}")

    def _run_scraper(self, scraper_name: str):
        """Run a scraper (called by scheduler)."""
        log_event(self.logger, "info", "scheduler.run.start", scraper=scraper_name)

        try:
            # Load scraper config to get upload flags
            config_path = Config.get_scraper_config_path(scraper_name)
            scraper_config = {}
            if config_path.exists():
                with open(config_path) as f:
                    scraper_config = json.load(f)

            # Use Pipeline to handle scraping + upload + parsing
            from app.orchestrator.pipeline import run_pipeline

            result = run_pipeline(
                scraper_name=scraper_name,
                upload_to_ragflow=scraper_config.get("upload_to_ragflow", True),
                upload_to_paperless=scraper_config.get("upload_to_paperless", True),
                verify_document_timeout=scraper_config.get(
                    "verify_document_timeout", 60
                ),
            )

            log_event(
                self.logger,
                "info",
                "scheduler.run.complete",
                scraper=scraper_name,
                downloaded=result.downloaded_count,
                failed=result.failed_count,
                status=result.status,
            )
        except Exception as e:
            log_exception(
                self.logger,
                e,
                "scheduler.run.failed",
                scraper=scraper_name,
            )

    def remove_schedule(self, scraper_name: str):
        """Remove a schedule for a scraper."""
        scheduler = self._get_scheduler()
        job_id = f"scraper_{scraper_name}"
        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                self.logger.info(f"Removed schedule for {scraper_name}")
        except Exception:
            pass

    def clear_all(self):
        """Clear all schedules."""
        scheduler = self._get_scheduler()
        scheduler.remove_all_jobs()
        self.logger.info("Cleared all schedules")

    def start(self):
        """Start the scheduler."""
        scheduler = self._get_scheduler()
        if scheduler.running:
            self.logger.warning("Scheduler is already running")
            return

        scheduler.start()
        log_event(self.logger, "info", "scheduler.started")

    def run_now(self, scraper_name: str):
        """Trigger a scraper immediately without waiting for its next schedule."""
        thread = threading.Thread(
            target=self._run_scraper,
            args=(scraper_name,),
            daemon=True,
        )
        thread.start()
        return thread

    def stop(self):
        """Stop the scheduler."""
        scheduler = self._get_scheduler()
        if scheduler.running:
            scheduler.shutdown(wait=False)
        log_event(self.logger, "info", "scheduler.stopped")

    def get_next_runs(self) -> dict[str, Optional[datetime]]:
        """Get the next scheduled run time for each scraper."""
        scheduler = self._get_scheduler()
        result = {}
        for job in scheduler.get_jobs():
            name = job.id.replace("scraper_", "", 1)
            result[name] = getattr(job, "next_run_time", None)
        return result

    def get_status(self) -> dict:
        """Get scheduler status."""
        scheduler = self._get_scheduler()
        return {
            "running": scheduler.running,
            "job_count": len(scheduler.get_jobs()),
            "jobs": [
                {
                    "name": job.id.replace("scraper_", "", 1),
                    "next_run": nrt.isoformat() if (nrt := getattr(job, "next_run_time", None)) else None,
                }
                for job in scheduler.get_jobs()
            ],
        }


# Global scheduler instance
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
