"""Helpers for web blueprints."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.config import Config
from app.scrapers import ScraperRegistry
from app.utils.logging_config import log_exception
from app.web.runtime import container, job_queue

_SENTINEL: Any = object()  # distinguishes "not passed" from None


def get_scraper_status(name: str, *, info: Optional[dict] = _SENTINEL) -> str:
    """Resolve scraper status using in-flight jobs then persisted state.

    Args:
        name: Scraper name.
        info: Pre-fetched ``get_last_run_info()`` dict.  Pass explicitly
              to avoid a redundant DB round-trip when the caller already
              has the data.  ``None`` means "no data" (different from
              *not passed*).
    """
    in_flight = job_queue.status(name)
    if in_flight != "idle":
        return in_flight

    if info is _SENTINEL:
        state = container.state_tracker(name)
        info = state.get_last_run_info()

    if not info or not info.get("last_updated"):
        return "idle"

    stats = info.get("statistics", {})
    if stats.get("total_failed", 0) > 0:
        return "error"

    return "ready"


def load_scraper_configs(scrapers: list[dict]) -> None:
    """Attach config and state to scraper metadata."""
    settings_mgr = container.settings

    for scraper in scrapers:
        config_path = Config.SCRAPERS_CONFIG_DIR / f"{scraper['name']}.json"
        if config_path.exists():
            with open(config_path) as f:
                scraper["config"] = json.load(f)
        else:
            scraper["config"] = {}

        state = container.state_tracker(scraper["name"])
        scraper["state"] = state.get_last_run_info()
        scraper["status"] = get_scraper_status(scraper["name"], info=scraper["state"])

        scraper["cloudflare_enabled"] = settings_mgr.get_scraper_cloudflare_enabled(scraper["name"])

        scraper_defaults = {
            "default_chunk_method": scraper.get("default_chunk_method", "naive"),
            "default_parser": scraper.get("default_parser", "DeepDOC"),
        }
        scraper["ragflow_settings"] = settings_mgr.get_scraper_ragflow_settings(
            scraper["name"], scraper_defaults=scraper_defaults
        )


def build_ragflow_options(logger) -> dict[str, Any]:
    """Fetch ragflow options for dropdowns, handling optional session models."""
    empty_options: dict[str, Any] = {
        "chunk_methods": [],
        "pdf_parsers": [],
        "pipelines": [],
        "embedding_providers": {},
    }

    try:
        ragflow_client = container.ragflow_client
    except ValueError:
        # RAGFlow not configured — return empty options so the page still renders
        return empty_options

    options = {
        "chunk_methods": ragflow_client.list_chunk_methods(),
        "pdf_parsers": ragflow_client.list_pdf_parsers(),
        "pipelines": ragflow_client.list_ingestion_pipelines(),
        "embedding_providers": {},
    }

    if ragflow_client.session_configured:
        try:
            models = ragflow_client.list_embedding_models()
            for model in models:
                provider = model.get("provider", "Unknown")
                options["embedding_providers"].setdefault(provider, []).append(model)
        except Exception as exc:
            log_exception(logger, exc, "ragflow.models.fetch_failed", page="scrapers")

    return options


def build_scraper_metadata(scraper_name: str) -> dict:
    scraper_class = ScraperRegistry.get_scraper_class(scraper_name)
    if not scraper_class:
        return {}
    metadata = scraper_class.get_metadata()
    state = container.state_tracker(scraper_name)
    metadata["state"] = state.get_last_run_info()
    metadata["status"] = get_scraper_status(scraper_name, info=metadata["state"])
    return metadata
