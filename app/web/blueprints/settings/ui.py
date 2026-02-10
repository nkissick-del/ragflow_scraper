"""Settings UI page route."""

from __future__ import annotations

import requests as http_requests

from flask import Blueprint, render_template

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
    eff_embedding_url = _get_effective_url("embedding", "EMBEDDING_URL")
    eff_embedding_timeout = _get_effective_timeout("embedding", "EMBEDDING_TIMEOUT")
    eff_pgvector_url = _get_effective_url("pgvector", "DATABASE_URL")

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
        pgvector_status=pgvector_status,
        embedding_status=embedding_status,
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
        eff_embedding_url=eff_embedding_url,
        eff_embedding_timeout=eff_embedding_timeout,
        eff_pgvector_url=eff_pgvector_url,
        tika_enrichment_active=tika_enrichment_active,
        scraper_names=ScraperRegistry.get_scraper_names(),
    )
