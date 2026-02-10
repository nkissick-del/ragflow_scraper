"""Integration tests for Flask blueprint routes."""

import base64

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app
from app.scrapers.scraper_registry import ScraperRegistry


def _make_mock_settings():
    """Create a properly configured mock SettingsManager."""
    mock = MagicMock()
    mock.get_all.return_value = {
        "ragflow": {
            "default_dataset_id": "",
            "auto_upload": False,
            "auto_create_dataset": True,
            "default_embedding_model": "",
            "default_chunk_method": "paper",
            "wait_for_parsing": True,
            "parser_config": {"chunk_token_num": 128, "layout_recognize": "DeepDOC"},
        },
        "flaresolverr": {"enabled": False, "timeout": 60, "max_timeout": 120},
        "scraping": {
            "use_flaresolverr_by_default": False,
            "default_request_delay": 2.0,
            "default_timeout": 60,
            "default_retry_attempts": 3,
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
        },
        "application": {"name": "PDF Scraper", "version": "0.1.0"},
        "scrapers": {},
        "scheduler": {"enabled": False, "run_on_startup": False},
    }
    mock.flaresolverr_enabled = False
    # _get_effective_* helpers call settings.get("services.xxx", ""); return the default
    _all_settings = mock.get_all.return_value
    def _mock_get(key, default=None):
        keys = key.split(".")
        value = _all_settings
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
    mock.ragflow_client.test_connection.return_value = False
    mock.ragflow_client.list_embedding_models.return_value = []
    mock.ragflow_client.list_chunk_methods.return_value = []
    mock.flaresolverr_client.test_connection.return_value = False
    mock.gotenberg_client.health_check.return_value = False
    mock.tika_client.health_check.return_value = False
    mock.state_tracker.return_value.get_all_status.return_value = {}
    mock.state_tracker.return_value.get_status.return_value = {
        "scraper": "test", "status": "idle", "is_running": False
    }
    mock.state_tracker.return_value.get_last_run_info.return_value = {}
    return mock


# Auth header for basic auth (testuser:testpass from .env.test)
_AUTH_HEADER = {
    "Authorization": "Basic " + base64.b64encode(b"testuser:testpass").decode()
}


