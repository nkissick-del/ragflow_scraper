"""Tests for the API ingest blueprint (app/web/blueprints/api_ingest.py).

Covers api_ingest_sync and api_ingest_documents endpoints.
"""

import base64

import pytest
from unittest.mock import patch, MagicMock, Mock

from app.config import Config
from app.web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUTH_HEADER = {
    "Authorization": "Basic " + base64.b64encode(b"testuser:testpass").decode()
}


def _make_mock_settings():
    mock = MagicMock()
    mock.get_all.return_value = {
        "ragflow": {
            "default_dataset_id": "", "auto_upload": False, "auto_create_dataset": True,
            "default_embedding_model": "", "default_chunk_method": "paper",
            "wait_for_parsing": True,
            "parser_config": {"chunk_token_num": 128, "layout_recognize": "DeepDOC"},
        },
        "flaresolverr": {"enabled": False, "timeout": 60, "max_timeout": 120},
        "scraping": {
            "use_flaresolverr_by_default": False, "default_request_delay": 2.0,
            "default_timeout": 60, "default_retry_attempts": 3, "max_concurrent_downloads": 3,
        },
        "pipeline": {
            "metadata_merge_strategy": "", "filename_template": "",
            "parser_backend": "", "archive_backend": "", "rag_backend": "",
        },
        "services": {
            "gotenberg_url": "", "gotenberg_timeout": 0, "tika_url": "", "tika_timeout": 0,
            "docling_serve_url": "", "docling_serve_timeout": 0, "paperless_url": "",
            "paperless_timeout": 0, "ragflow_url": "", "ragflow_timeout": 0,
            "anythingllm_url": "", "anythingllm_timeout": 0, "embedding_url": "",
            "embedding_timeout": 0, "pgvector_url": "", "llm_url": "", "llm_timeout": 0,
        },
        "application": {"name": "PDF Scraper", "version": "0.1.0"},
        "scrapers": {},
        "scheduler": {"enabled": False, "run_on_startup": False},
        "advanced": {
            "health_check_timeout": 0, "paperless_upload_timeout": 0,
            "paperless_retry_attempts": 0, "paperless_retry_backoff": 0,
            "paperless_poll_interval": 0, "paperless_poll_timeout": 0,
            "ragflow_max_retries": 0, "ragflow_parse_timeout": 0,
            "ragflow_poll_interval": 0, "ragflow_session_timeout": 0,
            "anythingllm_max_retries": 0, "db_pool_min_size": 0,
            "db_pool_max_size": 0, "db_pool_timeout": 0,
            "flaresolverr_cache_ttl": 0, "flaresolverr_cache_max_size": 0,
            "search_max_results": 0, "search_default_limit": 0,
            "embedding_batch_size": 0, "retry_backoff_factor": 0,
            "retry_jitter": 0,
        },
    }
    mock.flaresolverr_enabled = False

    _all = mock.get_all.return_value

    def _mock_get(key, default=None):
        keys = key.split(".")
        value = _all
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    mock.get.side_effect = _mock_get
    return mock


def _make_mock_container():
    mock = MagicMock()
    mock.settings = _make_mock_settings()
    mock._get_state_store.return_value = None
    mock.ragflow_client.test_connection.return_value = False
    mock.ragflow_client.list_embedding_models.return_value = []
    mock.ragflow_client.list_chunk_methods.return_value = []
    mock.ragflow_client.list_pdf_parsers.return_value = []
    mock.ragflow_client.list_ingestion_pipelines.return_value = []
    mock.ragflow_client.session_configured = False
    mock.flaresolverr_client.test_connection.return_value = False
    mock.gotenberg_client.health_check.return_value = False
    mock.tika_client.health_check.return_value = False
    mock.state_tracker.return_value.get_all_status.return_value = {}
    mock.state_tracker.return_value.get_status.return_value = {
        "scraper": "test", "status": "idle", "is_running": False,
    }
    mock.state_tracker.return_value.get_last_run_info.return_value = {}
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_container():
    return _make_mock_container()


@pytest.fixture
def mock_job_queue():
    return MagicMock()


@pytest.fixture
def app(mock_container, mock_job_queue):
    patches = [
        patch.object(Config, "BASIC_AUTH_ENABLED", True),
        patch.object(Config, "BASIC_AUTH_USERNAME", "testuser"),
        patch.object(Config, "BASIC_AUTH_PASSWORD", "testpass"),
        patch.object(Config, "SECRET_KEY", "test-secret-key"),
        patch("app.web.blueprints.settings.ui.container", mock_container),
        patch("app.web.blueprints.settings.api.container", mock_container),
        patch("app.web.blueprints.settings.helpers.container", mock_container),
        patch("app.web.blueprints.settings.reconciliation.container", mock_container),
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.metrics_logs.container", mock_container),
        patch("app.web.blueprints.api_ingest.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.blueprints.settings.ui.http_requests"),
        patch("app.web.blueprints.settings.api.http_requests"),
        patch("app.web.blueprints.scrapers.job_queue", mock_job_queue),
        patch("app.web.blueprints.api_scrapers.job_queue", mock_job_queue),
        patch("app.web.helpers.job_queue", mock_job_queue),
    ]

    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)

        flask_app = create_app()
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        flask_app.config["RATELIMIT_ENABLED"] = False
        yield flask_app
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    _HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})

    class AuthClient:
        def __init__(self, test_client):
            self._client = test_client

        def __getattr__(self, name):
            attr = getattr(self._client, name)
            if callable(attr) and name in _HTTP_METHODS:
                def _wrapper(*args, **kwargs):
                    headers = dict(kwargs.pop("headers", {}) or {})
                    headers.update(_AUTH_HEADER)
                    return attr(*args, headers=headers, **kwargs)
                return _wrapper
            return attr

    return AuthClient(app.test_client())


