"""
Flask routes for the web interface.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, Response  # type: ignore[import]

from app.config import Config
from app.container import get_container
from app.scrapers import ScraperRegistry
from app.services import FlareSolverrClient
from app.utils import get_logger
from app.utils.errors import ScraperAlreadyRunningError
from app.utils.logging_config import log_event, log_exception
from app.web.runtime import job_queue

bp = Blueprint("main", __name__, static_folder="static", static_url_path="/static")
logger = get_logger("web")
container = get_container()
def _auth_failed() -> Response:
    """Return a basic-auth challenge response."""
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": "Basic realm=\"PDF Scraper\""},
    )


@bp.before_request
def enforce_basic_auth():
    """Apply optional basic auth to all routes except static assets."""
    if not Config.BASIC_AUTH_ENABLED:
        return None

    # Skip auth for static assets
    endpoint = (request.endpoint or "").split(".")[-1]
    if endpoint == "static":
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return _auth_failed()

    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return _auth_failed()

    if (
        username == Config.BASIC_AUTH_USERNAME
        and password == Config.BASIC_AUTH_PASSWORD
        and username
        and password
    ):
        return None

    log_event(logger, "warning", "auth.failure", endpoint=request.endpoint)
    return _auth_failed()


@bp.route("/")
def index():
    """Dashboard page."""
    scrapers = ScraperRegistry.list_scrapers()

    # Add status info to each scraper
    for scraper in scrapers:
        state = container.state_tracker(scraper["name"])
        info = (state.get_last_run_info() if state is not None else {}) or {}
        scraper["last_run"] = info.get("last_updated")
        scraper["processed_count"] = info.get("processed_count", 0)
        scraper["status"] = _get_scraper_status(scraper["name"])

    log_event(logger, "info", "ui.page.index", scraper_count=len(scrapers))
    return render_template("index.html", scrapers=scrapers)


@bp.route("/scrapers")
def scrapers():
    """Scrapers configuration page."""
    scrapers = ScraperRegistry.list_scrapers()
    settings_mgr = container.settings

    # Initialize RAGFlow client for dynamic options
    ragflow_client = container.ragflow_client

    # Build ragflow_options dict with all dynamic data
    ragflow_options = {
        "chunk_methods": ragflow_client.list_chunk_methods(),
        "pdf_parsers": ragflow_client.list_pdf_parsers(),
        "pipelines": ragflow_client.list_ingestion_pipelines(),
        "embedding_providers": {},  # provider -> [models]
    }

    # Fetch embedding models if session auth configured
    if ragflow_client.session_configured:
        try:
            ragflow_models = ragflow_client.list_embedding_models()
            # Group models by provider for cascading dropdown
            for model in ragflow_models:
                provider = model.get("provider", "Unknown")
                if provider not in ragflow_options["embedding_providers"]:
                    ragflow_options["embedding_providers"][provider] = []
                ragflow_options["embedding_providers"][provider].append(model)
        except Exception as e:
            log_exception(logger, e, "ragflow.models.fetch_failed", page="scrapers")

    for scraper in scrapers:
        # Load scraper config if exists
        config_path = Config.SCRAPERS_CONFIG_DIR / f"{scraper['name']}.json"
        if config_path.exists():
            with open(config_path) as f:
                scraper["config"] = json.load(f)
        else:
            scraper["config"] = {}

        # Get state info
        state = container.state_tracker(scraper["name"])
        scraper["state"] = (state.get_last_run_info() if state is not None else {}) or {}
        scraper["status"] = _get_scraper_status(scraper["name"])

        # Get per-scraper cloudflare setting
        scraper["cloudflare_enabled"] = settings_mgr.get_scraper_cloudflare_enabled(scraper["name"])

        # Get scraper-specific defaults for RAGFlow settings
        scraper_defaults = {
            "default_chunk_method": scraper.get("default_chunk_method", "naive"),
            "default_parser": scraper.get("default_parser", "DeepDOC"),
        }

        # Get per-scraper RAGFlow settings with scraper-specific defaults
        scraper["ragflow_settings"] = settings_mgr.get_scraper_ragflow_settings(
            scraper["name"],
            scraper_defaults=scraper_defaults,
        )

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
    """Get scraper status (for HTMX polling)."""
    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        log_event(logger, "warning", "scraper.status.unknown", scraper=name)
        return render_template(
            "components/status-badge.html",
            status="unknown",
            status_text="Unknown",
        )

    status = _get_scraper_status(name)
    status_text = status.replace("_", " ").title()

    return render_template(
        "components/status-badge.html",
        scraper_name=name,
        status=status,
        status_text=status_text,
    )


@bp.route("/scrapers/<name>/run", methods=["POST"])
def run_scraper(name):
    """Trigger a scraper run."""
    dry_run = request.form.get("dry_run") == "true"
    max_pages = request.form.get("max_pages", type=int)

    scraper = ScraperRegistry.get_scraper(name, dry_run=dry_run, max_pages=max_pages or 1 if dry_run else None)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    try:
        job_queue.enqueue(name, scraper, dry_run=dry_run, max_pages=max_pages)
    except ScraperAlreadyRunningError:
        scraper_class = ScraperRegistry.get_scraper_class(name)
        metadata = scraper_class.get_metadata() if scraper_class is not None else {"name": name}
        return render_template(
            "components/scraper-card.html",
            scraper=metadata,
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

    # Return updated card
    scraper_class = ScraperRegistry.get_scraper_class(name)
    metadata = scraper_class.get_metadata() if scraper_class is not None else {"name": name}
    state = container.state_tracker(name)
    metadata["state"] = (state.get_last_run_info() if state is not None else {}) or {}
    metadata["status"] = job_queue.status(name)
    metadata["dry_run"] = dry_run

    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/scrapers/<name>/cancel", methods=["POST"])
def cancel_scraper(name):
    """Cancel a running scraper."""
    if not job_queue.cancel(name):
        return render_template(
            "components/status-badge.html",
            scraper_name=name,
            status="idle",
            status_text="Not Running",
        )

    log_event(logger, "warning", "scraper.cancel.requested", scraper=name)

    # Return cancelling status badge
    return render_template(
        "components/status-badge.html",
        scraper_name=name,
        status="cancelling",
        status_text="Cancelling...",
    )


@bp.route("/scrapers/<name>/preview", methods=["POST"])
def preview_scraper(name):
    """Start a dry-run preview asynchronously."""
    max_pages = request.form.get("max_pages", 1, type=int)

    scraper = ScraperRegistry.get_scraper(name, dry_run=True, max_pages=max_pages)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    try:
        job_queue.enqueue(name, scraper, preview=True, dry_run=True, max_pages=max_pages)
    except ScraperAlreadyRunningError:
        return '<div class="preview-error">Scraper is currently running. Please wait.</div>'

    log_event(logger, "info", "scraper.preview.requested", scraper=name, max_pages=max_pages)

    # Return polling template
    return render_template(
        "components/preview-loading.html",
        scraper_name=name,
    )


@bp.route("/scrapers/<name>/preview/status")
def preview_status(name):
    """Check preview status and return results when ready (for HTMX polling)."""
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

    # Still running - return loading state with continued polling
    return render_template(
        "components/preview-loading.html",
        scraper_name=name,
    )


@bp.route("/scrapers/<name>/card")
def scraper_card(name):
    """Get scraper card (for HTMX refresh)."""
    scraper_class = ScraperRegistry.get_scraper_class(name)
    if not scraper_class:
        return "Not found", 404

    metadata = scraper_class.get_metadata()
    state = container.state_tracker(name)
    metadata["state"] = state.get_last_run_info()
    metadata["status"] = _get_scraper_status(name)

    return render_template("components/scraper-card.html", scraper=metadata)


@bp.route("/logs")
def logs():
    """Log viewer page."""
    # Get list of log files
    log_files = sorted(
        Config.LOG_DIR.glob("*.log"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )[:10]  # Last 10 log files

    log_event(logger, "info", "ui.page.logs", file_count=len(log_files))
    return render_template("logs.html", log_files=log_files)


@bp.route("/metrics/flaresolverr")
def flaresolverr_metrics():
    """Expose FlareSolverr client metrics for observability panels."""
    container.ragflow_client  # ensures container is initialized
    # FlareSolverr metrics come from the dedicated client to avoid side effects
    try:
        flaresolverr = container.flaresolverr_client
        metrics = flaresolverr.get_metrics()
        log_event(logger, "info", "metrics.flaresolverr.success", metrics=metrics)
        return jsonify(metrics)
    except Exception as exc:
        log_exception(logger, exc, "metrics.flaresolverr.error")
        # Keep metric endpoint resilient; return empty metrics on error
        return jsonify({"success": 0, "failure": 0, "timeout": 0, "total": 0, "success_rate": 0.0})


@bp.route("/metrics/pipeline")
def pipeline_metrics():
    """Expose last-run pipeline stats per scraper using state tracker snapshots."""
    metrics: list[dict] = []
    total_processed = 0
    total_failed = 0

    for scraper in ScraperRegistry.list_scrapers():
        name = scraper.get("name")
        if not isinstance(name, str):
            continue
        state = container.state_tracker(name)
        last_run = (state.get_last_run_info() if state is not None else {}) or {}
        processed = last_run.get("processed_count", 0)
        failed = last_run.get("failed_count", 0)
        total_processed += processed
        total_failed += failed
        metrics.append(
            {
                "scraper": name,
                "last_run": last_run.get("last_updated"),
                "processed_count": processed,
                "failed_count": failed,
                "status": last_run.get("status", "unknown"),
            }
        )

    log_event(
        logger,
        "info",
        "metrics.pipeline.snapshot",
        scraper_count=len(metrics),
        total_processed=total_processed,
        total_failed=total_failed,
    )
    return jsonify({
        "scrapers": metrics,
        "totals": {
            "processed": total_processed,
            "failed": total_failed,
        },
    })


@bp.route("/logs/stream")
def log_stream():
    """Stream new log entries (for HTMX polling)."""
    # Get the most recent log file
    log_files = sorted(Config.LOG_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        return ""

    # Read last 50 lines
    try:
        with open(log_files[0]) as f:
            lines = f.readlines()[-50:]

        # Format as HTML
        html = ""
        for line in lines:
            css_class = "log-info"
            if "ERROR" in line:
                css_class = "log-error"
            elif "WARNING" in line:
                css_class = "log-warning"
            elif "DEBUG" in line:
                css_class = "log-debug"
            html += f'<div class="log-entry {css_class}">{line.strip()}</div>'

        return html
    except Exception as e:
        log_exception(logger, e, "logs.stream.error")
        return f'<div class="log-entry log-error">Error reading logs: {e}</div>'


@bp.route("/logs/download/<filename>")
def download_log(filename):
    """Download a log file."""
    log_path = Config.LOG_DIR / filename
    if not log_path.exists() or not log_path.is_file():
        return "Not found", 404

    try:
        with open(log_path) as f:
            content = f.read()
    except Exception as exc:
        log_exception(logger, exc, "logs.download.error", filename=filename)
        return "Not found", 404

    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.route("/settings")
def settings():
    """Settings page."""
    settings_mgr = container.settings
    current_settings = settings_mgr.get_all()

    # Test RAGFlow connection
    ragflow_status = "unknown"
    ragflow_models = []
    ragflow_chunk_methods = []
    ragflow_client = None

    try:
        ragflow_client = container.ragflow_client
        if ragflow_client.test_connection():
            ragflow_status = "connected"
        else:
            ragflow_status = "disconnected"
    except Exception as exc:
        log_exception(logger, exc, "ragflow.connection.error", page="settings")
        ragflow_status = "error"

    # Fetch RAGFlow models if session auth is configured
    ragflow_providers = {}  # Provider -> list of models
    if ragflow_client and Config.RAGFLOW_USERNAME and Config.RAGFLOW_PASSWORD:
        try:
            ragflow_models = ragflow_client.list_embedding_models()
            ragflow_chunk_methods = ragflow_client.list_chunk_methods()
            # Group models by provider for cascading dropdown
            for model in ragflow_models:
                provider = model.get("provider", "Unknown")
                if provider not in ragflow_providers:
                    ragflow_providers[provider] = []
                ragflow_providers[provider].append(model)
        except Exception as e:
            log_exception(logger, e, "ragflow.models.fetch_failed", page="settings")

    # If we couldn't fetch models dynamically, use static chunk methods list
    if not ragflow_chunk_methods:
        from app.services.ragflow_client import CHUNK_METHODS
        ragflow_chunk_methods = CHUNK_METHODS

    # Test FlareSolverr connection (URL from env, not settings)
    flaresolverr_status = "unknown"
    if Config.FLARESOLVERR_URL:
        try:
            client = container.flaresolverr_client
            if client.test_connection():
                flaresolverr_status = "connected"
            else:
                flaresolverr_status = "disconnected"
        except Exception as exc:
            log_exception(logger, exc, "flaresolverr.connection.error", page="settings")
            flaresolverr_status = "error"
    else:
        flaresolverr_status = "not_configured"

    log_event(
        logger,
        "info",
        "ui.page.settings",
        ragflow_status=ragflow_status,
        flaresolverr_status=flaresolverr_status,
    )
    return render_template(
        "settings.html",
        settings=current_settings,
        ragflow_status=ragflow_status,
        ragflow_models=ragflow_models,
        ragflow_providers=ragflow_providers,
        ragflow_chunk_methods=ragflow_chunk_methods,
        flaresolverr_status=flaresolverr_status,
        config=Config,
    )


@bp.route("/settings/test-ragflow", methods=["POST"])
def test_ragflow():
    """Test RAGFlow connection (HTMX endpoint)."""
    try:
        client = container.ragflow_client
        if client.test_connection():
            datasets = client.list_datasets()
            return f'''
                <span class="status-badge status-connected">Connected</span>
                <p class="mt-2">Found {len(datasets)} dataset(s)</p>
            '''
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as e:
        return f'<span class="status-badge status-error">Error: {str(e)}</span>'


@bp.route("/settings/test-flaresolverr", methods=["POST"])
def test_flaresolverr():
    """Test FlareSolverr connection (HTMX endpoint)."""
    if not Config.FLARESOLVERR_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = FlareSolverrClient()
        if client.test_connection():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as e:
        return f'<span class="status-badge status-error">Error: {str(e)}</span>'


@bp.route("/settings/flaresolverr", methods=["POST"])
def save_flaresolverr_settings():
    """Save FlareSolverr settings (HTMX endpoint)."""
    settings_mgr = container.settings

    enabled = request.form.get("enabled") == "on"
    timeout = request.form.get("timeout", 60, type=int)
    max_timeout = request.form.get("max_timeout", 120, type=int)

    # URL comes from env, only save behavioral settings
    settings_mgr.update_section("flaresolverr", {
        "enabled": enabled,
        "timeout": timeout,
        "max_timeout": max_timeout,
    })

    logger.info(f"FlareSolverr settings updated: enabled={enabled}")

    # Return success message
    return '''
        <div class="alert alert-success">
            FlareSolverr settings saved successfully!
        </div>
    '''


@bp.route("/settings/scraping", methods=["POST"])
def save_scraping_settings():
    """Save scraping settings (HTMX endpoint)."""
    settings_mgr = container.settings

    use_flaresolverr = request.form.get("use_flaresolverr_by_default") == "on"
    request_delay = request.form.get("default_request_delay", 2.0, type=float)
    timeout = request.form.get("default_timeout", 60, type=int)
    retry_attempts = request.form.get("default_retry_attempts", 3, type=int)

    settings_mgr.update_section("scraping", {
        "use_flaresolverr_by_default": use_flaresolverr,
        "default_request_delay": request_delay,
        "default_timeout": timeout,
        "default_retry_attempts": retry_attempts,
    })

    logger.info(f"Scraping settings updated: use_flaresolverr={use_flaresolverr}")

    return '''
        <div class="alert alert-success">
            Scraping settings saved successfully!
        </div>
    '''


@bp.route("/settings/ragflow", methods=["POST"])
def save_ragflow_settings():
    """Save RAGFlow dataset settings (HTMX endpoint)."""
    settings_mgr = container.settings

    default_embedding_model = request.form.get("default_embedding_model", "")
    default_chunk_method = request.form.get("default_chunk_method", "paper")
    auto_upload = request.form.get("auto_upload") == "on"
    auto_create_dataset = request.form.get("auto_create_dataset") == "on"
    wait_for_parsing = request.form.get("wait_for_parsing") == "on"

    settings_mgr.update_section("ragflow", {
        "default_embedding_model": default_embedding_model,
        "default_chunk_method": default_chunk_method,
        "auto_upload": auto_upload,
        "auto_create_dataset": auto_create_dataset,
        "wait_for_parsing": wait_for_parsing,
    })

    logger.info(f"RAGFlow settings updated: model={default_embedding_model}, chunk={default_chunk_method}")

    return '''
        <div class="alert alert-success">
            RAGFlow settings saved successfully!
        </div>
    '''


@bp.route("/api/ragflow/models", methods=["GET"])
def get_ragflow_models():
    """API endpoint to fetch available RAGFlow embedding models."""
    try:
        client = container.ragflow_client
        models = client.list_embedding_models()
        return jsonify({"success": True, "models": models})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@bp.route("/api/ragflow/chunk-methods", methods=["GET"])
def get_ragflow_chunk_methods():
    """API endpoint to fetch available chunk methods."""
    try:
        client = container.ragflow_client
        methods = client.list_chunk_methods()
        return jsonify({"success": True, "methods": methods})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@bp.route("/scrapers/<name>/ragflow", methods=["POST"])
def save_scraper_ragflow_settings(name):
    """Save per-scraper RAGFlow settings (HTMX endpoint)."""
    settings_mgr = container.settings
    settings = {}

    # Check for ingestion mode (radio button name includes scraper name)
    ingestion_mode = request.form.get(f"ingestion_mode_{name}")
    if ingestion_mode:
        settings["ingestion_mode"] = ingestion_mode

    # Built-in mode settings
    if request.form.get("chunk_method"):
        settings["chunk_method"] = request.form.get("chunk_method")
    if request.form.get("pdf_parser"):
        settings["pdf_parser"] = request.form.get("pdf_parser")
    if "embedding_model" in request.form:
        settings["embedding_model"] = request.form.get("embedding_model", "")

    # Custom mode settings
    if "pipeline_id" in request.form:
        settings["pipeline_id"] = request.form.get("pipeline_id", "")

    # Legacy field support
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


@bp.route("/api/scrapers")
def api_list_scrapers():
    """API endpoint to list scrapers."""
    scrapers = ScraperRegistry.list_scrapers()
    return jsonify({"scrapers": scrapers})


@bp.route("/api/scrapers/<name>/run", methods=["POST"])
def api_run_scraper(name):
    """API endpoint to run a scraper."""
    scraper = ScraperRegistry.get_scraper(name)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    # Run synchronously for API
    result = scraper.run()
    return jsonify(result.to_dict())


def _get_scraper_status(name: str) -> str:
    """Get the current status of a scraper."""
    in_flight = job_queue.status(name)
    if in_flight != "idle":
        return in_flight

    state = container.state_tracker(name)
    info = (state.get_last_run_info() if state is not None else {}) or {}

    if not info.get("last_updated"):
        return "idle"

    stats = info.get("statistics", {})
    if stats.get("total_failed", 0) > 0:
        return "error"

    return "ready"
