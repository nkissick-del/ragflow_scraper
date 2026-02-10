"""Settings API routes: service tests and save handlers."""

from __future__ import annotations

import requests as http_requests

from flask import Blueprint, request
from markupsafe import escape

from app.config import Config
from app.utils.logging_config import log_exception
from app.web.runtime import container
from app.web.blueprints.settings.helpers import (
    logger,
    _MAX_URL_LENGTH,
    _MAX_FIELD_LENGTH,
    _MAX_TEMPLATE_LENGTH,
    _get_effective_url,
    _validate_url_ssrf,
)

bp = Blueprint("settings_api", __name__)


# --------------- service test routes ---------------

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
        log_exception(logger, exc, "ragflow.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-flaresolverr", methods=["POST"])
def test_flaresolverr():
    if not Config.FLARESOLVERR_URL:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.flaresolverr_client
        if client.test_connection():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "flaresolverr.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


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


@bp.route("/settings/test-pgvector", methods=["POST"])
def test_pgvector():
    eff_url = _get_effective_url("pgvector", "DATABASE_URL")
    if not eff_url:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.pgvector_client
        if client.test_connection():
            stats = client.get_stats()
            return f'''
                <span class="status-badge status-connected">Connected</span>
                <p class="mt-2">{stats.get("total_chunks", 0)} chunks across {stats.get("total_sources", 0)} source(s)</p>
            '''
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "pgvector.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-embedding", methods=["POST"])
def test_embedding():
    eff_url = _get_effective_url("embedding", "EMBEDDING_URL")
    if not eff_url:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.embedding_client
        if client.test_connection():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "embedding.test.error")
        return '<span class="status-badge status-error">Connection test failed</span>'


@bp.route("/settings/test-llm", methods=["POST"])
def test_llm():
    eff_url = _get_effective_url("llm", "LLM_URL")
    if not eff_url:
        # Fall back to embedding URL (same Ollama server)
        eff_url = _get_effective_url("embedding", "EMBEDDING_URL")
    if not eff_url:
        return '<span class="status-badge status-not_configured">Not Configured</span>'

    try:
        client = container.llm_client
        if client.test_connection():
            return '<span class="status-badge status-connected">Connected</span>'
        else:
            return '<span class="status-badge status-disconnected">Connection Failed</span>'
    except Exception as exc:
        log_exception(logger, exc, "llm.test.error")
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


# --------------- save handlers ---------------