@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies.

    Patches the container and http_requests at each blueprint's module level
    so that route handlers see mocks instead of real services.
    """
    mock_container = _make_mock_container()

    patches = [
        # Ensure auth credentials are configured for tests
        patch.object(Config, "BASIC_AUTH_ENABLED", True),
        patch.object(Config, "BASIC_AUTH_USERNAME", "testuser"),
        patch.object(Config, "BASIC_AUTH_PASSWORD", "testpass"),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
        # Patch container in every module that imports it from runtime
        patch("app.web.blueprints.settings.ui.container", mock_container),
        patch("app.web.blueprints.settings.api.container", mock_container),
        patch("app.web.blueprints.settings.helpers.container", mock_container),
        patch("app.web.blueprints.settings.reconciliation.container", mock_container),
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.metrics_logs.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        # Patch http_requests in settings to prevent real HTTP calls
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
    """Create test client with auth headers."""

    _HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})

    class AuthClient:
        """Thin wrapper that injects Basic Auth on every request."""

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


class TestScraperEndpoints:
    """Test scraper blueprint endpoints."""
    
    def test_index_dashboard(self, client):
        """Test index renders dashboard."""
        with patch.object(ScraperRegistry, "list_scrapers") as mock_list, \
             patch("app.web.blueprints.scrapers.load_scraper_configs"):
            mock_list.return_value = [{"name": "test_scraper"}]

            response = client.get("/")
            assert response.status_code == 200
            assert b"Dashboard" in response.data
    
    def test_scrapers_page_loads(self, client):
        """Test scrapers page renders."""
        with patch.object(ScraperRegistry, "get_all_scrapers") as mock_get_all:
            mock_get_all.return_value = ["test_scraper"]
            response = client.get("/scrapers")
            assert response.status_code == 200
            assert b"Scrapers" in response.data
    
    def test_scraper_status_endpoint(self, client):
        """Test scraper status HTMX endpoint."""
        with patch("app.web.runtime.container") as mock_container, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class, \
             patch("app.web.blueprints.scrapers.get_scraper_status") as mock_status:
            mock_get_class.return_value = MagicMock()
            mock_status.return_value = "idle"
            mock_state_tracker = MagicMock()
            mock_state_tracker.get_status.return_value = {
                "scraper": "test_scraper",
                "status": "idle",
                "is_running": False
            }
            mock_container.state_tracker.return_value = mock_state_tracker
            
            response = client.get("/scrapers/test_scraper/status")
            assert response.status_code == 200
            assert b"idle" in response.data
    
    def test_run_scraper_endpoint(self, client):
        """Test run scraper endpoint enqueues job."""
        with patch("app.web.blueprints.scrapers.job_queue") as mock_queue, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get_scraper, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class:
            mock_get_scraper.return_value = MagicMock()
            mock_get_class.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
            mock_queue.enqueue.return_value = None
            mock_queue.status.return_value = "queued"
            
            response = client.post("/scrapers/test_scraper/run")
            assert response.status_code == 200
            mock_queue.enqueue.assert_called_once()
    
    def test_cancel_scraper_endpoint(self, client):
        """Test cancel scraper endpoint."""
        with patch("app.web.blueprints.scrapers.job_queue") as mock_queue:
            mock_queue.cancel.return_value = True
            
            response = client.post("/scrapers/test_scraper/cancel")
            assert response.status_code == 200
            mock_queue.cancel.assert_called_once_with("test_scraper")
    
    def test_preview_scraper_endpoint(self, client):
        """Test scraper preview endpoint initiates dry run."""
        with patch("app.web.blueprints.scrapers.job_queue") as mock_queue, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper") as mock_get_scraper, \
             patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_get_class:
            mock_get_scraper.return_value = MagicMock()
            mock_get_class.return_value = MagicMock(get_metadata=MagicMock(return_value={}))
            mock_queue.enqueue.return_value = None
            mock_queue.status.return_value = "queued"
            
            response = client.post("/scrapers/test_scraper/preview")
            assert response.status_code == 200
            mock_queue.enqueue.assert_called_once()
    
    def test_scraper_card_endpoint(self, client):
        """Test scraper card HTMX endpoint."""
        with patch.object(ScraperRegistry, "get_scraper_class") as mock_get_class, \
             patch("app.web.blueprints.scrapers.container") as mock_container:
            mock_class = MagicMock()
            mock_class.get_metadata.return_value = {
                "name": "test_scraper",
                "description": "Test description",
                "status": "idle",
                "state": None
            }
            mock_get_class.return_value = mock_class
            mock_state = MagicMock()
            mock_state.get_last_run_info.return_value = {}
            mock_container.state_tracker.return_value = mock_state
            
            response = client.get("/scrapers/test_scraper/card")
            assert response.status_code == 200
            assert b"test_scraper" in response.data or b"Test description" in response.data
    
    def test_save_ragflow_settings_endpoint(self, client):
        """Test save RAGFlow settings endpoint."""
        with patch("app.web.blueprints.scrapers.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings = mock_settings
            
            response = client.post("/scrapers/aemc/ragflow", data={
                "chunk_method": "paper",
                "embedding_model": "test_model"
            })
            assert response.status_code == 200
            assert b"saved" in response.data.lower()
    
    def test_toggle_cloudflare_bypass(self, client):
        """Test toggle cloudflare bypass endpoint."""
        with patch("app.web.blueprints.scrapers.container") as mock_container:
            mock_settings = MagicMock()
            mock_settings.flaresolverr_enabled = True
            mock_container.settings = mock_settings
            
            with patch("app.web.blueprints.scrapers.Config") as mock_config:
                mock_config.FLARESOLVERR_URL = "http://flaresolverr:8191"
                
                response = client.post("/scrapers/aemc/cloudflare", data={
                    "enabled": "on"
                })
                assert response.status_code == 200
                assert b"enabled" in response.data.lower()


class TestSettingsEndpoints:
    """Test settings blueprint endpoints."""
    
    def test_settings_page_loads(self, client):
        """Test settings page renders."""
        response = client.get("/settings")
        assert response.status_code == 200
        assert b"Settings" in response.data
    
    def test_test_ragflow_connection(self, client):
        """Test RAGFlow connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container:
            mock_ragflow = MagicMock()
            mock_ragflow.test_connection.return_value = True
            mock_ragflow.list_datasets.return_value = []
            mock_container.ragflow_client = mock_ragflow

            response = client.post("/settings/test-ragflow")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
    
    def test_test_flaresolverr_connection(self, client):
        """Test FlareSolverr connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "FLARESOLVERR_URL", "http://test:8191"):

            mock_flaresolverr = MagicMock()
            mock_flaresolverr.test_connection.return_value = True
            mock_container.flaresolverr_client = mock_flaresolverr

            response = client.post("/settings/test-flaresolverr")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
    
    def test_save_flaresolverr_settings(self, client):
        """Test save FlareSolverr settings."""
        with patch("app.web.blueprints.settings.api.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings = mock_settings

            response = client.post("/settings/flaresolverr", data={
                "enabled": "on",
                "timeout": "60"
            })
            assert response.status_code == 200
            mock_settings.update_section.assert_called_once()
    
    def test_save_scraping_settings(self, client):
        """Test save scraping settings."""
        with patch("app.web.blueprints.settings.api.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings = mock_settings

            response = client.post("/settings/scraping", data={
                "use_flaresolverr_by_default": "on",
                "default_request_delay": "2.0"
            })
            assert response.status_code == 200
            mock_settings.update_section.assert_called_once()
    
    def test_save_ragflow_settings(self, client):
        """Test save RAGFlow settings."""
        with patch("app.web.blueprints.settings.api.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings = mock_settings

            response = client.post("/settings/ragflow", data={
                "default_embedding_model": "test_model",
                "default_chunk_method": "paper"
            })
            assert response.status_code == 200
            mock_settings.update_section.assert_called_once()

    def test_test_gotenberg_connection(self, client):
        """Test Gotenberg connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "GOTENBERG_URL", "http://test:3000"):
            mock_container.settings.get.return_value = ""
            mock_gotenberg = MagicMock()
            mock_gotenberg.health_check.return_value = True
            mock_container.gotenberg_client = mock_gotenberg

            response = client.post("/settings/test-gotenberg")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()

    def test_test_tika_connection(self, client):
        """Test Tika connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "TIKA_SERVER_URL", "http://test:9998"):
            mock_container.settings.get.return_value = ""
            mock_tika = MagicMock()
            mock_tika.health_check.return_value = True
            mock_container.tika_client = mock_tika

            response = client.post("/settings/test-tika")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()

    def test_test_paperless_connection(self, client):
        """Test Paperless connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "PAPERLESS_API_URL", "http://test:8000"), \
             patch.object(Config, "PAPERLESS_API_TOKEN", "test-token"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_requests:
            # _get_effective_url reads from settings; return empty to fall through to Config
            mock_container.settings.get.return_value = ""

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_requests.get.return_value = mock_resp

            response = client.post("/settings/test-paperless")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
            mock_requests.get.assert_called_once_with(
                "http://test:8000/api/",
                headers={"Authorization": "Token test-token"},
                timeout=10,
            )

    def test_test_anythingllm_connection(self, client):
        """Test AnythingLLM connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "ANYTHINGLLM_API_URL", "http://test:3001"), \
             patch.object(Config, "ANYTHINGLLM_API_KEY", "test-key"):
            mock_container.settings.get.return_value = ""

            mock_instance = MagicMock()
            mock_instance.test_connection.return_value = True

            with patch("app.services.anythingllm_client.AnythingLLMClient", return_value=mock_instance):
                response = client.post("/settings/test-anythingllm")
                assert response.status_code == 200
                assert b"connected" in response.data.lower()

    def test_test_docling_serve_connection(self, client):
        """Test Docling-serve connection test endpoint."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "DOCLING_SERVE_URL", "http://test:4949"), \
             patch("app.web.blueprints.settings.api.http_requests") as mock_requests:
            # _get_effective_url reads from settings; return empty to fall through to Config
            mock_container.settings.get.return_value = ""

            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_requests.get.return_value = mock_resp

            response = client.post("/settings/test-docling-serve")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
            mock_requests.get.assert_called_once_with(
                "http://test:4949/health",
                timeout=10,
            )

    def test_save_pipeline_settings(self, client):
        """Test save pipeline settings."""
        with patch("app.web.blueprints.settings.api.container") as mock_container, \
             patch.object(Config, "VALID_METADATA_MERGE_STRATEGIES", ("smart", "parser_wins", "scraper_wins")):
            mock_settings = MagicMock()
            mock_container.settings = mock_settings

            response = client.post("/settings/pipeline", data={
                "metadata_merge_strategy": "smart",
                "filename_template": "{{ title }}{{ extension }}",
            })
            assert response.status_code == 200
            assert b"saved" in response.data.lower()
            mock_settings.update_section.assert_called_once_with("pipeline", {
                "metadata_merge_strategy": "smart",
                "filename_template": "{{ title }}{{ extension }}",
                "tika_enrichment_enabled": "false",
                "embedding_backend": "",
                "embedding_model": "",
                "chunking_strategy": "",
                "chunk_max_tokens": 0,
                "chunk_overlap_tokens": 0,
            })

    def test_preview_filename(self, client):
        """Test filename preview endpoint."""
        with patch.object(Config, "FILENAME_TEMPLATE", "{{ title }}{{ extension }}"):

            response = client.post("/settings/pipeline/preview-filename", data={
                "template": "{{ org }}_{{ title | slugify }}{{ extension }}",
            })
            assert response.status_code == 200
            assert b"AEMO" in response.data
            assert b"annual-report-2024" in response.data


class TestMetricsLogsEndpoints:
    """Test metrics and logs blueprint endpoints."""
    
    def test_logs_page_loads(self, client):
        """Test logs page renders."""
        response = client.get("/logs")
        assert response.status_code == 200
        assert b"Logs" in response.data or b"logs" in response.data
    
    def test_log_stream_endpoint(self, client):
        """Test log stream endpoint."""
        response = client.get("/logs/stream")
        assert response.status_code == 200
        # The endpoint returns HTML content (log entries)
        assert response.content_type == "text/html; charset=utf-8"
    
    def test_flaresolverr_metrics_endpoint(self, client):
        """Test FlareSolverr metrics endpoint."""
        with patch("app.web.runtime.container") as mock_container:
            mock_flaresolverr = MagicMock()
            mock_flaresolverr.get_metrics.return_value = {"requests": 0}
            mock_container.flaresolverr_client.return_value = mock_flaresolverr
            
            response = client.get("/metrics/flaresolverr")
            assert response.status_code == 200
    
    def test_pipeline_metrics_endpoint(self, client):
        """Test pipeline metrics endpoint."""
        with patch("app.web.blueprints.metrics_logs.ScraperRegistry.list_scrapers") as mock_list:
            mock_list.return_value = []
            response = client.get("/metrics/pipeline")
            assert response.status_code == 200


class TestAPIEndpoints:
    """Test API blueprint endpoints."""
    
    def test_api_list_scrapers(self, client):
        """Test API list scrapers endpoint."""
        response = client.get("/api/scrapers")
        assert response.status_code == 200
        data = response.get_json()
        assert "scrapers" in data
        assert isinstance(data["scrapers"], list)
