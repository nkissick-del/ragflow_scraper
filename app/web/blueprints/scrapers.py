"""Scraper UI and control endpoints."""

from __future__ import annotations

import re
from flask import Blueprint, render_template, request, jsonify
from markupsafe import escape

from app.config import Config
from app.scrapers import ScraperRegistry
from app.services.ragflow_client import CHUNK_METHODS, PDF_PARSERS
from app.utils import get_logger
from app.utils.logging_config import log_event
from app.web.limiter import limiter
from app.web.helpers import (
    build_ragflow_options,
    build_scraper_metadata,
    get_scraper_status,
    load_scraper_configs,
)
from app.web.runtime import container, job_queue

bp = Blueprint("scrapers", __name__)
logger = get_logger("web.scrapers")


def _bulk_last_run_info(names: list[str]) -> dict[str, dict | None]:
    """Fetch last-run info for multiple scrapers in one DB round-trip.

    Falls back to per-scraper queries if the store doesn't support batch,
    or if the DB is unreachable (returns None for that scraper).
    """
    store = container._get_state_store()
    if store is not None and hasattr(store, "get_all_last_run_info"):
        try:
            return store.get_all_last_run_info(names)
        except Exception:
            pass

    # Fallback: per-scraper queries with error tolerance
    result: dict[str, dict | None] = {}
    for name in names:
        try:
            state = container.state_tracker(name)
            result[name] = state.get_last_run_info()
        except Exception:
            result[name] = None
    return result


@bp.route("/")
def index():
    scrapers = ScraperRegistry.list_scrapers()
    load_scraper_configs(scrapers)

    log_event(logger, "info", "ui.page.dashboard")
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


@bp.route("/scrapers/cards/bulk")
def bulk_scraper_cards():
    """Return all scraper cards with OOB attributes for bulk dashboard polling."""
    scrapers = ScraperRegistry.list_scrapers()
    all_info = _bulk_last_run_info([s["name"] for s in scrapers])
    for scraper in scrapers:
        scraper["state"] = all_info.get(scraper["name"])
        scraper["status"] = get_scraper_status(scraper["name"], info=scraper["state"])
    return render_template("components/bulk-cards.html", scrapers=scrapers, oob=True)


@bp.route("/scrapers/status/bulk")
def bulk_scraper_status():
    """Return all status badges with OOB attributes for bulk scrapers page polling."""
    scrapers = ScraperRegistry.list_scrapers()
    all_info = _bulk_last_run_info([s["name"] for s in scrapers])
    badges = []
    for scraper in scrapers:
        name = scraper["name"]
        status = get_scraper_status(name, info=all_info.get(name))
        badges.append({
            "scraper_name": name,
            "status": status,
            "status_text": status.replace("_", " ").title(),
        })
    return render_template("components/bulk-status-badges.html", badges=badges, oob=True)


@bp.route("/scrapers/<name>/status")
def scraper_status(name):
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return render_template(
            "components/status-badge.html",
            status="error",
            status_text="Invalid Name",
        )

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
@limiter.limit("10/minute")
def run_scraper(name):
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"error": "Invalid scraper name format"}), 400

    dry_run = request.form.get("dry_run") == "true"
    max_pages = request.form.get("max_pages", type=int)

    if max_pages is not None and max_pages < 1:
        return jsonify({"error": "max_pages must be positive"}), 400

    # Fix precedence: original `max_pages or 1 if dry_run else None` parsed as
    # `max_pages or (1 if dry_run else None)` due to Python operator precedence
    effective_max_pages = max_pages
    if dry_run and effective_max_pages is None:
        effective_max_pages = 1

    if dry_run:
        # Dry runs: use raw scraper (no pipeline processing needed)
        scraper = ScraperRegistry.get_scraper(name, dry_run=True, max_pages=effective_max_pages)
        if not scraper:
            return jsonify({"error": f"Scraper not found: {name}"}), 404
        runnable = scraper
    else:
        # Real runs: use Pipeline so documents are processed (parsed, archived, indexed)
        from app.orchestrator.pipeline import Pipeline

        # Verify scraper exists before creating pipeline
        if not ScraperRegistry.get_scraper_class(name):
            return jsonify({"error": f"Scraper not found: {name}"}), 404

        # Load scraper config for upload flags
        config_path = Config.SCRAPERS_CONFIG_DIR / f"{name}.json"
        scraper_config = {}
        if config_path.exists():
            import json as json_mod
            try:
                with open(config_path) as f:
                    scraper_config = json_mod.load(f)
            except json_mod.JSONDecodeError as e:
                log_event(logger, "error", "scraper.config.invalid", scraper=name, error=str(e))

        runnable = Pipeline(
            scraper_name=name,
            max_pages=effective_max_pages,
            upload_to_ragflow=scraper_config.get("upload_to_ragflow", True),
            upload_to_paperless=scraper_config.get("upload_to_paperless", True),
            verify_document_timeout=scraper_config.get("verify_document_timeout", 60),
        )

    try:
        job_queue.enqueue(name, runnable, dry_run=dry_run, max_pages=effective_max_pages)
    except ValueError:
        scraper_class = ScraperRegistry.get_scraper_class(name)
        if not scraper_class:
            return jsonify({"error": f"Scraper not found: {name}"}), 404
        return render_template(
            "components/scraper-card.html",
            scraper=scraper_class.get_metadata(),
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

    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        return jsonify({"error": f"Scraper not found: {name}"}), 404
    
    metadata = scraper_class.get_metadata()
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
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"error": "Invalid scraper name format"}), 400

    max_pages = request.form.get("max_pages", 1, type=int)

    if max_pages < 1:
        return jsonify({"error": "max_pages must be positive"}), 400

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
        # Escape error message to prevent XSS
        safe_error = escape(str(job.error))
        return f'<div class="preview-error">Preview failed: {safe_error}</div>'

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
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return "Invalid scraper name", 400

    if not ScraperRegistry.get_scraper_class(name):
        return f"Scraper not found: {escape(name)}", 404

    settings_mgr = container.settings
    settings = {}

    ingestion_mode = request.form.get(f"ingestion_mode_{name}")
    if ingestion_mode:
        if ingestion_mode not in ("builtin", "custom"):
            return "Invalid ingestion mode", 400
        settings["ingestion_mode"] = ingestion_mode

    chunk_method = request.form.get("chunk_method")
    if chunk_method:
        if chunk_method not in CHUNK_METHODS:
            return "Invalid chunk method", 400
        settings["chunk_method"] = chunk_method

    pdf_parser = request.form.get("pdf_parser")
    if pdf_parser:
        if pdf_parser not in PDF_PARSERS:
            return "Invalid PDF parser", 400
        settings["pdf_parser"] = pdf_parser

    if "embedding_model" in request.form:
        model = request.form.get("embedding_model", "")
        if model and len(model) > 255:
            return "Embedding model name exceeds maximum length of 255 characters", 400
        if model and not re.match(r'^[a-zA-Z0-9_\-\.@\s/:]+$', model):
            return "Invalid embedding model format", 400
        settings["embedding_model"] = model

    if "pipeline_id" in request.form:
        pipeline_id = request.form.get("pipeline_id", "")
        if pipeline_id and len(pipeline_id) > 255:
            return "Pipeline ID exceeds maximum length of 255 characters", 400
        if pipeline_id and not re.match(r'^[a-zA-Z0-9_\-]+$', pipeline_id):
            return "Invalid pipeline ID format", 400
        settings["pipeline_id"] = pipeline_id

    if request.form.get("dataset_id"):
        dataset_id = request.form.get("dataset_id")
        if dataset_id and len(dataset_id) > 255:
            return "Dataset ID exceeds maximum length of 255 characters", 400
        if dataset_id and not re.match(r'^[a-zA-Z0-9_\-]+$', dataset_id):
            return "Invalid dataset ID format", 400
        settings["dataset_id"] = dataset_id

    if settings:
        settings_mgr.set_scraper_ragflow_settings(name, settings)
        logger.info(f"RAGFlow settings for {name} updated: {list(settings.keys())}")

    return '''
        <span class="setting-saved">Saved</span>
    '''


