"""Tests for the settings reconciliation blueprint (app/web/blueprints/settings/reconciliation.py).

Covers reconciliation_report, reconciliation_rebuild, and reconciliation_sync_rag routes.
"""

import base64

import pytest
from unittest.mock import patch, MagicMock

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
            "ragflow_url": "", "anythingllm_url": "", "embedding_url": "",
            "embedding_timeout": 0, "pgvector_url": "", "llm_url": "", "llm_timeout": 0,
        },
        "application": {"name": "PDF Scraper", "version": "0.1.0"},
        "scrapers": {},
        "scheduler": {"enabled": False, "run_on_startup": False},
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
    mock._get_state_store.return_value = None  # no batch DB path
    mock.ragflow_client.test_connection.return_value = False
    mock.ragflow_client.list_embedding_models.return_value = []
    mock.ragflow_client.list_chunk_methods.return_value = []
    mock.ragflow_client.list_pdf_parsers.return_value = []
    mock.ragflow_client.list_ingestion_pipelines.return_value = []
    mock.ragflow_client.session_configured = False
    mock.flaresolverr_client.test_connection.return_value = False
    mock.flaresolverr_client.get_metrics.return_value = {
        "success": 5, "failure": 1, "timeout": 0, "total": 6, "success_rate": 83.3,
    }
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
def app(mock_container):
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
        patch("app.web.helpers.container", mock_container),
        patch("app.web.blueprints.settings.ui.http_requests"),
        patch("app.web.blueprints.settings.api.http_requests"),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.job_queue"),
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
# Reconciliation Report
# ===================================================================


class TestReconciliationReport:
    """POST /settings/reconciliation/report/<name>"""

    def test_invalid_name(self, client):
        resp = client.post("/settings/reconciliation/report/bad name!")
        assert resp.status_code == 200
        assert b"Invalid scraper name" in resp.data

    def test_success_basic(self, client):
        mock_report = MagicMock()
        mock_report.errors = []
        mock_report.urls_only_in_state = []
        mock_report.urls_only_in_paperless = []
        mock_report.urls_in_paperless_not_rag = []
        mock_report.state_url_count = 10
        mock_report.paperless_url_count = 8
        mock_report.rag_document_count = 7

        mock_service = MagicMock()
        mock_service.get_report.return_value = mock_report

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/report/test_scraper")

        assert resp.status_code == 200
        assert b"Reconciliation Report" in resp.data
        assert b"test_scraper" in resp.data
        assert b"10" in resp.data  # state_url_count
        assert b"8" in resp.data   # paperless_url_count
        assert b"7" in resp.data   # rag_document_count

    def test_success_with_errors_and_urls(self, client):
        mock_report = MagicMock()
        mock_report.errors = ["Error 1", "Error 2"]
        mock_report.urls_only_in_state = ["http://a.com/1.pdf", "http://a.com/2.pdf"]
        mock_report.urls_only_in_paperless = ["http://b.com/3.pdf"]
        mock_report.urls_in_paperless_not_rag = ["http://c.com/4.pdf"]
        mock_report.state_url_count = 5
        mock_report.paperless_url_count = 4
        mock_report.rag_document_count = 3

        mock_service = MagicMock()
        mock_service.get_report.return_value = mock_report

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/report/my-scraper")

        assert resp.status_code == 200
        assert b"Error 1" in resp.data
        assert b"Error 2" in resp.data
        assert b"2 URLs only in state" in resp.data
        assert b"1 URLs only in Paperless" in resp.data
        assert b"1 URLs in Paperless but not RAG" in resp.data

    def test_success_with_many_urls_truncated(self, client):
        """When more than 50 URLs, shows truncation message."""
        mock_report = MagicMock()
        mock_report.errors = []
        urls = [f"http://a.com/{i}.pdf" for i in range(60)]
        mock_report.urls_only_in_state = urls
        mock_report.urls_only_in_paperless = []
        mock_report.urls_in_paperless_not_rag = []
        mock_report.state_url_count = 60
        mock_report.paperless_url_count = 0
        mock_report.rag_document_count = 0

        mock_service = MagicMock()
        mock_service.get_report.return_value = mock_report

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/report/test_scraper")

        assert resp.status_code == 200
        assert b"... and 10 more" in resp.data

    def test_exception(self, client):
        with patch(
            "app.services.reconciliation.ReconciliationService",
            side_effect=RuntimeError("service down"),
        ):
            resp = client.post("/settings/reconciliation/report/test_scraper")

        assert resp.status_code == 200
        assert b"Report failed" in resp.data
        assert b"service down" in resp.data


# ===================================================================
# Reconciliation Rebuild
# ===================================================================


class TestReconciliationRebuild:
    """POST /settings/reconciliation/rebuild/<name>"""

    def test_invalid_name(self, client):
        resp = client.post("/settings/reconciliation/rebuild/bad%20name!")
        assert resp.status_code == 200
        assert b"Invalid scraper name" in resp.data

    def test_success(self, client):
        mock_service = MagicMock()
        mock_service.rebuild_state.return_value = 42

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/rebuild/my_scraper")

        assert resp.status_code == 200
        assert b"State rebuilt" in resp.data
        assert b"42 URLs added from Paperless" in resp.data
        assert b"my_scraper" in resp.data

    def test_exception(self, client):
        with patch(
            "app.services.reconciliation.ReconciliationService",
            side_effect=RuntimeError("rebuild failed"),
        ):
            resp = client.post("/settings/reconciliation/rebuild/test_scraper")

        assert resp.status_code == 200
        assert b"Rebuild failed" in resp.data
        assert b"rebuild failed" in resp.data


# ===================================================================
# Reconciliation Sync RAG
# ===================================================================


class TestReconciliationSyncRag:
    """POST /settings/reconciliation/sync-rag/<name>"""

    def test_invalid_name(self, client):
        resp = client.post("/settings/reconciliation/sync-rag/bad%20name!")
        assert resp.status_code == 200
        assert b"Invalid scraper name" in resp.data

    def test_success_with_urls(self, client):
        mock_service = MagicMock()
        mock_service.sync_rag_gaps.return_value = [
            "http://a.com/1.pdf",
            "http://a.com/2.pdf",
        ]

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/sync-rag/my_scraper")

        assert resp.status_code == 200
        assert b"RAG sync complete" in resp.data
        assert b"2 documents re-ingested" in resp.data
        assert b"http://a.com/1.pdf" in resp.data

    def test_success_with_many_urls_truncated(self, client):
        mock_service = MagicMock()
        urls = [f"http://a.com/{i}.pdf" for i in range(25)]
        mock_service.sync_rag_gaps.return_value = urls

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/sync-rag/my_scraper")

        assert resp.status_code == 200
        assert b"25 documents re-ingested" in resp.data
        assert b"... and 5 more" in resp.data

    def test_no_docs_needed(self, client):
        mock_service = MagicMock()
        mock_service.sync_rag_gaps.return_value = []

        with patch(
            "app.services.reconciliation.ReconciliationService",
            return_value=mock_service,
        ):
            resp = client.post("/settings/reconciliation/sync-rag/my_scraper")

        assert resp.status_code == 200
        assert b"No documents needed re-ingestion" in resp.data
        assert b"RAG is in sync with Paperless" in resp.data

    def test_exception(self, client):
        with patch(
            "app.services.reconciliation.ReconciliationService",
            side_effect=RuntimeError("sync failed"),
        ):
            resp = client.post("/settings/reconciliation/sync-rag/test_scraper")

        assert resp.status_code == 200
        assert b"RAG sync failed" in resp.data
        assert b"sync failed" in resp.data
