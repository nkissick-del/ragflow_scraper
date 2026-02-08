"""Settings pages and actions."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import requests as http_requests

from flask import Blueprint, render_template, request
from markupsafe import escape


from app.config import Config
from app.scrapers import ScraperRegistry
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


def _get_effective_url(service: str, config_attr: str) -> str:
    """Get effective service URL from settings override or Config fallback."""
    override = container.settings.get(f"services.{service}_url", "")
    if override:
        return override
    return getattr(Config, config_attr, "")


def _get_effective_timeout(service: str, config_attr: str) -> int:
    """Get effective timeout from settings override (if >0) or Config fallback."""
    override = container.settings.get(f"services.{service}_timeout", 0)
    if override and override > 0:
        return override
    return getattr(Config, config_attr, 60)


def _get_effective_backend(backend_type: str) -> str:
    """Get effective backend name from settings override or Config fallback."""
    override = container.settings.get(f"pipeline.{backend_type}_backend", "")
    if override:
        return override
    return getattr(Config, f"{backend_type.upper()}_BACKEND", "")


# Cloud metadata / link-local networks to block (SSRF mitigation).
# Private RFC1918 ranges (10.x, 172.16-31.x, 192.168.x) are intentionally
# ALLOWED because this self-hosted app connects to local-network services.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


def _validate_url_ssrf(url: str) -> str | None:
    """Return an error message if *url* targets a blocked address, else None."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "URL has no hostname"

        # Resolve hostname to IP(s) and check each
        infos = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canonname, sockaddr in infos:
            addr = ipaddress.ip_address(sockaddr[0])
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return f"URL resolves to a blocked address range ({net})"
    except socket.gaierror:
        # DNS resolution failed — allow it; the health-check will surface the real error
        pass
    except Exception:
        return "URL could not be validated"
    return None


