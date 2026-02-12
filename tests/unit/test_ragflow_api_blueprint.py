"""Tests for the ragflow_api blueprint (app/web/blueprints/ragflow_api.py).

Covers get_ragflow_models and get_ragflow_chunk_methods.
"""

import base64

import pytest
from unittest.mock import patch, MagicMock

import requests

from app.config import Config
from app.utils.errors import ValidationError, ConfigurationError
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


def _make_http_error(status_code):
    """Create a requests.HTTPError with a mock response having the given status code."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    error = requests.HTTPError(response=mock_response)
    return error


# ===================================================================
# get_ragflow_models
# ===================================================================


class TestGetRagflowModels:
    """GET /api/ragflow/models"""

    def test_success(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.return_value = [
            {"name": "bge-large-en", "provider": "BAAI"},
        ]

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "bge-large-en"

    def test_http_error_401(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.side_effect = _make_http_error(401)

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False

    def test_http_error_400(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.side_effect = _make_http_error(400)

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_validation_error(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.side_effect = ValidationError("bad input")

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_configuration_error(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.side_effect = ConfigurationError("not configured")

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False

    def test_generic_exception(self, client):
        mock_client = MagicMock()
        mock_client.list_embedding_models.side_effect = RuntimeError("unexpected")

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/models")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False


# ===================================================================
# get_ragflow_chunk_methods
# ===================================================================


class TestGetRagflowChunkMethods:
    """GET /api/ragflow/chunk-methods"""

    def test_success(self, client):
        mock_client = MagicMock()
        mock_client.list_chunk_methods.return_value = ["naive", "paper", "book"]

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/chunk-methods")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "naive" in data["methods"]
        assert len(data["methods"]) == 3

    def test_error(self, client):
        mock_client = MagicMock()
        mock_client.list_chunk_methods.side_effect = RuntimeError("fail")

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/chunk-methods")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["success"] is False

    def test_http_error_403(self, client):
        mock_client = MagicMock()
        mock_client.list_chunk_methods.side_effect = _make_http_error(403)

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/chunk-methods")

        # 403 maps to 401 in the error handler
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False

    def test_http_error_404(self, client):
        mock_client = MagicMock()
        mock_client.list_chunk_methods.side_effect = _make_http_error(404)

        with patch("app.web.blueprints.ragflow_api.RAGFlowClient", return_value=mock_client):
            resp = client.get("/api/ragflow/chunk-methods")

        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False