@bp.route("/scrapers/<name>/purge", methods=["POST"])
@limiter.limit("5/minute")
def purge_scraper(name):
    """Purge all local data for a scraper and return refreshed card."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"error": "Invalid scraper name format"}), 400

    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        return jsonify({"error": f"Scraper not found: {escape(name)}"}), 404

    # Refuse if scraper is running
    job = job_queue.get(name)
    if job and job.is_active:
        metadata = scraper_class.get_metadata()
        state = container.state_tracker(name)
        metadata["state"] = state.get_last_run_info()
        metadata["status"] = job_queue.status(name)
        return render_template(
            "components/scraper-card.html",
            scraper=metadata,
            message="Cannot purge while running",
        )

    state = container.state_tracker(name)
    counts = state.purge()
    log_event(logger, "warning", "scraper.purge", scraper=name, **counts)

    metadata = build_scraper_metadata(name)
    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/scrapers/<name>/nuclear-purge", methods=["POST"])
@limiter.limit("2/minute")
def nuclear_purge_scraper(name):
    """Nuclear purge: delete local data, Paperless documents, and vector chunks."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"error": "Invalid scraper name format"}), 400

    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        return jsonify({"error": f"Scraper not found: {escape(name)}"}), 404

    # Refuse if scraper is running
    job = job_queue.get(name)
    if job and job.is_active:
        metadata = scraper_class.get_metadata()
        state = container.state_tracker(name)
        metadata["state"] = state.get_last_run_info()
        metadata["status"] = job_queue.status(name)
        return render_template(
            "components/scraper-card.html",
            scraper=metadata,
            message="Cannot purge while running",
        )

    tag_name = scraper_class.get_metadata().get("primary_tag", "")

    archive_backend = None
    try:
        archive_backend = container.archive_backend
    except Exception as exc:
        log_event(logger, "warning", "scraper.nuclear_purge.archive_unavailable", scraper=name, error=str(exc))

    vector_store = None
    try:
        vector_store = container.vector_store
    except Exception as exc:
        log_event(logger, "warning", "scraper.nuclear_purge.vector_unavailable", scraper=name, error=str(exc))

    state = container.state_tracker(name)
    counts = state.nuclear_purge(
        archive_backend=archive_backend,
        vector_store=vector_store,
        tag_name=tag_name,
    )
    log_event(logger, "warning", "scraper.nuclear_purge", scraper=name, **counts)

    metadata = build_scraper_metadata(name)
    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/scrapers/<name>/cloudflare", methods=["POST"])
def toggle_scraper_cloudflare(name):
    """Toggle FlareSolverr/Cloudflare bypass for a specific scraper."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return '''
            <span class="toggle-status error">
                Invalid name
            </span>
        ''', 400

    if not ScraperRegistry.get_scraper_class(name):
        return '''
            <span class="toggle-status error">
                Not found
            </span>
        ''', 404

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
