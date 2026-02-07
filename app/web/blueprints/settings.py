"""Settings pages and actions."""

from __future__ import annotations

import requests as http_requests

from flask import Blueprint, render_template, request
from markupsafe import escape


from app.config import Config
from app.services import FlareSolverrClient, RAGFlowClient
from app.utils.logging_config import log_event, log_exception
from app.utils import get_logger
from app.web.runtime import container

bp = Blueprint("settings", __name__)
logger = get_logger("web.settings")


def _check_service_status(check_fn, service_name: str) -> str:
    """Run a health check function and return status string."""
    try:
        if check_fn():
            return "connected"
        return "disconnected"
    except Exception as exc:
        log_exception(logger, exc, f"{service_name}.connection.error", page="settings")
        return "error"


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

    # Service health checks
    gotenberg_status = "not_configured"
    if Config.GOTENBERG_URL:
        gotenberg_status = _check_service_status(
            lambda: container.gotenberg_client.health_check(), "gotenberg"
        )

    tika_status = "not_configured"
    if Config.TIKA_SERVER_URL:
        tika_status = _check_service_status(
            lambda: container.tika_client.health_check(), "tika"
        )

    paperless_status = "not_configured"
    if Config.PAPERLESS_API_URL and Config.PAPERLESS_API_TOKEN:
        def _check_paperless():
            resp = http_requests.get(
                f"{Config.PAPERLESS_API_URL}/api/",
                headers={"Authorization": f"Token {Config.PAPERLESS_API_TOKEN}"},
                timeout=10,
            )
            return resp.status_code == 200
        paperless_status = _check_service_status(_check_paperless, "paperless")

    docling_serve_status = "not_configured"
    if Config.DOCLING_SERVE_URL:
        def _check_docling():
            resp = http_requests.get(f"{Config.DOCLING_SERVE_URL}/health", timeout=10)
            return resp.ok
        docling_serve_status = _check_service_status(_check_docling, "docling_serve")

    anythingllm_status = "not_configured"
    if Config.ANYTHINGLLM_API_URL and Config.ANYTHINGLLM_API_KEY:
        def _check_anythingllm():
            from app.services.anythingllm_client import AnythingLLMClient
            client = AnythingLLMClient(
                api_url=Config.ANYTHINGLLM_API_URL,
                api_key=Config.ANYTHINGLLM_API_KEY,
            )
            try:
                return client.test_connection()
            finally:
                client.close()
        anythingllm_status = _check_service_status(_check_anythingllm, "anythingllm")

    # Current pipeline settings (with Config fallback)
    pipeline_settings = current_settings.get("pipeline", {})
    current_merge_strategy = pipeline_settings.get("metadata_merge_strategy", "") or Config.METADATA_MERGE_STRATEGY
    current_filename_template = pipeline_settings.get("filename_template", "") or Config.FILENAME_TEMPLATE

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
        gotenberg_status=gotenberg_status,
        tika_status=tika_status,
        paperless_status=paperless_status,
        docling_serve_status=docling_serve_status,
        anythingllm_status=anythingllm_status,
        current_merge_strategy=current_merge_strategy,
        current_filename_template=current_filename_template,
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


@bp.route("/settings/test-gotenberg", methods=["POST"])
def test_gotenberg():
    if not Config.GOTENBERG_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.gotenberg_client
        if client.health_check():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "gotenberg.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-tika", methods=["POST"])
def test_tika():
    if not Config.TIKA_SERVER_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.tika_client
        if client.health_check():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "tika.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-paperless", methods=["POST"])
def test_paperless():
    if not Config.PAPERLESS_API_URL or not Config.PAPERLESS_API_TOKEN:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        resp = http_requests.get(
            f"{Config.PAPERLESS_API_URL}/api/",
            headers={"Authorization": f"Token {Config.PAPERLESS_API_TOKEN}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "paperless.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-anythingllm", methods=["POST"])
def test_anythingllm():
    if not Config.ANYTHINGLLM_API_URL or not Config.ANYTHINGLLM_API_KEY:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        from app.services.anythingllm_client import AnythingLLMClient
        client = AnythingLLMClient(
            api_url=Config.ANYTHINGLLM_API_URL,
            api_key=Config.ANYTHINGLLM_API_KEY,
        )
        try:
            if client.test_connection():
                return '<span class="status-badge status-connected">Connected</span>'
            else:
                return '<span class="status-badge status-disconnected">Connection Failed</span>'
        finally:
            client.close()
    except Exception as exc:
        log_exception(logger, exc, "anythingllm.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-docling-serve", methods=["POST"])
def test_docling_serve():
    if not Config.DOCLING_SERVE_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        resp = http_requests.get(
            f"{Config.DOCLING_SERVE_URL}/health",
            timeout=10,
        )
        if resp.ok:
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "docling_serve.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/pipeline", methods=["POST"])
def save_pipeline_settings():
    settings_mgr = container.settings

    metadata_merge_strategy = request.form.get("metadata_merge_strategy", "")
    filename_template = request.form.get("filename_template", "")

    # Validate merge strategy if provided
    if metadata_merge_strategy and metadata_merge_strategy not in Config.VALID_METADATA_MERGE_STRATEGIES:
        return f'''
            <div class="alert alert-danger">
                Invalid merge strategy: {escape(metadata_merge_strategy)}. Must be one of: {", ".join(Config.VALID_METADATA_MERGE_STRATEGIES)}
            </div>
        '''

    # Validate filename template if provided
    if filename_template:
        from jinja2 import TemplateSyntaxError
        from jinja2.sandbox import SandboxedEnvironment
        try:
            env = SandboxedEnvironment()
            env.from_string(filename_template)
        except TemplateSyntaxError as e:
            return f'''
                <div class="alert alert-danger">
                    Invalid template syntax: {escape(str(e))}
                </div>
            '''

    settings_mgr.update_section("pipeline", {
        "metadata_merge_strategy": metadata_merge_strategy,
        "filename_template": filename_template,
    })

    logger.info(f"Pipeline settings updated: strategy={metadata_merge_strategy or '(default)'}, template={filename_template or '(default)'}")

    return '''
        <div class="alert alert-success">
            Pipeline settings saved successfully!
        </div>
    '''


@bp.route("/settings/pipeline/preview-filename", methods=["POST"])
def preview_filename():
    template = request.form.get("template", "")
    if not template:
        template = Config.FILENAME_TEMPLATE

    from app.utils.file_utils import generate_filename_from_template

    sample_metadata = {
        "title": "Annual Report 2024",
        "organization": "AEMO",
        "publication_date": "2024-07-15",
        "filename": "report.pdf",
    }

    try:
        rendered = generate_filename_from_template(sample_metadata, template=template)
        return f'<code>{escape(rendered)}</code>'
    except Exception as e:
        return f'<span class="text-danger">Error: {escape(str(e))}</span>'