@bp.route("/settings")
def settings_page():
    settings_mgr = container.settings
    current_settings = settings_mgr.get_all()

    # Compute effective values for all services
    eff_gotenberg_url = _get_effective_url("gotenberg", "GOTENBERG_URL")
    eff_gotenberg_timeout = _get_effective_timeout("gotenberg", "GOTENBERG_TIMEOUT")
    eff_tika_url = _get_effective_url("tika", "TIKA_SERVER_URL")
    eff_tika_timeout = _get_effective_timeout("tika", "TIKA_TIMEOUT")
    eff_docling_serve_url = _get_effective_url("docling_serve", "DOCLING_SERVE_URL")
    eff_docling_serve_timeout = _get_effective_timeout("docling_serve", "DOCLING_SERVE_TIMEOUT")
    eff_paperless_url = _get_effective_url("paperless", "PAPERLESS_API_URL")
    eff_ragflow_url = _get_effective_url("ragflow", "RAGFLOW_API_URL")
    eff_anythingllm_url = _get_effective_url("anythingllm", "ANYTHINGLLM_API_URL")

    # Effective backend selections
    eff_parser_backend = _get_effective_backend("parser")
    eff_archive_backend = _get_effective_backend("archive")
    eff_rag_backend = _get_effective_backend("rag")

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

    # Service health checks — use effective URLs
    gotenberg_status = "not_configured"
    if eff_gotenberg_url:
        gotenberg_status = _check_service_status(
            lambda: container.gotenberg_client.health_check(), "gotenberg"
        )

    tika_status = "not_configured"
    if eff_tika_url:
        tika_status = _check_service_status(
            lambda: container.tika_client.health_check(), "tika"
        )

    paperless_status = "not_configured"
    if eff_paperless_url and Config.PAPERLESS_API_TOKEN:
        def _check_paperless():
            resp = http_requests.get(
                f"{eff_paperless_url}/api/",
                headers={"Authorization": f"Token {Config.PAPERLESS_API_TOKEN}"},
                timeout=10,
            )
            return resp.status_code == 200
        paperless_status = _check_service_status(_check_paperless, "paperless")

    docling_serve_status = "not_configured"
    if eff_docling_serve_url:
        def _check_docling():
            resp = http_requests.get(f"{eff_docling_serve_url}/health", timeout=10)
            return resp.ok
        docling_serve_status = _check_service_status(_check_docling, "docling_serve")

    anythingllm_status = "not_configured"
    if eff_anythingllm_url and Config.ANYTHINGLLM_API_KEY:
        def _check_anythingllm():
            from app.services.anythingllm_client import AnythingLLMClient
            client = AnythingLLMClient(
                api_url=eff_anythingllm_url,
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

    # Tika enrichment toggle
    tika_enrichment_override = pipeline_settings.get("tika_enrichment_enabled", "")
    if tika_enrichment_override != "":
        tika_enrichment_active = tika_enrichment_override == "true"
    else:
        tika_enrichment_active = Config.TIKA_ENRICHMENT_ENABLED

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
        # Effective values for template
        eff_parser_backend=eff_parser_backend,
        eff_archive_backend=eff_archive_backend,
        eff_rag_backend=eff_rag_backend,
        eff_gotenberg_url=eff_gotenberg_url,
        eff_gotenberg_timeout=eff_gotenberg_timeout,
        eff_tika_url=eff_tika_url,
        eff_tika_timeout=eff_tika_timeout,
        eff_docling_serve_url=eff_docling_serve_url,
        eff_docling_serve_timeout=eff_docling_serve_timeout,
        eff_paperless_url=eff_paperless_url,
        eff_ragflow_url=eff_ragflow_url,
        eff_anythingllm_url=eff_anythingllm_url,
        tika_enrichment_active=tika_enrichment_active,
        scraper_names=ScraperRegistry.get_scraper_names(),
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
    eff_url = _get_effective_url("gotenberg", "GOTENBERG_URL")
    if not eff_url:
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
    eff_url = _get_effective_url("tika", "TIKA_SERVER_URL")
    if not eff_url:
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
    eff_url = _get_effective_url("paperless", "PAPERLESS_API_URL")
    if not eff_url or not Config.PAPERLESS_API_TOKEN:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        resp = http_requests.get(
            f"{eff_url}/api/",
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
    eff_url = _get_effective_url("anythingllm", "ANYTHINGLLM_API_URL")
    if not eff_url or not Config.ANYTHINGLLM_API_KEY:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        from app.services.anythingllm_client import AnythingLLMClient
        client = AnythingLLMClient(
            api_url=eff_url,
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
    eff_url = _get_effective_url("docling_serve", "DOCLING_SERVE_URL")
    if not eff_url:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        resp = http_requests.get(
            f"{eff_url}/health",
            timeout=10,
        )
        if resp.ok:
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "docling_serve.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/backends", methods=["POST"])
def save_backend_settings():
    settings_mgr = container.settings

    parser_backend = request.form.get("parser_backend", "")
    archive_backend = request.form.get("archive_backend", "")
    rag_backend = request.form.get("rag_backend", "")

    # Validate backends if non-empty
    if parser_backend and parser_backend not in Config.VALID_PARSER_BACKENDS:
        return f'''
            <div class="alert alert-danger">
                Invalid parser backend: {escape(parser_backend)}.
                Must be one of: {", ".join(Config.VALID_PARSER_BACKENDS)}
            </div>
        '''
    if archive_backend and archive_backend not in Config.VALID_ARCHIVE_BACKENDS:
        return f'''
            <div class="alert alert-danger">
                Invalid archive backend: {escape(archive_backend)}.
                Must be one of: {", ".join(Config.VALID_ARCHIVE_BACKENDS)}
            </div>
        '''
    if rag_backend and rag_backend not in Config.VALID_RAG_BACKENDS:
        return f'''
            <div class="alert alert-danger">
                Invalid RAG backend: {escape(rag_backend)}.
                Must be one of: {", ".join(Config.VALID_RAG_BACKENDS)}
            </div>
        '''

    settings_mgr.update_section("pipeline", {
        "parser_backend": parser_backend,
        "archive_backend": archive_backend,
        "rag_backend": rag_backend,
    })

    container.reset_services()

    logger.info(
        f"Backend settings updated: parser={parser_backend or '(default)'}, "
        f"archive={archive_backend or '(default)'}, rag={rag_backend or '(default)'}"
    )

    return '''
        <div class="alert alert-success">
            Backend settings saved. Services will use new backends on next operation.
        </div>
    '''


@bp.route("/settings/services", methods=["POST"])
def save_service_settings():
    settings_mgr = container.settings

    # Extract URLs
    gotenberg_url = request.form.get("gotenberg_url", "").strip()
    tika_url = request.form.get("tika_url", "").strip()
    docling_serve_url = request.form.get("docling_serve_url", "").strip()
    paperless_url = request.form.get("paperless_url", "").strip()
    ragflow_url = request.form.get("ragflow_url", "").strip()
    anythingllm_url = request.form.get("anythingllm_url", "").strip()

    # Extract timeouts
    gotenberg_timeout = request.form.get("gotenberg_timeout", 0, type=int)
    tika_timeout = request.form.get("tika_timeout", 0, type=int)
    docling_serve_timeout = request.form.get("docling_serve_timeout", 0, type=int)

    # Validate URLs (scheme + SSRF check)
    for label, url in [
        ("Gotenberg", gotenberg_url),
        ("Tika", tika_url),
        ("Docling-serve", docling_serve_url),
        ("Paperless", paperless_url),
        ("RAGFlow", ragflow_url),
        ("AnythingLLM", anythingllm_url),
    ]:
        if url and not url.startswith(("http://", "https://")):
            return f'''
                <div class="alert alert-danger">
                    {escape(label)} URL must start with http:// or https://
                </div>
            '''
        if url:
            ssrf_err = _validate_url_ssrf(url)
            if ssrf_err:
                return f'''
                    <div class="alert alert-danger">
                        {escape(label)}: {escape(ssrf_err)}
                    </div>
                '''

    # Validate timeouts (0 or 1-600)
    for label, timeout in [
        ("Gotenberg", gotenberg_timeout),
        ("Tika", tika_timeout),
        ("Docling-serve", docling_serve_timeout),
    ]:
        if timeout != 0 and not (1 <= timeout <= 600):
            return f'''
                <div class="alert alert-danger">
                    {escape(label)} timeout must be 0 (use default) or between 1 and 600 seconds.
                </div>
            '''

    settings_mgr.update_section("services", {
        "gotenberg_url": gotenberg_url,
        "gotenberg_timeout": gotenberg_timeout,
        "tika_url": tika_url,
        "tika_timeout": tika_timeout,
        "docling_serve_url": docling_serve_url,
        "docling_serve_timeout": docling_serve_timeout,
        "paperless_url": paperless_url,
        "ragflow_url": ragflow_url,
        "anythingllm_url": anythingllm_url,
    })

    container.reset_services()

    logger.info("Service configuration updated")

    return '''
        <div class="alert alert-success">
            Service configuration saved. Clients will reconnect with new settings.
        </div>
    '''


@bp.route("/settings/pipeline", methods=["POST"])
def save_pipeline_settings():
    settings_mgr = container.settings

    metadata_merge_strategy = request.form.get("metadata_merge_strategy", "")
    filename_template = request.form.get("filename_template", "")
    tika_enrichment = request.form.get("tika_enrichment_enabled", "")
    tika_enrichment_value = "true" if tika_enrichment else "false"

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
        "tika_enrichment_enabled": tika_enrichment_value,
    })

    logger.info(f"Pipeline settings updated: strategy={metadata_merge_strategy or '(default)'}, template={filename_template or '(default)'}, tika_enrichment={tika_enrichment_value}")

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


