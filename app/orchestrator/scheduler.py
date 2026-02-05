"""
Simple scheduler for running scrapers on a schedule.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Optional

import schedule  # type: ignore[import-untyped]

from app.config import Config
from app.utils import get_logger
from app.utils.logging_config import log_exception, log_event


class Scheduler:
    """
    Simple Python scheduler for running scrapers.

    Uses the 'schedule' library for cron-like scheduling.
    Runs in a background thread.
    """

    def __init__(self):
        """Initialize the scheduler."""
        self.logger = get_logger("scheduler")
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._jobs: dict[str, schedule.Job] = {}

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
        Add a schedule for a scraper.

        Args:
            scraper_name: Name of the scraper
            cron: Cron-like expression (simplified)

        Supported cron formats:
            - "0 2 * * *" - Daily at 2 AM
            - "0 0 * * 0" - Weekly on Sunday at midnight
            - "0 */6 * * *" - Every 6 hours
            - "*/30 * * * *" - Every 30 minutes
        """
        # Remove existing schedule if any
        self.remove_schedule(scraper_name)

        job = self._parse_cron_and_schedule(scraper_name, cron)
        if job:
            self._jobs[scraper_name] = job
            log_event(
                self.logger,
                "info",
                "scheduler.job.scheduled",
                scraper=scraper_name,
                cron=cron,
            )

    def _parse_cron_and_schedule(
        self,
        scraper_name: str,
        cron: str,
    ) -> Optional[schedule.Job]:
        """Parse a cron expression and create a schedule job."""
        parts = cron.split()
        if len(parts) != 5:
            self.logger.error(f"Invalid cron expression: {cron}")
            return None

        minute, hour, day, month, weekday = parts

        def run_scraper():
            self._run_scraper(scraper_name)

        try:
            # Handle common patterns
            if minute.startswith("*/"):
                # Every N minutes
                interval = int(minute[2:])
                return schedule.every(interval).minutes.do(run_scraper)

            elif hour.startswith("*/"):
                # Every N hours
                interval = int(hour[2:])
                return schedule.every(interval).hours.do(run_scraper)

            elif weekday != "*":
                # Weekly on specific day
                days = {
                    "0": schedule.every().sunday,
                    "1": schedule.every().monday,
                    "2": schedule.every().tuesday,
                    "3": schedule.every().wednesday,
                    "4": schedule.every().thursday,
                    "5": schedule.every().friday,
                    "6": schedule.every().saturday,
                }
                time_str = f"{int(hour):02d}:{int(minute):02d}"
                day_scheduler = days.get(weekday, schedule.every().sunday)
                return day_scheduler.at(time_str).do(run_scraper)

            elif day != "*":
                # Monthly on specific day (simplified: run daily and check)
                def check_and_run():
                    if datetime.now().day == int(day):
                        run_scraper()

                time_str = f"{int(hour):02d}:{int(minute):02d}"
                return schedule.every().day.at(time_str).do(check_and_run)

            else:
                # Daily at specific time
                time_str = f"{int(hour):02d}:{int(minute):02d}"
                return schedule.every().day.at(time_str).do(run_scraper)

        except Exception as e:
            self.logger.error(f"Failed to parse cron '{cron}': {e}")
            return None

    def _run_scraper(self, scraper_name: str):
        """Run a scraper (called by scheduler)."""
        log_event(self.logger, "info", "scheduler.run.start", scraper=scraper_name)

        try:
            # Use Pipeline to handle scraping + upload + parsing
            from app.orchestrator.pipeline import run_pipeline

            # Run pipeline (scraper -> paperless -> ragflow)
            result = run_pipeline(
                scraper_name=scraper_name,
                upload_to_ragflow=True,  # Default to True from config
                upload_to_paperless=True,  # Default to True
                verify_document_timeout=60,  # Standard timeout
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
        if scraper_name in self._jobs:
            schedule.cancel_job(self._jobs[scraper_name])
            del self._jobs[scraper_name]
            self.logger.info(f"Removed schedule for {scraper_name}")

    def clear_all(self):
        """Clear all schedules."""
        schedule.clear()
        self._jobs.clear()
        self.logger.info("Cleared all schedules")

    def start(self):
        """Start the scheduler in a background thread."""
        if self._running:
            self.logger.warning("Scheduler is already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
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
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log_event(self.logger, "info", "scheduler.stopped")

    def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            schedule.run_pending()
            time.sleep(1)

    def get_next_runs(self) -> dict[str, Optional[datetime]]:
        """Get the next scheduled run time for each scraper."""
        result = {}
        for name, job in self._jobs.items():
            next_run = job.next_run
            result[name] = next_run
        return result

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "job_count": len(self._jobs),
            "jobs": [
                {
                    "name": name,
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                }
                for name, job in self._jobs.items()
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
