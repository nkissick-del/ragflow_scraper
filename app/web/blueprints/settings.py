"""Settings pages and actions."""

from __future__ import annotations

from flask import Blueprint, render_template, request


from app.config import Config
from app.services import FlareSolverrClient, RAGFlowClient
from app.utils.logging_config import log_event, log_exception
from app.utils import get_logger
from app.web.runtime import container

bp = Blueprint("settings", __name__)
logger = get_logger("web.settings")


@bp.route("/settings")
def settings_page():
    settings_mgr = container.settings
    current_settings = settings_mgr.get_all()

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

    ragflow_providers = {}
    if ragflow_client and Config.RAGFLOW_USERNAME and Config.RAGFLOW_PASSWORD:
        try:
            ragflow_models = ragflow_client.list_embedding_models()
            ragflow_chunk_methods = ragflow_client.list_chunk_methods()
            for model in ragflow_models:
                provider = model.get("provider", "Unknown")
                ragflow_providers.setdefault(provider, []).append(model)
        except Exception as exc:
            log_exception(logger, exc, "ragflow.models.fetch_failed", page="settings")

    if not ragflow_chunk_methods:
        from app.services.ragflow_client import CHUNK_METHODS
        ragflow_chunk_methods = CHUNK_METHODS

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
    except Exception as exc:
        # Escape exception message to prevent XSS
        log_exception(logger, exc, "ragflow.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-flaresolverr", methods=["POST"])
def test_flaresolverr():
    if not Config.FLARESOLVERR_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        # Use same client instance as settings_page for consistency
        client = container.flaresolverr_client
        if client.test_connection():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        # Escape exception message to prevent XSS
        log_exception(logger, exc, "flaresolverr.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/flaresolverr", methods=["POST"])
def save_flaresolverr_settings():
    settings_mgr = container.settings

    enabled = request.form.get("enabled") == "on"
    timeout = request.form.get("timeout", 60, type=int)
    max_timeout = request.form.get("max_timeout", 120, type=int)

    settings_mgr.update_section("flaresolverr", {
        "enabled": enabled,
        "timeout": timeout,
        "max_timeout": max_timeout,
    })

    logger.info(f"FlareSolverr settings updated: enabled={enabled}")

    return '''
        <div class="alert alert-success">
            FlareSolverr settings saved successfully!
        </div>
    '''


@bp.route("/settings/scraping", methods=["POST"])
def save_scraping_settings():
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
