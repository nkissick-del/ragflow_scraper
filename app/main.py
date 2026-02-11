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

from app.config import Config  # noqa: E402
from app.container import get_container  # noqa: E402
from app.scrapers import ScraperRegistry  # noqa: E402
from app.utils import get_logger, setup_logging  # noqa: E402
from app.web import create_app  # noqa: E402


def main():
    """Run the Flask application."""
    # Initialize configuration (before logging is set up)
    try:
        Config.ensure_directories()
        Config.validate()
    except Exception as exc:
        # Logging not yet configured, so use stderr for diagnostics
        print(
            f"FATAL: Configuration initialization failed: {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        raise

    # Setup logging
    setup_logging(name="scraper", level=Config.LOG_LEVEL)

    logger = get_logger("main")
    container = get_container()

    # Ensure pgvector schema + AnythingLLM view exist (if configured)
    if Config.DATABASE_URL:
        try:
            pgvector = container.pgvector_client
            pgvector.ensure_schema()
            logger.info(
                "pgvector schema ensured (table + view '%s')",
                Config.ANYTHINGLLM_VIEW_NAME,
            )
        except Exception:
            logger.exception("Failed to initialize pgvector schema (non-fatal)")

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
            logger.info(
                "Scheduler enabled; loaded schedules and started background loop"
            )

            if scheduler_settings.get("run_on_startup"):
                logger.info(
                    "Scheduler run_on_startup enabled; triggering all scrapers once"
                )
                for scraper_name in ScraperRegistry.get_scraper_names():
                    scheduler.run_now(scraper_name)
    except Exception:  # Keep the app booting even if scheduler fails
        logger.exception("Failed to initialize scheduler")

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
