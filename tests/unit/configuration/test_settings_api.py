"""Comprehensive tests for the settings API blueprint (app/web/blueprints/settings/api.py).

Covers all service test routes, save handlers, validation, and the IOError handler.
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
    """Create a properly configured mock SettingsManager."""
    mock = MagicMock()
    mock.get_all.return_value = {
        "ragflow": {
            "default_dataset_id": "", "auto_upload": False,
            "auto_create_dataset": True, "default_embedding_model": "",
            "default_chunk_method": "paper", "wait_for_parsing": True,
            "parser_config": {"chunk_token_num": 128, "layout_recognize": "DeepDOC"},
        },
        "flaresolverr": {"enabled": False, "timeout": 60, "max_timeout": 120},
        "scraping": {
            "use_flaresolverr_by_default": False, "default_request_delay": 2.0,
            "default_timeout": 60, "default_retry_attempts": 3,
            "max_concurrent_downloads": 3,
        },
        "pipeline": {
            "metadata_merge_strategy": "", "filename_template": "",
            "parser_backend": "", "archive_backend": "", "rag_backend": "",
        },
        "services": {
            "gotenberg_url": "", "gotenberg_timeout": 0,
            "tika_url": "", "tika_timeout": 0,
            "docling_serve_url": "", "docling_serve_timeout": 0,
            "paperless_url": "", "ragflow_url": "", "anythingllm_url": "",
            "embedding_url": "", "embedding_timeout": 0,
            "pgvector_url": "", "llm_url": "", "llm_timeout": 0,
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
    """Create a fully stubbed ServiceContainer mock."""
    mock = MagicMock()
    mock.settings = _make_mock_settings()
    mock._get_state_store.return_value = None  # no batch DB path
    mock.ragflow_client.test_connection.return_value = False
    mock.ragflow_client.list_embedding_models.return_value = []
    mock.ragflow_client.list_chunk_methods.return_value = []
    mock.ragflow_client.list_datasets.return_value = []
    mock.flaresolverr_client.test_connection.return_value = False
    mock.gotenberg_client.health_check.return_value = False
    mock.tika_client.health_check.return_value = False
    mock.pgvector_client.test_connection.return_value = False
    mock.pgvector_client.get_stats.return_value = {"total_chunks": 0, "total_sources": 0}
    mock.embedding_client.test_connection.return_value = False
    mock.llm_client.test_connection.return_value = False
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
    """Expose the mock container so tests can reconfigure it."""
    return _make_mock_container()


@pytest.fixture
def app(mock_container):
    """Create a test Flask app with all necessary patches."""
    patches = [
        # Auth & secret
        patch.object(Config, "BASIC_AUTH_ENABLED", True),
        patch.object(Config, "BASIC_AUTH_USERNAME", "testuser"),
        patch.object(Config, "BASIC_AUTH_PASSWORD", "testpass"),
        patch.object(Config, "SECRET_KEY", "test-secret-key"),
        # Patch container in every module that imports it from runtime
        patch("app.web.blueprints.settings.ui.container", mock_container),
        patch("app.web.blueprints.settings.api.container", mock_container),
        patch("app.web.blueprints.settings.helpers.container", mock_container),
        patch("app.web.blueprints.settings.reconciliation.container", mock_container),
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.metrics_logs.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        # Prevent real HTTP calls from settings blueprints
        patch("app.web.blueprints.settings.ui.http_requests"),
        patch("app.web.blueprints.settings.api.http_requests"),
        # Patch job_queue in modules that use it
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
    """Flask test client that auto-injects Basic Auth headers."""
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
# Service test routes
# ===================================================================


class TestTestRagflow:
    """POST /settings/test-ragflow"""

    def test_connected(self, client, mock_container):
        mock_container.ragflow_client.test_connection.return_value = True
        mock_container.ragflow_client.list_datasets.return_value = ["ds1", "ds2"]
        resp = client.post("/settings/test-ragflow")
        assert resp.status_code == 200
        assert b"Connected" in resp.data
        assert b"2 dataset(s)" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.ragflow_client.test_connection.return_value = False
        resp = client.post("/settings/test-ragflow")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.ragflow_client.test_connection.side_effect = RuntimeError("boom")
        resp = client.post("/settings/test-ragflow")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestFlaresolverr:
    """POST /settings/test-flaresolverr"""

    def test_not_configured(self, client):
        with patch.object(Config, "FLARESOLVERR_URL", ""):
            resp = client.post("/settings/test-flaresolverr")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        with patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191"):
            mock_container.flaresolverr_client.test_connection.return_value = True
            resp = client.post("/settings/test-flaresolverr")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        with patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191"):
            mock_container.flaresolverr_client.test_connection.return_value = False
            resp = client.post("/settings/test-flaresolverr")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        with patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191"):
            mock_container.flaresolverr_client.test_connection.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-flaresolverr")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestGotenberg:
    """POST /settings/test-gotenberg"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "GOTENBERG_URL", ""):
            resp = client.post("/settings/test-gotenberg")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "GOTENBERG_URL", "http://gotenberg:3000"):
            mock_container.gotenberg_client.health_check.return_value = True
            resp = client.post("/settings/test-gotenberg")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "GOTENBERG_URL", "http://gotenberg:3000"):
            mock_container.gotenberg_client.health_check.return_value = False
            resp = client.post("/settings/test-gotenberg")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "GOTENBERG_URL", "http://gotenberg:3000"):
            mock_container.gotenberg_client.health_check.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-gotenberg")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestTika:
    """POST /settings/test-tika"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "TIKA_SERVER_URL", ""):
            resp = client.post("/settings/test-tika")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "TIKA_SERVER_URL", "http://tika:9998"):
            mock_container.tika_client.health_check.return_value = True
            resp = client.post("/settings/test-tika")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "TIKA_SERVER_URL", "http://tika:9998"):
            mock_container.tika_client.health_check.return_value = False
            resp = client.post("/settings/test-tika")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "TIKA_SERVER_URL", "http://tika:9998"):
            mock_container.tika_client.health_check.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-tika")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestPaperless:
    """POST /settings/test-paperless"""

    def test_not_configured_no_url(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "PAPERLESS_API_URL", ""), \
             patch.object(Config, "PAPERLESS_API_TOKEN", ""):
            resp = client.post("/settings/test-paperless")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_not_configured_no_token(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "PAPERLESS_API_URL", "http://paperless:8000"), \
             patch.object(Config, "PAPERLESS_API_TOKEN", ""):
            resp = client.post("/settings/test-paperless")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected_200(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "PAPERLESS_API_URL", "http://paperless:8000"), \
             patch.object(Config, "PAPERLESS_API_TOKEN", "tok-123"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_http.get.return_value = mock_resp
            resp = client.post("/settings/test-paperless")
        assert resp.status_code == 200
        assert b"Connected" in resp.data
        mock_http.get.assert_called_once_with(
            "http://paperless:8000/api/",
            headers={"Authorization": "Token tok-123"},
            timeout=10,
        )

    def test_non_200(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "PAPERLESS_API_URL", "http://paperless:8000"), \
             patch.object(Config, "PAPERLESS_API_TOKEN", "tok-123"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_http.get.return_value = mock_resp
            resp = client.post("/settings/test-paperless")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "PAPERLESS_API_URL", "http://paperless:8000"), \
             patch.object(Config, "PAPERLESS_API_TOKEN", "tok-123"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_http.get.side_effect = ConnectionError("refused")
            resp = client.post("/settings/test-paperless")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestAnythingLLM:
    """POST /settings/test-anythingllm"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "ANYTHINGLLM_API_URL", ""), \
             patch.object(Config, "ANYTHINGLLM_API_KEY", ""):
            resp = client.post("/settings/test-anythingllm")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        mock_instance = MagicMock()
        mock_instance.test_connection.return_value = True
        with patch.object(Config, "ANYTHINGLLM_API_URL", "http://anythingllm:3001"), \
             patch.object(Config, "ANYTHINGLLM_API_KEY", "key-123"), \
             patch("app.services.anythingllm_client.AnythingLLMClient",
                   return_value=mock_instance):
            resp = client.post("/settings/test-anythingllm")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        mock_instance = MagicMock()
        mock_instance.test_connection.return_value = False
        with patch.object(Config, "ANYTHINGLLM_API_URL", "http://anythingllm:3001"), \
             patch.object(Config, "ANYTHINGLLM_API_KEY", "key-123"), \
             patch("app.services.anythingllm_client.AnythingLLMClient",
                   return_value=mock_instance):
            resp = client.post("/settings/test-anythingllm")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "ANYTHINGLLM_API_URL", "http://anythingllm:3001"), \
             patch.object(Config, "ANYTHINGLLM_API_KEY", "key-123"), \
             patch("app.services.anythingllm_client.AnythingLLMClient",
                   side_effect=RuntimeError("import fail")):
            resp = client.post("/settings/test-anythingllm")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestPgvector:
    """POST /settings/test-pgvector"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DATABASE_URL", ""):
            resp = client.post("/settings/test-pgvector")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected_with_stats(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DATABASE_URL", "postgresql://localhost/db"):
            mock_container.pgvector_client.test_connection.return_value = True
            mock_container.pgvector_client.get_stats.return_value = {
                "total_chunks": 42, "total_sources": 3,
            }
            resp = client.post("/settings/test-pgvector")
        assert resp.status_code == 200
        assert b"Connected" in resp.data
        assert b"42 chunks" in resp.data
        assert b"3 source(s)" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DATABASE_URL", "postgresql://localhost/db"):
            mock_container.pgvector_client.test_connection.return_value = False
            resp = client.post("/settings/test-pgvector")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DATABASE_URL", "postgresql://localhost/db"):
            mock_container.pgvector_client.test_connection.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-pgvector")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestEmbedding:
    """POST /settings/test-embedding"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "EMBEDDING_URL", ""):
            resp = client.post("/settings/test-embedding")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "EMBEDDING_URL", "http://ollama:11434"):
            mock_container.embedding_client.test_connection.return_value = True
            resp = client.post("/settings/test-embedding")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "EMBEDDING_URL", "http://ollama:11434"):
            mock_container.embedding_client.test_connection.return_value = False
            resp = client.post("/settings/test-embedding")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "EMBEDDING_URL", "http://ollama:11434"):
            mock_container.embedding_client.test_connection.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-embedding")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestLLM:
    """POST /settings/test-llm"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "LLM_URL", ""), \
             patch.object(Config, "EMBEDDING_URL", ""):
            resp = client.post("/settings/test-llm")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_fallback_to_embedding_url(self, client, mock_container):
        """When LLM_URL is empty, falls back to EMBEDDING_URL."""
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "LLM_URL", ""), \
             patch.object(Config, "EMBEDDING_URL", "http://ollama:11434"):
            mock_container.llm_client.test_connection.return_value = True
            resp = client.post("/settings/test-llm")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "LLM_URL", "http://ollama:11434"):
            mock_container.llm_client.test_connection.return_value = True
            resp = client.post("/settings/test-llm")
        assert resp.status_code == 200
        assert b"Connected" in resp.data

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "LLM_URL", "http://ollama:11434"):
            mock_container.llm_client.test_connection.return_value = False
            resp = client.post("/settings/test-llm")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "LLM_URL", "http://ollama:11434"):
            mock_container.llm_client.test_connection.side_effect = RuntimeError("boom")
            resp = client.post("/settings/test-llm")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


class TestTestDoclingServe:
    """POST /settings/test-docling-serve"""

    def test_not_configured(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DOCLING_SERVE_URL", ""):
            resp = client.post("/settings/test-docling-serve")
        assert resp.status_code == 200
        assert b"Not Configured" in resp.data

    def test_connected(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DOCLING_SERVE_URL", "http://docling:4949"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_http.get.return_value = mock_resp
            resp = client.post("/settings/test-docling-serve")
        assert resp.status_code == 200
        assert b"Connected" in resp.data
        mock_http.get.assert_called_once_with("http://docling:4949/health", timeout=10)

    def test_failed(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DOCLING_SERVE_URL", "http://docling:4949"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_http.get.return_value = mock_resp
            resp = client.post("/settings/test-docling-serve")
        assert resp.status_code == 200
        assert b"Connection Failed" in resp.data

    def test_exception(self, client, mock_container):
        mock_container.settings.get.side_effect = lambda k, d=None: ""
        with patch.object(Config, "DOCLING_SERVE_URL", "http://docling:4949"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_http:
            mock_http.get.side_effect = ConnectionError("refused")
            resp = client.post("/settings/test-docling-serve")
        assert resp.status_code == 200
        assert b"Connection test failed" in resp.data


# ===================================================================
# Save handlers
# ===================================================================


class TestSaveFlareSolverrSettings:
    """POST /settings/flaresolverr"""

    def test_success(self, client, mock_container):
        resp = client.post("/settings/flaresolverr", data={
            "enabled": "on", "timeout": "60", "max_timeout": "120",
        })
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once_with(
            "flaresolverr", {"enabled": True, "timeout": 60, "max_timeout": 120},
        )

    def test_timeout_out_of_range_low(self, client):
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "0", "max_timeout": "120",
        })
        assert resp.status_code == 200
        assert b"Timeout must be between 1 and 600" in resp.data

    def test_timeout_out_of_range_high(self, client):
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "601", "max_timeout": "601",
        })
        assert resp.status_code == 200
        assert b"Timeout must be between 1 and 600" in resp.data

    def test_max_timeout_out_of_range(self, client):
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "60", "max_timeout": "0",
        })
        assert resp.status_code == 200
        assert b"Max timeout must be between 1 and 600" in resp.data

    def test_max_less_than_timeout(self, client):
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "120", "max_timeout": "60",
        })
        assert resp.status_code == 200
        assert b"Max timeout must be greater than or equal to timeout" in resp.data


class TestSaveScrapingSettings:
    """POST /settings/scraping"""

    def test_success(self, client, mock_container):
        resp = client.post("/settings/scraping", data={
            "use_flaresolverr_by_default": "on",
            "default_request_delay": "1.5",
            "default_timeout": "30",
            "default_retry_attempts": "5",
        })
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once_with(
            "scraping", {
                "use_flaresolverr_by_default": True,
                "default_request_delay": 1.5,
                "default_timeout": 30,
                "default_retry_attempts": 5,
            },
        )

    def test_invalid_delay_too_high(self, client):
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "61",
            "default_timeout": "60",
            "default_retry_attempts": "3",
        })
        assert resp.status_code == 200
        assert b"Request delay must be between 0 and 60" in resp.data

    def test_invalid_timeout(self, client):
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "2.0",
            "default_timeout": "0",
            "default_retry_attempts": "3",
        })
        assert resp.status_code == 200
        assert b"Timeout must be between 1 and 600" in resp.data

    def test_invalid_retries(self, client):
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "2.0",
            "default_timeout": "60",
            "default_retry_attempts": "11",
        })
        assert resp.status_code == 200
        assert b"Retry attempts must be between 0 and 10" in resp.data


class TestSaveRagflowSettings:
    """POST /settings/ragflow"""

    def test_success(self, client, mock_container):
        resp = client.post("/settings/ragflow", data={
            "default_embedding_model": "BAAI/bge-large-en",
            "default_chunk_method": "paper",
            "auto_upload": "on",
            "auto_create_dataset": "on",
            "wait_for_parsing": "on",
        })
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once_with(
            "ragflow", {
                "default_embedding_model": "BAAI/bge-large-en",
                "default_chunk_method": "paper",
                "auto_upload": True,
                "auto_create_dataset": True,
                "wait_for_parsing": True,
            },
        )

    def test_embedding_model_too_long(self, client):
        resp = client.post("/settings/ragflow", data={
            "default_embedding_model": "x" * 256,
            "default_chunk_method": "paper",
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data.lower()


class TestSaveBackendSettings:
    """POST /settings/backends"""

    def test_success(self, client, mock_container):
        resp = client.post("/settings/backends", data={
            "parser_backend": "docling",
            "archive_backend": "paperless",
            "rag_backend": "ragflow",
        })
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once_with(
            "pipeline", {
                "parser_backend": "docling",
                "archive_backend": "paperless",
                "rag_backend": "ragflow",
            },
        )
        mock_container.reset_services.assert_called_once()

    def test_empty_backends_allowed(self, client, mock_container):
        """Empty strings (use defaults) are valid."""
        resp = client.post("/settings/backends", data={
            "parser_backend": "",
            "archive_backend": "",
            "rag_backend": "",
        })
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()

    def test_invalid_parser_backend(self, client):
        resp = client.post("/settings/backends", data={
            "parser_backend": "invalid_parser",
            "archive_backend": "",
            "rag_backend": "",
        })
        assert resp.status_code == 200
        assert b"Invalid parser backend" in resp.data

    def test_invalid_archive_backend(self, client):
        resp = client.post("/settings/backends", data={
            "parser_backend": "",
            "archive_backend": "invalid_archive",
            "rag_backend": "",
        })
        assert resp.status_code == 200
        assert b"Invalid archive backend" in resp.data

    def test_invalid_rag_backend(self, client):
        resp = client.post("/settings/backends", data={
            "parser_backend": "",
            "archive_backend": "",
            "rag_backend": "invalid_rag",
        })
        assert resp.status_code == 200
        assert b"Invalid RAG backend" in resp.data


class TestSaveServiceSettings:
    """POST /settings/services"""

    def _valid_data(self, **overrides):
        """Return baseline valid form data, with optional overrides."""
        data = {
            "gotenberg_url": "", "gotenberg_timeout": "0",
            "tika_url": "", "tika_timeout": "0",
            "docling_serve_url": "", "docling_serve_timeout": "0",
            "paperless_url": "", "ragflow_url": "",
            "anythingllm_url": "", "embedding_url": "",
            "embedding_timeout": "0", "pgvector_url": "",
            "llm_url": "", "llm_timeout": "0",
        }
        data.update(overrides)
        return data

    def test_success_empty_urls(self, client, mock_container):
        resp = client.post("/settings/services", data=self._valid_data())
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once()
        mock_container.reset_services.assert_called_once()

    def test_success_with_urls(self, client, mock_container):
        with patch("app.web.blueprints.settings.api._validate_url_ssrf", return_value=None):
            resp = client.post("/settings/services", data=self._valid_data(
                gotenberg_url="http://gotenberg:3000",
                tika_url="http://tika:9998",
            ))
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()

    def test_url_too_long(self, client):
        resp = client.post("/settings/services", data=self._valid_data(
            gotenberg_url="http://example.com/" + "a" * 2048,
        ))
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data.lower()

    def test_invalid_scheme(self, client):
        resp = client.post("/settings/services", data=self._valid_data(
            gotenberg_url="ftp://gotenberg:3000",
        ))
        assert resp.status_code == 200
        assert b"must start with http:// or https://" in resp.data.lower()

    def test_pgvector_url_too_long(self, client):
        resp = client.post("/settings/services", data=self._valid_data(
            pgvector_url="postgresql://localhost/" + "a" * 2048,
        ))
        assert resp.status_code == 200
        assert b"pgvector URL exceeds maximum length" in resp.data

    def test_pgvector_url_invalid_scheme(self, client):
        resp = client.post("/settings/services", data=self._valid_data(
            pgvector_url="http://localhost/db",
        ))
        assert resp.status_code == 200
        assert b"must start with postgresql:// or postgres://" in resp.data.lower()

    def test_pgvector_url_valid_postgres_scheme(self, client, mock_container):
        """postgres:// prefix is also accepted."""
        resp = client.post("/settings/services", data=self._valid_data(
            pgvector_url="postgres://user:pass@localhost:5432/db",
        ))
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower()

    def test_invalid_timeout(self, client):
        resp = client.post("/settings/services", data=self._valid_data(
            gotenberg_timeout="700",
        ))
        assert resp.status_code == 200
        assert b"timeout must be 0 (use default) or between 1 and 600" in resp.data.lower()


