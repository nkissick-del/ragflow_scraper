"""Settings UI page route."""

from __future__ import annotations

import re

import requests as http_requests

from flask import Blueprint, render_template, request

from app.config import Config
from app.scrapers import ScraperRegistry
from app.utils.logging_config import log_event, log_exception
from app.web.runtime import container
from app.web.blueprints.settings.helpers import (
    logger,
    _check_service_status,
    _get_effective_url,
    _get_effective_timeout,
    _get_effective_backend,
)

bp = Blueprint("settings_ui", __name__)

VALID_TABS = frozenset({"connections", "scraping", "pipeline", "maintenance", "advanced"})


# ---------------------------------------------------------------------------
# Per-tab context builders
# ---------------------------------------------------------------------------

def _base_context():
    """Context shared by every tab."""
    settings_mgr = container.settings
    return {
        "settings": settings_mgr.get_all(),
        "config": Config,
    }


def _build_connections_context():
    """Context for the Connections tab (service URLs, health checks, directories)."""
    ctx = _base_context()

    # Effective URLs and timeouts
    eff_gotenberg_url = _get_effective_url("gotenberg", "GOTENBERG_URL")
    eff_gotenberg_timeout = _get_effective_timeout("gotenberg", "GOTENBERG_TIMEOUT")
    eff_tika_url = _get_effective_url("tika", "TIKA_SERVER_URL")
    eff_tika_timeout = _get_effective_timeout("tika", "TIKA_TIMEOUT")
    eff_docling_serve_url = _get_effective_url("docling_serve", "DOCLING_SERVE_URL")
    eff_docling_serve_timeout = _get_effective_timeout("docling_serve", "DOCLING_SERVE_TIMEOUT")
    eff_paperless_url = _get_effective_url("paperless", "PAPERLESS_API_URL")
    eff_paperless_timeout = _get_effective_timeout("paperless", "PAPERLESS_TIMEOUT")
    eff_ragflow_url = _get_effective_url("ragflow", "RAGFLOW_API_URL")
    eff_ragflow_timeout = _get_effective_timeout("ragflow", "RAGFLOW_SESSION_TIMEOUT")
    eff_anythingllm_url = _get_effective_url("anythingllm", "ANYTHINGLLM_API_URL")
    eff_anythingllm_timeout = _get_effective_timeout("anythingllm", "ANYTHINGLLM_TIMEOUT")
    eff_embedding_url = _get_effective_url("embedding", "EMBEDDING_URL")
    eff_embedding_timeout = _get_effective_timeout("embedding", "EMBEDDING_TIMEOUT")
    eff_pgvector_url = _get_effective_url("pgvector", "DATABASE_URL")
    eff_llm_url_direct = _get_effective_url("llm", "LLM_URL")
    eff_llm_url = eff_llm_url_direct or _get_effective_url("embedding", "EMBEDDING_URL")
    llm_url_is_fallback = not eff_llm_url_direct and bool(eff_llm_url)
    eff_llm_timeout = _get_effective_timeout("llm", "LLM_TIMEOUT")

    # Service health checks
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
                timeout=Config.HEALTH_CHECK_TIMEOUT,
            )
            return resp.status_code == 200
        paperless_status = _check_service_status(_check_paperless, "paperless")

    docling_serve_status = "not_configured"
    if eff_docling_serve_url:
        def _check_docling():
            resp = http_requests.get(f"{eff_docling_serve_url}/health", timeout=Config.HEALTH_CHECK_TIMEOUT)
            return resp.ok
        docling_serve_status = _check_service_status(_check_docling, "docling_serve")

    ragflow_status = "unknown"
    try:
        ragflow_client = container.ragflow_client
        if ragflow_client.test_connection():
            ragflow_status = "connected"
        else:
            ragflow_status = "disconnected"
    except Exception as exc:
        log_exception(logger, exc, "ragflow.connection.error", page="settings")
        ragflow_status = "error"

    pgvector_status = "not_configured"
    if eff_pgvector_url:
        pgvector_status = _check_service_status(
            lambda: container.pgvector_client.test_connection(), "pgvector"
        )

    embedding_status = "not_configured"
    if eff_embedding_url:
        embedding_status = _check_service_status(
            lambda: container.embedding_client.test_connection(), "embedding"
        )

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

    llm_status = "not_configured"
    if eff_llm_url:
        llm_status = _check_service_status(
            lambda: container.llm_client.test_connection(), "llm"
        )

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

    ctx.update(
        gotenberg_status=gotenberg_status,
        tika_status=tika_status,
        paperless_status=paperless_status,
        docling_serve_status=docling_serve_status,
        ragflow_status=ragflow_status,
        anythingllm_status=anythingllm_status,
        pgvector_status=pgvector_status,
        embedding_status=embedding_status,
        llm_status=llm_status,
        flaresolverr_status=flaresolverr_status,
        eff_gotenberg_url=eff_gotenberg_url,
        eff_gotenberg_timeout=eff_gotenberg_timeout,
        eff_tika_url=eff_tika_url,
        eff_tika_timeout=eff_tika_timeout,
        eff_docling_serve_url=eff_docling_serve_url,
        eff_docling_serve_timeout=eff_docling_serve_timeout,
        eff_paperless_url=eff_paperless_url,
        eff_paperless_timeout=eff_paperless_timeout,
        eff_ragflow_url=eff_ragflow_url,
        eff_ragflow_timeout=eff_ragflow_timeout,
        eff_anythingllm_url=eff_anythingllm_url,
        eff_anythingllm_timeout=eff_anythingllm_timeout,
        eff_embedding_url=eff_embedding_url,
        eff_embedding_timeout=eff_embedding_timeout,
        eff_pgvector_url=eff_pgvector_url,
        eff_llm_url=eff_llm_url,
        llm_url_is_fallback=llm_url_is_fallback,
        eff_llm_timeout=eff_llm_timeout,
    )
    return ctx


