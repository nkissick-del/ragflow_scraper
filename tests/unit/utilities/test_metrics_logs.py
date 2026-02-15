"""Tests for the metrics_logs blueprint (app/web/blueprints/metrics_logs.py).

Covers logs, log_stream, download_log, flaresolverr_metrics, and pipeline_metrics.
"""

import base64
import json

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
# logs
# ===================================================================


class TestLogs:
    """GET /logs"""

    def test_renders_page(self, client, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test log line\n")

        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs")

        assert resp.status_code == 200


# ===================================================================
# log_stream
# ===================================================================


class TestLogStream:
    """GET /logs/stream"""

    def test_with_json_logs(self, client, tmp_path):
        log_file = tmp_path / "app.log"
        entries = [
            json.dumps({"timestamp": "2024-01-01T00:00:00", "level": "INFO",
                         "logger": "app", "message": "Started"}),
            json.dumps({"timestamp": "2024-01-01T00:00:01", "level": "ERROR",
                         "logger": "app", "message": "Something failed"}),
        ]
        log_file.write_text("\n".join(entries) + "\n")

        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/stream")

        assert resp.status_code == 200
        assert b"Started" in resp.data
        assert b"Something failed" in resp.data
        assert b"log-error" in resp.data

    def test_with_plain_text_logs(self, client, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("INFO plain text log\nERROR something bad\n")

        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/stream")

        assert resp.status_code == 200
        assert b"plain text log" in resp.data
        assert b"log-error" in resp.data  # ERROR line should get error class

    def test_no_logs(self, client, tmp_path):
        # Empty directory - no log files
        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/stream")

        assert resp.status_code == 200
        assert resp.data == b""

    def test_read_exception(self, client, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test\n")

        with patch.object(Config, "LOG_DIR", tmp_path), \
             patch("builtins.open", side_effect=PermissionError("denied")):
            resp = client.get("/logs/stream")

        assert resp.status_code == 200
        assert b"Error reading logs" in resp.data


# ===================================================================
# download_log
# ===================================================================


class TestDownloadLog:
    """GET /logs/download/<filename>"""

    def test_success(self, client, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("log content here\n")

        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/download/app.log")

        assert resp.status_code == 200
        assert b"log content here" in resp.data
        assert resp.headers["Content-Disposition"] == 'attachment; filename="app.log"'

    def test_path_traversal_slash_blocked(self, client, tmp_path):
        """Flask resolves '../' in URLs before routing, returning 404."""
        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/download/../etc/passwd")
        # Flask's URL resolver handles this before the handler is reached
        assert resp.status_code == 404

    def test_path_traversal_dotdot_in_filename_blocked(self, client, tmp_path):
        """Filenames containing '..' are rejected by the handler."""
        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/download/..app.log")
        assert resp.status_code == 400
        assert b"Invalid filename" in resp.data

    def test_backslash_traversal_blocked(self, client, tmp_path):
        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/download/..\\etc\\passwd")

        assert resp.status_code == 400
        assert b"Invalid filename" in resp.data

    def test_not_found(self, client, tmp_path):
        with patch.object(Config, "LOG_DIR", tmp_path):
            resp = client.get("/logs/download/nonexistent.log")

        assert resp.status_code == 404


# ===================================================================
# flaresolverr_metrics
# ===================================================================


class TestFlaresolverrMetrics:
    """GET /metrics/flaresolverr"""

    def test_success(self, client, mock_container):
        mock_container.flaresolverr_client.get_metrics.return_value = {
            "success": 10, "failure": 2, "timeout": 1, "total": 13, "success_rate": 76.9,
        }

        resp = client.get("/metrics/flaresolverr")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] == 10
        assert data["total"] == 13

    def test_exception(self, client, mock_container):
        mock_container.flaresolverr_client.get_metrics.side_effect = RuntimeError("down")

        resp = client.get("/metrics/flaresolverr")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] == 0
        assert data["total"] == 0
        assert data["success_rate"] == 0.0


# ===================================================================
# pipeline_metrics
# ===================================================================


class TestPipelineMetrics:
    """GET /metrics/pipeline"""

    def test_with_scraper_data(self, client, mock_container):
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {
            "last_updated": "2024-01-01",
            "processed_count": 10,
            "failed_count": 2,
            "status": "completed",
        }
        mock_container.state_tracker.return_value = mock_state

        with patch("app.web.blueprints.metrics_logs.ScraperRegistry") as mock_reg:
            mock_reg.list_scrapers.return_value = [
                {"name": "aemo"},
                {"name": "cer"},
            ]
            resp = client.get("/metrics/pipeline")

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["scrapers"]) == 2
        assert data["totals"]["processed"] == 20  # 10 * 2
        assert data["totals"]["failed"] == 4       # 2 * 2

    def test_empty_scrapers(self, client):
        with patch("app.web.blueprints.metrics_logs.ScraperRegistry") as mock_reg:
            mock_reg.list_scrapers.return_value = []
            resp = client.get("/metrics/pipeline")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["scrapers"] == []
        assert data["totals"]["processed"] == 0
        assert data["totals"]["failed"] == 0