# ===================================================================
# POST /api/ingest/sync/<scraper_name>
# ===================================================================


class TestApiIngestSync:
    """POST /api/ingest/sync/<scraper_name>"""

    def test_invalid_scraper_name_rejected(self, client):
        """Should return 400 for invalid scraper name."""
        resp = client.post(
            "/api/ingest/sync/bad;name",
            json={"dry_run": True},
        )
        assert resp.status_code == 400
        assert "Invalid scraper name" in resp.get_json()["error"]

    def test_dry_run_default_true(self, client):
        """Should default to dry_run=True for safety."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_recon = Mock()
            mock_recon.sync_rag_gaps.return_value = ["https://example.com/a.pdf"]
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/sync/aemo",
                json={},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["dry_run"] is True
            assert data["count"] == 1
            mock_recon.sync_rag_gaps.assert_called_once_with("aemo", dry_run=True)

    def test_dry_run_false(self, client):
        """Should honor dry_run=False."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_recon = Mock()
            mock_recon.sync_rag_gaps.return_value = [
                "https://example.com/a.pdf",
                "https://example.com/b.pdf",
            ]
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/sync/aemo",
                json={"dry_run": False},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["dry_run"] is False
            assert data["count"] == 2
            assert len(data["synced_urls"]) == 2
            mock_recon.sync_rag_gaps.assert_called_once_with("aemo", dry_run=False)

    def test_no_gaps_returns_empty(self, client):
        """Should return empty list when no gaps exist."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_recon = Mock()
            mock_recon.sync_rag_gaps.return_value = []
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/sync/aemo",
                json={"dry_run": False},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["count"] == 0
            assert data["synced_urls"] == []

    def test_runtime_error_returns_503(self, client):
        """Should return 503 when Paperless is unavailable."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_recon = Mock()
            mock_recon.sync_rag_gaps.side_effect = RuntimeError("Paperless not configured")
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/sync/aemo",
                json={"dry_run": True},
            )

            assert resp.status_code == 503

    def test_unexpected_error_returns_500(self, client):
        """Should return 500 on unexpected errors."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_cls.side_effect = Exception("unexpected")

            resp = client.post(
                "/api/ingest/sync/aemo",
                json={},
            )

            assert resp.status_code == 500


# ===================================================================
# POST /api/ingest/documents
# ===================================================================


class TestApiIngestDocuments:
    """POST /api/ingest/documents"""

    def test_missing_document_ids_rejected(self, client):
        """Should return 400 when document_ids is missing."""
        resp = client.post(
            "/api/ingest/documents",
            json={},
        )
        assert resp.status_code == 400
        assert "document_ids" in resp.get_json()["error"]

    def test_empty_document_ids_rejected(self, client):
        """Should return 400 when document_ids is empty."""
        resp = client.post(
            "/api/ingest/documents",
            json={"document_ids": []},
        )
        assert resp.status_code == 400

    def test_invalid_document_id_rejected(self, client):
        """Should return 400 when document_ids contains invalid values."""
        resp = client.post(
            "/api/ingest/documents",
            json={"document_ids": ["not-an-int"]},
        )
        assert resp.status_code == 400

    def test_negative_document_id_rejected(self, client):
        """Should return 400 when document_ids contains negative values."""
        resp = client.post(
            "/api/ingest/documents",
            json={"document_ids": [-1]},
        )
        assert resp.status_code == 400

    def test_zero_document_id_rejected(self, client):
        """Should return 400 when document_ids contains zero."""
        resp = client.post(
            "/api/ingest/documents",
            json={"document_ids": [0]},
        )
        assert resp.status_code == 400

    def test_successful_reingest(self, client):
        """Should return results for each document."""
        with (
            patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls,
            patch.object(Config, "RAGFLOW_DATASET_ID", ""),
        ):
            mock_recon = Mock()
            mock_recon._get_paperless_client.return_value = Mock()
            mock_recon._get_paperless_client.return_value.get_document.return_value = {
                "custom_fields": []
            }
            mock_recon._reingest_document.return_value = True
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/documents",
                json={"document_ids": [1, 2]},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert len(data["results"]) == 2

    def test_partial_failure(self, client):
        """Should report partial failures."""
        with (
            patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls,
            patch.object(Config, "RAGFLOW_DATASET_ID", ""),
        ):
            mock_recon = Mock()
            mock_recon._get_paperless_client.return_value = Mock()
            mock_recon._get_paperless_client.return_value.get_document.return_value = {
                "custom_fields": []
            }
            mock_recon._reingest_document.side_effect = [True, False]
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/documents",
                json={"document_ids": [1, 2]},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2
        assert data["succeeded"] == 1

    def test_custom_source_label(self, client):
        """Should pass custom source label to _reingest_document."""
        with (
            patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls,
            patch.object(Config, "RAGFLOW_DATASET_ID", ""),
        ):
            mock_recon = Mock()
            mock_recon._get_paperless_client.return_value = Mock()
            mock_recon._get_paperless_client.return_value.get_document.return_value = {
                "custom_fields": []
            }
            mock_recon._reingest_document.return_value = True
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/documents",
                json={"document_ids": [1], "source": "bulk-import"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_recon._reingest_document.call_args[1]
        assert call_kwargs["source"] == "bulk-import"

    def test_runtime_error_returns_503(self, client):
        """Should return 503 when service unavailable."""
        with patch("app.web.blueprints.api_ingest.ReconciliationService") as mock_cls:
            mock_recon = Mock()
            mock_recon._get_paperless_client.side_effect = RuntimeError("no Paperless")
            mock_cls.return_value = mock_recon

            resp = client.post(
                "/api/ingest/documents",
                json={"document_ids": [1]},
            )

            assert resp.status_code == 503
