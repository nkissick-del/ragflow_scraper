"""
Shared helper for constructing runnable scraper/pipeline objects.

Eliminates duplicated construction logic between the web UI and API
blueprints.  Also used by Redis-based dispatch (Phase 3) to
reconstruct runnables from serialised job descriptors.
"""

from __future__ import annotations

import json as json_mod
from typing import Any, Optional

from app.config import Config


def create_runnable(
    scraper_name: str,
    *,
    dry_run: bool = False,
    max_pages: Optional[int] = None,
    preview: bool = False,
) -> Any:
    """Build a runnable object (scraper or pipeline) for a job.

    Dry-run / preview jobs return a raw scraper.
    Real runs return a Pipeline wrapping the scraper.

    Args:
        scraper_name: Registered scraper name.
        dry_run: If True, return raw scraper (no pipeline).
        max_pages: Page limit passed to both scraper and pipeline.
        preview: If True, treat as dry-run (raw scraper).

    Returns:
        An object with a callable ``run()`` method.
    """
    from app.scrapers import ScraperRegistry

    if dry_run or preview:
        return ScraperRegistry.get_scraper(
            scraper_name, dry_run=True, max_pages=max_pages,
        )

    # Real run — wrap in Pipeline
    from app.orchestrator.pipeline import Pipeline

    config_path = Config.SCRAPERS_CONFIG_DIR / f"{scraper_name}.json"
    scraper_config: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                scraper_config = json_mod.load(f)
        except json_mod.JSONDecodeError:
            pass  # Use defaults when config is invalid

    return Pipeline(
        scraper_name=scraper_name,
        max_pages=max_pages,
        upload_to_ragflow=scraper_config.get("upload_to_ragflow", True),
        upload_to_paperless=scraper_config.get("upload_to_paperless", True),
        verify_document_timeout=scraper_config.get(
            "verify_document_timeout", 60
        ),
    )
