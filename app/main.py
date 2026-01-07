#!/usr/bin/env python3
"""
Main entry point for the PDF Scraper Flask application.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import Config
from app.container import get_container
from app.scrapers import ScraperRegistry
from app.utils import get_logger, setup_logging
from app.web import create_app


def main():
    """Run the Flask application."""
    # Setup logging
    setup_logging(name="scraper", level=Config.LOG_LEVEL)

    logger = get_logger("main")
    container = get_container()

    # Create Flask app
    app = create_app()

    # Optionally start scheduler
    try:
        settings = container.settings
        scheduler_settings = settings.get_section("scheduler")
        if scheduler_settings.get("enabled"):
            scheduler = container.scheduler
            scheduler.load_schedules()
            scheduler.start()
            logger.info("Scheduler enabled; loaded schedules and started background loop")

            if scheduler_settings.get("run_on_startup"):
                logger.info("Scheduler run_on_startup enabled; triggering all scrapers once")
                for scraper_name in ScraperRegistry.get_scraper_names():
                    scheduler.run_now(scraper_name)
    except Exception as exc:  # Keep the app booting even if scheduler fails
        logger.error(f"Failed to initialize scheduler: {exc}")

    # Run the development server
    print(f"\n{'=' * 60}")
    print("PDF Scraper Web Interface")
    print(f"{'=' * 60}")
    print(f"Running on: http://{Config.HOST}:{Config.PORT}")
    print(f"Debug mode: {'enabled' if Config.DEBUG else 'disabled'}")
    print(f"{'=' * 60}\n")

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )


if __name__ == "__main__":
    main()