class TestSavePipelineSettings:
    """POST /settings/pipeline"""

    def _valid_data(self, **overrides):
        data = {
            "metadata_merge_strategy": "",
            "filename_template": "",
            "tika_enrichment_enabled": "",
            "llm_enrichment_enabled": "",
            "contextual_enrichment_enabled": "",
            "llm_enrichment_max_tokens": "0",
            "contextual_enrichment_window": "0",
            "llm_backend": "",
            "llm_model": "",
            "embedding_backend": "",
            "embedding_model": "",
            "chunking_strategy": "",
            "chunk_max_tokens": "0",
            "chunk_overlap_tokens": "0",
        }
        data.update(overrides)
        return data

    def test_success(self, client, mock_container):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            metadata_merge_strategy="smart",
            filename_template="{{ title }}{{ extension }}",
        ))
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()
        mock_container.settings.update_section.assert_called_once()

    def test_invalid_merge_strategy(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            metadata_merge_strategy="invalid_strategy",
        ))
        assert resp.status_code == 200
        assert b"Invalid merge strategy" in resp.data

    def test_invalid_template_syntax(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            filename_template="{{ unclosed",
        ))
        assert resp.status_code == 200
        assert b"Invalid template syntax" in resp.data

    def test_template_too_long(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            filename_template="x" * 1025,
        ))
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data.lower()

    def test_llm_model_too_long(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            llm_model="x" * 256,
        ))
        assert resp.status_code == 200
        assert b"LLM model name exceeds maximum length" in resp.data

    def test_llm_max_tokens_out_of_range_low(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            llm_enrichment_max_tokens="500",
        ))
        assert resp.status_code == 200
        assert b"LLM max tokens must be 0" in resp.data

    def test_llm_max_tokens_out_of_range_high(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            llm_enrichment_max_tokens="200000",
        ))
        assert resp.status_code == 200
        assert b"LLM max tokens must be 0" in resp.data

    def test_contextual_window_out_of_range(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            contextual_enrichment_window="11",
        ))
        assert resp.status_code == 200
        assert b"Contextual enrichment window must be 0" in resp.data

    def test_invalid_llm_backend(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            llm_backend="invalid_backend",
        ))
        assert resp.status_code == 200
        assert b"Invalid LLM backend" in resp.data

    def test_chunk_max_tokens_out_of_range(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            chunk_max_tokens="9000",
        ))
        assert resp.status_code == 200
        assert b"Chunk max tokens must be 0" in resp.data

    def test_chunk_overlap_tokens_out_of_range(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            chunk_overlap_tokens="5000",
        ))
        assert resp.status_code == 200
        assert b"Chunk overlap tokens must be 0" in resp.data

    def test_embedding_model_too_long(self, client):
        resp = client.post("/settings/pipeline", data=self._valid_data(
            embedding_model="x" * 256,
        ))
        assert resp.status_code == 200
        assert b"Embedding model name exceeds maximum length" in resp.data

    def test_valid_llm_max_tokens(self, client, mock_container):
        """Boundary value: 1000 is valid."""
        resp = client.post("/settings/pipeline", data=self._valid_data(
            llm_enrichment_max_tokens="1000",
        ))
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()

    def test_valid_contextual_window(self, client, mock_container):
        """Boundary value: 10 is valid."""
        resp = client.post("/settings/pipeline", data=self._valid_data(
            contextual_enrichment_window="10",
        ))
        assert resp.status_code == 200
        assert b"saved successfully" in resp.data.lower()