def _build_scraping_context():
    """Context for the Scraping tab (FlareSolverr behavior, scraping defaults, RAGFlow dataset config)."""
    ctx = _base_context()

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

    # RAGFlow models for dataset config
    ragflow_models = []
    ragflow_chunk_methods = []
    ragflow_providers = {}
    ragflow_client = None

    try:
        ragflow_client = container.ragflow_client
    except Exception as exc:
        log_event(logger, "debug", "ragflow.client.unavailable", error=str(exc), page="settings")

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

    ctx.update(
        flaresolverr_status=flaresolverr_status,
        ragflow_models=ragflow_models,
        ragflow_providers=ragflow_providers,
        ragflow_chunk_methods=ragflow_chunk_methods,
    )
    return ctx


def _build_pipeline_context():
    """Context for the Pipeline tab (backends, enrichment, chunking)."""
    ctx = _base_context()
    current_settings = ctx["settings"]

    eff_parser_backend = _get_effective_backend("parser")
    eff_archive_backend = _get_effective_backend("archive")
    eff_rag_backend = _get_effective_backend("rag")

    eff_gotenberg_url = _get_effective_url("gotenberg", "GOTENBERG_URL")

    pipeline_settings = current_settings.get("pipeline", {})
    current_merge_strategy = pipeline_settings.get("metadata_merge_strategy", "") or Config.METADATA_MERGE_STRATEGY
    current_filename_template = pipeline_settings.get("filename_template", "") or Config.FILENAME_TEMPLATE

    # Enrichment toggles
    tika_enrichment_override = pipeline_settings.get("tika_enrichment_enabled", "")
    if tika_enrichment_override != "":
        tika_enrichment_active = tika_enrichment_override == "true"
    else:
        tika_enrichment_active = Config.TIKA_ENRICHMENT_ENABLED

    llm_enrichment_override = pipeline_settings.get("llm_enrichment_enabled", "")
    if llm_enrichment_override != "":
        llm_enrichment_active = llm_enrichment_override == "true"
    else:
        llm_enrichment_active = Config.LLM_ENRICHMENT_ENABLED

    contextual_enrichment_override = pipeline_settings.get("contextual_enrichment_enabled", "")
    if contextual_enrichment_override != "":
        contextual_enrichment_active = contextual_enrichment_override == "true"
    else:
        contextual_enrichment_active = Config.CONTEXTUAL_ENRICHMENT_ENABLED

    ctx.update(
        eff_parser_backend=eff_parser_backend,
        eff_archive_backend=eff_archive_backend,
        eff_rag_backend=eff_rag_backend,
        eff_gotenberg_url=eff_gotenberg_url,
        current_merge_strategy=current_merge_strategy,
        current_filename_template=current_filename_template,
        tika_enrichment_active=tika_enrichment_active,
        llm_enrichment_active=llm_enrichment_active,
        contextual_enrichment_active=contextual_enrichment_active,
    )
    return ctx


def _build_maintenance_context():
    """Context for the Maintenance tab (state reconciliation)."""
    ctx = _base_context()
    ctx["scraper_names"] = ScraperRegistry.get_scraper_names()
    return ctx


def _build_advanced_context():
    """Context for the Advanced tab (tuning parameters)."""
    return _base_context()


_TAB_BUILDERS = {
    "connections": _build_connections_context,
    "scraping": _build_scraping_context,
    "pipeline": _build_pipeline_context,
    "maintenance": _build_maintenance_context,
    "advanced": _build_advanced_context,
}


def _build_tab_context(tab: str) -> dict:
    """Build template context for a specific tab."""
    builder = _TAB_BUILDERS.get(tab, _build_connections_context)
    return builder()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/settings")
def settings_page():
    tab = request.args.get("tab", "connections")
    if tab not in VALID_TABS:
        tab = "connections"

    ctx = _build_tab_context(tab)
    ctx["active_tab"] = tab

    log_event(logger, "info", "ui.page.settings", tab=tab)
    return render_template("settings.html", **ctx)


@bp.route("/settings/tab/<tab>")
def settings_tab(tab: str):
    """Return partial HTML fragment for a settings tab (HTMX)."""
    if not re.match(r'^[a-z]+$', tab) or tab not in VALID_TABS:
        return "Not found", 404
    ctx = _build_tab_context(tab)
    return render_template(f"settings/_tab_{tab}.html", **ctx)