@bp.route("/settings/flaresolverr", methods=["POST"])
def save_flaresolverr_settings():
    settings_mgr = container.settings

    enabled = request.form.get("enabled") == "on"
    timeout = request.form.get("timeout", 60, type=int)
    max_timeout = request.form.get("max_timeout", 120, type=int)

    if not (1 <= timeout <= 600):
        return '''
            <div class="alert alert-danger">
                Timeout must be between 1 and 600 seconds.
            </div>
        '''
    if not (1 <= max_timeout <= 600):
        return '''
            <div class="alert alert-danger">
                Max timeout must be between 1 and 600 seconds.
            </div>
        '''
    if max_timeout < timeout:
        return '''
            <div class="alert alert-danger">
                Max timeout must be greater than or equal to timeout.
            </div>
        '''

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

    if not (0 <= request_delay <= 60):
        return '''
            <div class="alert alert-danger">
                Request delay must be between 0 and 60 seconds.
            </div>
        '''
    if not (1 <= timeout <= 600):
        return '''
            <div class="alert alert-danger">
                Timeout must be between 1 and 600 seconds.
            </div>
        '''
    if not (0 <= retry_attempts <= 10):
        return '''
            <div class="alert alert-danger">
                Retry attempts must be between 0 and 10.
            </div>
        '''

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
    if default_embedding_model and len(default_embedding_model) > _MAX_FIELD_LENGTH:
        return f'''
            <div class="alert alert-danger">
                Embedding model name exceeds maximum length of {_MAX_FIELD_LENGTH} characters.
            </div>
        '''
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
    embedding_url = request.form.get("embedding_url", "").strip()
    pgvector_url = request.form.get("pgvector_url", "").strip()
    llm_url = request.form.get("llm_url", "").strip()

    # Extract timeouts
    gotenberg_timeout = request.form.get("gotenberg_timeout", 0, type=int)
    tika_timeout = request.form.get("tika_timeout", 0, type=int)
    docling_serve_timeout = request.form.get("docling_serve_timeout", 0, type=int)
    embedding_timeout = request.form.get("embedding_timeout", 0, type=int)
    llm_timeout = request.form.get("llm_timeout", 0, type=int)

    # Validate pgvector database URL length, scheme, + SSRF
    if pgvector_url and len(pgvector_url) > _MAX_URL_LENGTH:
        return f'''
            <div class="alert alert-danger">
                pgvector URL exceeds maximum length of {_MAX_URL_LENGTH} characters.
            </div>
        '''
    if pgvector_url and not pgvector_url.startswith(("postgresql://", "postgres://")):
        return '''
            <div class="alert alert-danger">
                pgvector URL must start with postgresql:// or postgres://
            </div>
        '''
    if pgvector_url:
        ssrf_err = _validate_url_ssrf(pgvector_url)
        if ssrf_err:
            return f'''
                <div class="alert alert-danger">
                    pgvector: {escape(ssrf_err)}
                </div>
            '''

    # Validate URLs (length, scheme, SSRF check)
    for label, url in [
        ("Gotenberg", gotenberg_url),
        ("Tika", tika_url),
        ("Docling-serve", docling_serve_url),
        ("Paperless", paperless_url),
        ("RAGFlow", ragflow_url),
        ("AnythingLLM", anythingllm_url),
        ("Embedding", embedding_url),
        ("LLM", llm_url),
    ]:
        if url and len(url) > _MAX_URL_LENGTH:
            return f'''
                <div class="alert alert-danger">
                    {escape(label)} URL exceeds maximum length of {_MAX_URL_LENGTH} characters.
                </div>
            '''
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
        ("Embedding", embedding_timeout),
        ("LLM", llm_timeout),
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
        "embedding_url": embedding_url,
        "embedding_timeout": embedding_timeout,
        "pgvector_url": pgvector_url,
        "llm_url": llm_url,
        "llm_timeout": llm_timeout,
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

    # LLM enrichment settings
    llm_enrichment = request.form.get("llm_enrichment_enabled", "")
    llm_enrichment_value = "true" if llm_enrichment else "false"
    contextual_enrichment = request.form.get("contextual_enrichment_enabled", "")
    contextual_enrichment_value = "true" if contextual_enrichment else "false"
    llm_enrichment_max_tokens = request.form.get("llm_enrichment_max_tokens", 0, type=int)
    contextual_enrichment_window = request.form.get("contextual_enrichment_window", 0, type=int)
    llm_backend = request.form.get("llm_backend", "")
    llm_model = request.form.get("llm_model", "")

    # Embedding / chunking pipeline settings
    embedding_backend = request.form.get("embedding_backend", "")
    embedding_model = request.form.get("embedding_model", "")
    chunking_strategy = request.form.get("chunking_strategy", "")
    chunk_max_tokens = request.form.get("chunk_max_tokens", 0, type=int)
    chunk_overlap_tokens = request.form.get("chunk_overlap_tokens", 0, type=int)

    # Length validation
    if filename_template and len(filename_template) > _MAX_TEMPLATE_LENGTH:
        return f'''
            <div class="alert alert-danger">
                Filename template exceeds maximum length of {_MAX_TEMPLATE_LENGTH} characters.
            </div>
        '''
    if embedding_model and len(embedding_model) > _MAX_FIELD_LENGTH:
        return f'''
            <div class="alert alert-danger">
                Embedding model name exceeds maximum length of {_MAX_FIELD_LENGTH} characters.
            </div>
        '''
    if llm_model and len(llm_model) > _MAX_FIELD_LENGTH:
        return f'''
            <div class="alert alert-danger">
                LLM model name exceeds maximum length of {_MAX_FIELD_LENGTH} characters.
            </div>
        '''

    # Range validation for LLM settings
    if llm_enrichment_max_tokens != 0 and not (1000 <= llm_enrichment_max_tokens <= 128000):
        return '''
            <div class="alert alert-danger">
                LLM max tokens must be 0 (use default) or between 1,000 and 128,000.
            </div>
        '''
    if contextual_enrichment_window != 0 and not (1 <= contextual_enrichment_window <= 10):
        return '''
            <div class="alert alert-danger">
                Contextual enrichment window must be 0 (use default) or between 1 and 10.
            </div>
        '''
    if llm_backend and llm_backend not in Config.VALID_LLM_BACKENDS:
        return f'''
            <div class="alert alert-danger">
                Invalid LLM backend: {escape(llm_backend)}.
                Must be one of: {", ".join(Config.VALID_LLM_BACKENDS)}
            </div>
        '''

    # Range validation for chunk settings
    if chunk_max_tokens != 0 and not (1 <= chunk_max_tokens <= 8192):
        return '''
            <div class="alert alert-danger">
                Chunk max tokens must be 0 (use default) or between 1 and 8192.
            </div>
        '''
    if chunk_overlap_tokens != 0 and not (0 <= chunk_overlap_tokens <= 4096):
        return '''
            <div class="alert alert-danger">
                Chunk overlap tokens must be 0 (use default) or between 0 and 4096.
            </div>
        '''

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
        "llm_backend": llm_backend,
        "llm_model": llm_model,
        "llm_enrichment_enabled": llm_enrichment_value,
        "llm_enrichment_max_tokens": llm_enrichment_max_tokens,
        "contextual_enrichment_enabled": contextual_enrichment_value,
        "contextual_enrichment_window": contextual_enrichment_window,
        "embedding_backend": embedding_backend,
        "embedding_model": embedding_model,
        "chunking_strategy": chunking_strategy,
        "chunk_max_tokens": chunk_max_tokens,
        "chunk_overlap_tokens": chunk_overlap_tokens,
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