class TestPreviewFilename:
    """POST /settings/pipeline/preview-filename"""

    def test_default_template(self, client):
        with patch.object(Config, "FILENAME_TEMPLATE",
                          "{{ date_prefix }}_{{ org }}_{{ title | slugify }}{{ extension }}"):
            resp = client.post("/settings/pipeline/preview-filename", data={"template": ""})
        assert resp.status_code == 200
        # Sample metadata uses "AEMO" as org and "Annual Report 2024" as title
        assert b"AEMO" in resp.data

    def test_custom_template(self, client):
        resp = client.post("/settings/pipeline/preview-filename", data={
            "template": "{{ org }}_{{ title | slugify }}{{ extension }}",
        })
        assert resp.status_code == 200
        assert b"AEMO" in resp.data
        assert b"annual-report-2024" in resp.data

    def test_error_in_template(self, client):
        with patch("app.utils.file_utils.generate_filename_from_template",
                   side_effect=ValueError("bad template")):
            resp = client.post("/settings/pipeline/preview-filename", data={
                "template": "{{ broken }}",
            })
        assert resp.status_code == 200
        assert b"Error" in resp.data
        assert b"bad template" in resp.data


# ===================================================================
# IOError handler
# ===================================================================


class TestIOErrorHandler:
    """IOError handler on the settings_api blueprint."""

    def test_ioerror_returns_alert(self, client, mock_container):
        """When settings cannot be written, the IOError handler fires."""
        mock_container.settings.update_section.side_effect = IOError("disk full")
        resp = client.post("/settings/flaresolverr", data={
            "enabled": "on", "timeout": "60", "max_timeout": "120",
        })
        assert resp.status_code == 200
        assert b"Failed to save settings" in resp.data
        assert b"not writable" in resp.data
