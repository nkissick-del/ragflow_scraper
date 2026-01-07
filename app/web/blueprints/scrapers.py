"""Scraper UI and control endpoints."""

from __future__ import annotations

from datetime import datetime
from flask import Blueprint, render_template, request, jsonify

from app.config import Config
from app.scrapers import ScraperRegistry
from app.utils import get_logger
from app.utils.logging_config import log_event, log_exception
from app.web.helpers import (
    build_ragflow_options,
    build_scraper_metadata,
    get_scraper_status,
    load_scraper_configs,
)
from app.web.runtime import container, job_queue

bp = Blueprint("scrapers", __name__)
logger = get_logger("web.scrapers")


@bp.route("/")
def index():
    scrapers = ScraperRegistry.list_scrapers()
    for scraper in scrapers:
        state = container.state_tracker(scraper["name"])
        info = state.get_last_run_info()
        scraper["last_run"] = info.get("last_updated")
        scraper["processed_count"] = info.get("processed_count", 0)
        scraper["status"] = get_scraper_status(scraper["name"])

    log_event(logger, "info", "ui.page.index", scraper_count=len(scrapers))
    return render_template("index.html", scrapers=scrapers)


@bp.route("/scrapers")
def scrapers_page():
    scrapers = ScraperRegistry.list_scrapers()
    load_scraper_configs(scrapers)

    ragflow_options = build_ragflow_options(logger)

    log_event(
        logger,
        "info",
        "ui.page.scrapers",
        scraper_count=len(scrapers),
        ragflow_models=len(ragflow_options.get("embedding_providers", {})),
    )
    return render_template(
        "scrapers.html",
        scrapers=scrapers,
        config=Config,
        ragflow_options=ragflow_options,
    )


@bp.route("/scrapers/<name>/status")
def scraper_status(name):
    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        log_event(logger, "warning", "scraper.status.unknown", scraper=name)
        return render_template(
            "components/status-badge.html",
            status="unknown",
            status_text="Unknown",
        )

    status = get_scraper_status(name)
    status_text = status.replace("_", " ").title()

    return render_template(
        "components/status-badge.html",
        scraper_name=name,
        status=status,
        status_text=status_text,
    )


@bp.route("/scrapers/<name>/run", methods=["POST"])
def run_scraper(name):
    dry_run = request.form.get("dry_run") == "true"
    max_pages = request.form.get("max_pages", type=int)

    scraper = ScraperRegistry.get_scraper(name, dry_run=dry_run, max_pages=max_pages or 1 if dry_run else None)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    try:
        job_queue.enqueue(name, scraper, dry_run=dry_run, max_pages=max_pages)
    except ValueError:
        return render_template(
            "components/scraper-card.html",
            scraper=ScraperRegistry.get_scraper_class(name).get_metadata(),
            status="running",
            message="Already queued or running",
        )

    log_event(
        logger,
        "info",
        "scraper.run.requested",
        scraper=name,
        dry_run=dry_run,
        max_pages=max_pages,
    )

    metadata = ScraperRegistry.get_scraper_class(name).get_metadata()
    state = container.state_tracker(name)
    metadata["state"] = state.get_last_run_info()
    metadata["status"] = job_queue.status(name)
    metadata["dry_run"] = dry_run

    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/scrapers/<name>/cancel", methods=["POST"])
def cancel_scraper(name):
    if not job_queue.cancel(name):
        return render_template(
            "components/status-badge.html",
            scraper_name=name,
            status="idle",
            status_text="Not Running",
        )

    log_event(logger, "warning", "scraper.cancel.requested", scraper=name)
    return render_template(
        "components/status-badge.html",
        scraper_name=name,
        status="cancelling",
        status_text="Cancelling...",
    )


@bp.route("/scrapers/<name>/preview", methods=["POST"])
def preview_scraper(name):
    max_pages = request.form.get("max_pages", 1, type=int)

    scraper = ScraperRegistry.get_scraper(name, dry_run=True, max_pages=max_pages)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    try:
        job_queue.enqueue(name, scraper, preview=True, dry_run=True, max_pages=max_pages)
    except ValueError:
        return '<div class="preview-error">Scraper is currently running. Please wait.</div>'

    log_event(logger, "info", "scraper.preview.requested", scraper=name, max_pages=max_pages)

    return render_template(
        "components/preview-loading.html",
        scraper_name=name,
    )


@bp.route("/scrapers/<name>/preview/status")
def preview_status(name):
    job = job_queue.get(name)
    if not job or not job.preview:
        return '<div class="preview-error">No preview running.</div>'

    if job.error:
        job_queue.drop(name)
        return f'<div class="preview-error">Preview failed: {job.error}</div>'

    if job.is_finished and job.result is None:
        job_queue.drop(name)
        return '<div class="preview-error">Preview finished without a result.</div>'

    if job.is_finished and job.result is not None:
        try:
            return render_template(
                "components/preview-results.html",
                scraper_name=name,
                result=job.result,
                documents=job.result.documents,
            )
        finally:
            job_queue.drop(name)

    return render_template(
        "components/preview-loading.html",
        scraper_name=name,
    )


@bp.route("/scrapers/<name>/card")
def scraper_card(name):
    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        return "Not found", 404

    metadata = build_scraper_metadata(name)
    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/scrapers/<name>/ragflow", methods=["POST"])
def save_scraper_ragflow_settings(name):
    settings_mgr = container.settings
    settings = {}

    ingestion_mode = request.form.get(f"ingestion_mode_{name}")
    if ingestion_mode:
        settings["ingestion_mode"] = ingestion_mode

    if request.form.get("chunk_method"):
        settings["chunk_method"] = request.form.get("chunk_method")
    if request.form.get("pdf_parser"):
        settings["pdf_parser"] = request.form.get("pdf_parser")
    if "embedding_model" in request.form:
        settings["embedding_model"] = request.form.get("embedding_model", "")
    if "pipeline_id" in request.form:
        settings["pipeline_id"] = request.form.get("pipeline_id", "")
    if request.form.get("dataset_id"):
        settings["dataset_id"] = request.form.get("dataset_id")

    if settings:
        settings_mgr.set_scraper_ragflow_settings(name, settings)
        logger.info(f"RAGFlow settings for {name} updated: {list(settings.keys())}")

    return '''
        <span class="setting-saved">Saved</span>
    '''


@bp.route("/scrapers/<name>/cloudflare", methods=["POST"])
def toggle_scraper_cloudflare(name):
    """Toggle FlareSolverr/Cloudflare bypass for a specific scraper."""
    settings_mgr = container.settings

    # Check if global FlareSolverr is configured and enabled
    if not Config.FLARESOLVERR_URL:
        return '''
            <span class="toggle-status error">
                FlareSolverr URL not configured
            </span>
        '''

    if not settings_mgr.flaresolverr_enabled:
        return '''
            <span class="toggle-status warning">
                Enable FlareSolverr in Settings first
            </span>
        '''

    # Toggle the setting
    enabled = request.form.get("enabled") == "on"
    settings_mgr.set_scraper_cloudflare_enabled(name, enabled)

    logger.info(f"Cloudflare bypass for {name}: {'enabled' if enabled else 'disabled'}")

    # Return the toggle state feedback
    status_text = "Enabled" if enabled else "Disabled"
    return f'''
        <span class="toggle-status {'enabled' if enabled else 'disabled'}">
            {status_text}
        </span>
    '''