def _validate_scraper_name(name: str) -> bool:
    """Validate scraper name to prevent injection."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))


@bp.route("/settings/reconciliation/report/<name>", methods=["POST"])
def reconciliation_report(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        report = recon.get_report(name)

        errors_html = ""
        if report.errors:
            errors_html = '<ul class="text-warning">'
            for err in report.errors:
                errors_html += f"<li>{escape(err)}</li>"
            errors_html += "</ul>"

        only_state_html = ""
        if report.urls_only_in_state:
            only_state_html = f'<details><summary>{len(report.urls_only_in_state)} URLs only in state</summary><ul>'
            for url in report.urls_only_in_state[:50]:
                only_state_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_only_in_state) > 50:
                only_state_html += f"<li>... and {len(report.urls_only_in_state) - 50} more</li>"
            only_state_html += "</ul></details>"

        only_paperless_html = ""
        if report.urls_only_in_paperless:
            only_paperless_html = f'<details><summary>{len(report.urls_only_in_paperless)} URLs only in Paperless</summary><ul>'
            for url in report.urls_only_in_paperless[:50]:
                only_paperless_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_only_in_paperless) > 50:
                only_paperless_html += f"<li>... and {len(report.urls_only_in_paperless) - 50} more</li>"
            only_paperless_html += "</ul></details>"

        rag_gaps_html = ""
        if report.urls_in_paperless_not_rag:
            rag_gaps_html = f'<details><summary>{len(report.urls_in_paperless_not_rag)} URLs in Paperless but not RAG</summary><ul>'
            for url in report.urls_in_paperless_not_rag[:50]:
                rag_gaps_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_in_paperless_not_rag) > 50:
                rag_gaps_html += f"<li>... and {len(report.urls_in_paperless_not_rag) - 50} more</li>"
            rag_gaps_html += "</ul></details>"

        return f'''
            <div class="alert alert-info">
                <strong>Reconciliation Report: {escape(name)}</strong>
                <table class="mt-2" style="width: auto;">
                    <tr><td>State URLs:</td><td><strong>{report.state_url_count}</strong></td></tr>
                    <tr><td>Paperless URLs:</td><td><strong>{report.paperless_url_count}</strong></td></tr>
                    <tr><td>RAG Documents:</td><td><strong>{report.rag_document_count}</strong></td></tr>
                </table>
                {errors_html}
                {only_state_html}
                {only_paperless_html}
                {rag_gaps_html}
            </div>
        '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.report.error")
        return f'<div class="alert alert-danger">Report failed: {escape(str(exc))}</div>'


@bp.route("/settings/reconciliation/rebuild/<name>", methods=["POST"])
def reconciliation_rebuild(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        added = recon.rebuild_state(name)

        return f'''
            <div class="alert alert-success">
                State rebuilt for {escape(name)}: {added} URLs added from Paperless
            </div>
        '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.rebuild.error")
        return f'<div class="alert alert-danger">Rebuild failed: {escape(str(exc))}</div>'


@bp.route("/settings/reconciliation/sync-rag/<name>", methods=["POST"])
def reconciliation_sync_rag(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        re_ingested = recon.sync_rag_gaps(name, dry_run=False)

        if re_ingested:
            urls_html = "<ul>"
            for url in re_ingested[:20]:
                urls_html += f"<li><code>{escape(url)}</code></li>"
            if len(re_ingested) > 20:
                urls_html += f"<li>... and {len(re_ingested) - 20} more</li>"
            urls_html += "</ul>"
            return f'''
                <div class="alert alert-success">
                    RAG sync complete: {len(re_ingested)} documents re-ingested
                    {urls_html}
                </div>
            '''
        else:
            return '''
                <div class="alert alert-info">
                    No documents needed re-ingestion. RAG is in sync with Paperless.
                </div>
            '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.sync_rag.error")
        return f'<div class="alert alert-danger">RAG sync failed: {escape(str(exc))}</div>'
