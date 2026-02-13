"""Tests for the API scrapers blueprint (app/web/blueprints/api_scrapers.py).

Covers api_list_scrapers, api_run_scraper, and api_scraper_status.
"""

import base64

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.utils.errors import ScraperAlreadyRunningError
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
# api_list_scrapers
# ===================================================================


class TestApiListScrapers:
    """GET /api/scrapers"""

    def test_success(self, client):
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.list_scrapers.return_value = [
                {"name": "aemo", "display_name": "AEMO"},
                {"name": "cer", "display_name": "CER"},
            ]
            resp = client.get("/api/scrapers")

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["scrapers"]) == 2
        assert data["scrapers"][0]["name"] == "aemo"


# ===================================================================
# api_run_scraper
# ===================================================================


class TestApiRunScraper:
    """POST /api/scrapers/<name>/run"""

    def test_success(self, client, mock_job_queue):
        mock_scraper = MagicMock()

        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            resp = client.post("/api/scrapers/aemo/run",
                               json={"dry_run": False, "max_pages": 5})

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["success"] is True
        assert data["status"] == "queued"
        mock_job_queue.enqueue.assert_called_once()

    def test_invalid_name(self, client):
        resp = client.post("/api/scrapers/bad name!/run", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid scraper name" in data["error"]

    def test_not_found(self, client):
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = None
            mock_reg.get_scraper_class.return_value = None
            resp = client.post("/api/scrapers/nonexistent/run", json={})

        assert resp.status_code == 404

    def test_already_running(self, client, mock_job_queue):
        mock_scraper = MagicMock()
        mock_job_queue.enqueue.side_effect = ScraperAlreadyRunningError("already running")

        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            resp = client.post("/api/scrapers/aemo/run", json={})

        assert resp.status_code == 409
        data = resp.get_json()
        assert "already running" in data["error"]

    def test_max_pages_invalid_negative(self, client):
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = MagicMock()
            resp = client.post("/api/scrapers/aemo/run", json={"max_pages": -1})

        assert resp.status_code == 400
        data = resp.get_json()
        assert "max_pages must be >= 1" in data["error"]

    def test_max_pages_not_integer(self, client):
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = MagicMock()
            resp = client.post("/api/scrapers/aemo/run", json={"max_pages": "abc"})

        assert resp.status_code == 400
        data = resp.get_json()
        assert "max_pages must be an integer" in data["error"]

    def test_init_exception(self, client):
        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.side_effect = RuntimeError("init failed")
            # Non-dry-run uses get_scraper_class first, so test dry_run path
            resp = client.post("/api/scrapers/aemo/run", json={"dry_run": True})

        assert resp.status_code == 500
        data = resp.get_json()
        assert "Failed to initialize scraper" in data["error"]

    def test_enqueue_exception(self, client, mock_job_queue):
        mock_scraper = MagicMock()
        mock_job_queue.enqueue.side_effect = RuntimeError("queue broken")

        with patch("app.web.blueprints.api_scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            resp = client.post("/api/scrapers/aemo/run", json={})

        assert resp.status_code == 500
        data = resp.get_json()
        assert "Failed to queue scraper" in data["error"]


# ===================================================================
# api_scraper_status
# ===================================================================


class TestApiScraperStatus:
    """GET /api/scrapers/<name>/status"""

    def test_success_completed_with_result(self, client, mock_job_queue):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"documents": 5, "status": "completed"}

        mock_job = MagicMock()
        mock_job.status = "completed"
        mock_job.preview = False
        mock_job.dry_run = False
        mock_job.max_pages = None
        mock_job.started_at = "2024-01-01T00:00:00"
        mock_job.completed_at = "2024-01-01T00:05:00"
        mock_job.result = mock_result
        mock_job.error = None
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/api/scrapers/aemo/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["result"]["documents"] == 5

    def test_success_failed_with_error(self, client, mock_job_queue):
        mock_job = MagicMock()
        mock_job.status = "failed"
        mock_job.preview = False
        mock_job.dry_run = False
        mock_job.max_pages = None
        mock_job.started_at = "2024-01-01T00:00:00"
        mock_job.completed_at = "2024-01-01T00:01:00"
        mock_job.result = None
        mock_job.error = "Network timeout"
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/api/scrapers/aemo/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "failed"
        assert data["error"] == "Network timeout"

    def test_not_found(self, client, mock_job_queue):
        mock_job_queue.get.return_value = None
        resp = client.get("/api/scrapers/aemo/status")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "not_found"

    def test_invalid_name(self, client):
        resp = client.get("/api/scrapers/bad name!/status")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid scraper name" in data["error"]

    def test_job_has_no_to_dict(self, client, mock_job_queue):
        """When job.result has no to_dict, falls back to generic response."""
        mock_result = MagicMock(spec=[])  # spec=[] means no attributes
        # Ensure hasattr(mock_result, "to_dict") returns False
        del mock_result.to_dict

        mock_job = MagicMock()
        mock_job.status = "completed"
        mock_job.preview = False
        mock_job.dry_run = False
        mock_job.max_pages = None
        mock_job.started_at = "2024-01-01T00:00:00"
        mock_job.completed_at = "2024-01-01T00:05:00"
        mock_job.result = mock_result
        mock_job.error = None
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/api/scrapers/aemo/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "completed"

    def test_exception(self, client, mock_job_queue):
        mock_job_queue.get.side_effect = RuntimeError("db error")
        resp = client.get("/api/scrapers/aemo/status")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "Failed to retrieve job status" in data["error"]
