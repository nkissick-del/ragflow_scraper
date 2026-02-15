"""Tests for the scrapers blueprint (app/web/blueprints/scrapers.py).

Covers scraper_status, run_scraper, cancel_scraper, preview_scraper,
preview_status, scraper_card, save_scraper_ragflow_settings,
and toggle_scraper_cloudflare.
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
# scraper_status
# ===================================================================


class TestScraperStatus:
    """GET /scrapers/<name>/status"""

    def test_valid_name(self, client, mock_job_queue):
        mock_job_queue.status.return_value = "idle"
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "aemo"}

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = mock_class
            resp = client.get("/scrapers/aemo/status")

        assert resp.status_code == 200

    def test_invalid_name(self, client):
        resp = client.get("/scrapers/bad name!/status")
        assert resp.status_code == 200
        assert b"Invalid Name" in resp.data

    def test_unknown_scraper(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = None
            resp = client.get("/scrapers/nonexistent/status")

        assert resp.status_code == 200
        assert b"Unknown" in resp.data


# ===================================================================
# run_scraper
# ===================================================================


class TestRunScraper:
    """POST /scrapers/<name>/run"""

    def test_success(self, client, mock_container, mock_job_queue):
        mock_scraper = MagicMock()
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "aemo", "display_name": "AEMO"}
        mock_job_queue.status.return_value = "queued"

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            mock_reg.get_scraper_class.return_value = mock_class
            resp = client.post("/scrapers/aemo/run", data={})

        assert resp.status_code == 200
        mock_job_queue.enqueue.assert_called_once()

    def test_invalid_name(self, client):
        resp = client.post("/scrapers/bad name!/run", data={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid scraper name" in data["error"]

    def test_not_found(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = None
            mock_reg.get_scraper_class.return_value = None
            resp = client.post("/scrapers/nonexistent/run", data={})

        assert resp.status_code == 404

    def test_max_pages_invalid(self, client):
        resp = client.post("/scrapers/aemo/run", data={"max_pages": "0"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "max_pages must be positive" in data["error"]

    def test_already_running_value_error(self, client, mock_job_queue):
        mock_scraper = MagicMock()
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "aemo", "display_name": "AEMO"}
        mock_job_queue.enqueue.side_effect = ValueError("already running")

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            mock_reg.get_scraper_class.return_value = mock_class
            resp = client.post("/scrapers/aemo/run", data={})

        # Returns a scraper-card template (the ValueError handler renders the card)
        assert resp.status_code == 200
        # The card is rendered with scraper metadata
        assert b"aemo" in resp.data

    def test_dry_run_defaults_max_pages_to_1(self, client, mock_container, mock_job_queue):
        mock_scraper = MagicMock()
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "aemo"}
        mock_job_queue.status.return_value = "queued"

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            mock_reg.get_scraper_class.return_value = mock_class
            resp = client.post("/scrapers/aemo/run", data={"dry_run": "true"})

        assert resp.status_code == 200
        # get_scraper should be called with max_pages=1 for dry_run
        call_args = mock_reg.get_scraper.call_args
        assert call_args.kwargs.get("max_pages") == 1 or call_args[1].get("max_pages") == 1


# ===================================================================
# cancel_scraper
# ===================================================================


class TestCancelScraper:
    """POST /scrapers/<name>/cancel"""

    def test_success(self, client, mock_job_queue):
        mock_job_queue.cancel.return_value = True
        resp = client.post("/scrapers/aemo/cancel")
        assert resp.status_code == 200
        assert b"Cancelling" in resp.data

    def test_not_running(self, client, mock_job_queue):
        mock_job_queue.cancel.return_value = False
        resp = client.post("/scrapers/aemo/cancel")
        assert resp.status_code == 200
        assert b"Not Running" in resp.data


# ===================================================================
# preview_scraper
# ===================================================================


class TestPreviewScraper:
    """POST /scrapers/<name>/preview"""

    def test_success(self, client, mock_job_queue):
        mock_scraper = MagicMock()

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            resp = client.post("/scrapers/aemo/preview", data={})

        assert resp.status_code == 200
        mock_job_queue.enqueue.assert_called_once()

    def test_invalid_name(self, client):
        resp = client.post("/scrapers/bad name!/preview", data={})
        assert resp.status_code == 400

    def test_max_pages_invalid(self, client):
        resp = client.post("/scrapers/aemo/preview", data={"max_pages": "0"})
        assert resp.status_code == 400

    def test_not_found(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = None
            resp = client.post("/scrapers/nonexistent/preview", data={})

        assert resp.status_code == 404

    def test_already_running(self, client, mock_job_queue):
        mock_scraper = MagicMock()
        mock_job_queue.enqueue.side_effect = ValueError("already running")

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper.return_value = mock_scraper
            resp = client.post("/scrapers/aemo/preview", data={})

        assert resp.status_code == 200
        assert b"currently running" in resp.data


# ===================================================================
# preview_status
# ===================================================================


class TestPreviewStatus:
    """GET /scrapers/<name>/preview/status"""

    def test_no_job(self, client, mock_job_queue):
        mock_job_queue.get.return_value = None
        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        assert b"No preview running" in resp.data

    def test_non_preview_job(self, client, mock_job_queue):
        mock_job = MagicMock()
        mock_job.preview = False
        mock_job_queue.get.return_value = mock_job
        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        assert b"No preview running" in resp.data

    def test_error(self, client, mock_job_queue):
        mock_job = MagicMock()
        mock_job.preview = True
        mock_job.error = "Something went wrong"
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        assert b"Preview failed" in resp.data
        assert b"Something went wrong" in resp.data
        mock_job_queue.drop.assert_called_once_with("aemo")

    def test_finished_without_result(self, client, mock_job_queue):
        mock_job = MagicMock()
        mock_job.preview = True
        mock_job.error = None
        mock_job.is_finished = True
        mock_job.result = None
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        assert b"Preview finished without a result" in resp.data

    def test_finished_with_result(self, client, mock_job_queue):
        mock_result = MagicMock()
        mock_result.documents = [{"url": "http://example.com/test.pdf"}]
        mock_job = MagicMock()
        mock_job.preview = True
        mock_job.error = None
        mock_job.is_finished = True
        mock_job.result = mock_result
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        mock_job_queue.drop.assert_called_once_with("aemo")

    def test_still_running(self, client, mock_job_queue):
        mock_job = MagicMock()
        mock_job.preview = True
        mock_job.error = None
        mock_job.is_finished = False
        mock_job_queue.get.return_value = mock_job

        resp = client.get("/scrapers/aemo/preview/status")
        assert resp.status_code == 200
        # Still loading - should not drop
        mock_job_queue.drop.assert_not_called()


# ===================================================================
# scraper_card
# ===================================================================


class TestScraperCard:
    """GET /scrapers/<name>/card"""

    def test_found(self, client, mock_container, mock_job_queue):
        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "aemo", "display_name": "AEMO"}
        mock_job_queue.status.return_value = "idle"

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg, \
             patch("app.web.blueprints.scrapers.build_scraper_metadata") as mock_build:
            mock_reg.get_scraper_class.return_value = mock_class
            mock_build.return_value = {"name": "aemo", "display_name": "AEMO", "status": "idle"}
            resp = client.get("/scrapers/aemo/card")

        assert resp.status_code == 200

    def test_not_found(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = None
            resp = client.get("/scrapers/nonexistent/card")

        assert resp.status_code == 404


# ===================================================================
# save_scraper_ragflow_settings
# ===================================================================


class TestSaveScraperRagflowSettings:
    """POST /scrapers/<name>/ragflow"""

    def test_success(self, client, mock_container):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/ragflow", data={
                "chunk_method": "paper",
            })

        assert resp.status_code == 200
        assert b"Saved" in resp.data
        mock_container.settings.set_scraper_ragflow_settings.assert_called_once()

    def test_invalid_name(self, client):
        resp = client.post("/scrapers/bad name!/ragflow", data={})
        assert resp.status_code == 400
        assert b"Invalid scraper name" in resp.data

    def test_not_found(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = None
            resp = client.post("/scrapers/nonexistent/ragflow", data={})

        assert resp.status_code == 404

    def test_invalid_chunk_method(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/ragflow", data={
                "chunk_method": "invalid_method",
            })

        assert resp.status_code == 400
        assert b"Invalid chunk method" in resp.data

    def test_embedding_model_too_long(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/ragflow", data={
                "embedding_model": "x" * 256,
            })

        assert resp.status_code == 400
        assert b"exceeds maximum length" in resp.data


# ===================================================================
# toggle_scraper_cloudflare
# ===================================================================


class TestToggleScraperCloudflare:
    """POST /scrapers/<name>/cloudflare"""

    def test_success(self, client, mock_container):
        mock_container.settings.flaresolverr_enabled = True

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg, \
             patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191"):
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/cloudflare", data={"enabled": "on"})

        assert resp.status_code == 200
        assert b"Enabled" in resp.data

    def test_invalid_name(self, client):
        resp = client.post("/scrapers/bad name!/cloudflare", data={})
        assert resp.status_code == 400
        assert b"Invalid name" in resp.data

    def test_not_found(self, client):
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg:
            mock_reg.get_scraper_class.return_value = None
            resp = client.post("/scrapers/nonexistent/cloudflare", data={})

        assert resp.status_code == 404
        assert b"Not found" in resp.data

    def test_flaresolverr_not_configured(self, client, mock_container):
        mock_container.settings.flaresolverr_enabled = True

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg, \
             patch.object(Config, "FLARESOLVERR_URL", ""):
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/cloudflare", data={"enabled": "on"})

        assert resp.status_code == 200
        assert b"FlareSolverr URL not configured" in resp.data

    def test_flaresolverr_not_enabled(self, client, mock_container):
        mock_container.settings.flaresolverr_enabled = False

        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_reg, \
             patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191"):
            mock_reg.get_scraper_class.return_value = MagicMock()
            resp = client.post("/scrapers/aemo/cloudflare", data={"enabled": "on"})

        assert resp.status_code == 200
        assert b"Enable FlareSolverr in Settings first" in resp.data
