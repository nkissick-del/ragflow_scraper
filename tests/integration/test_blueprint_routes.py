"""Integration tests for Flask blueprint routes."""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from app.web import create_app
from app.web.job_queue import ScraperJob
from app.scrapers.models import ScraperResult
from app.scrapers.scraper_registry import ScraperRegistry


@pytest.fixture
def app():
    """Create test Flask app with mocked dependencies."""
    with patch("app.web.runtime.container") as mock_container, \
         patch("app.web.runtime.job_queue") as mock_queue:
        
        # Mock container services
        mock_container.settings_manager.return_value.get_settings.return_value = {
            "ragflow": {"api_url": "http://test", "api_key": "test"},
            "flaresolverr": {"api_url": "http://test"},
            "scraping": {"cloudflare_bypass": False}
        }
        mock_container.state_tracker.return_value.get_all_status.return_value = {}
        
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestScraperEndpoints:
    """Test scraper blueprint endpoints."""
    
    def test_index_dashboard(self, client):
        """Test index renders dashboard."""
        with patch.object(ScraperRegistry, "list_scrapers") as mock_list, \
             patch("app.web.blueprints.scrapers.load_scraper_configs") as mock_load:
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
        with patch("app.web.blueprints.settings.container") as mock_container:
            mock_ragflow = MagicMock()
            mock_ragflow.test_connection.return_value = True
            mock_ragflow.list_datasets.return_value = []
            mock_container.ragflow_client = mock_ragflow
            
            response = client.post("/settings/test-ragflow")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
    
    def test_test_flaresolverr_connection(self, client):
        """Test FlareSolverr connection test endpoint."""
        with patch("app.web.blueprints.settings.container") as mock_container, \
             patch("app.web.blueprints.settings.Config") as mock_config:

            mock_config.FLARESOLVERR_URL = "http://test:8191"

            mock_flaresolverr = MagicMock()
            mock_flaresolverr.test_connection.return_value = True
            mock_container.flaresolverr_client = mock_flaresolverr
            
            response = client.post("/settings/test-flaresolverr")
            assert response.status_code == 200
            assert b"connected" in response.data.lower()
    
    def test_save_flaresolverr_settings(self, client):
        """Test save FlareSolverr settings."""
        with patch("app.web.blueprints.settings.container") as mock_container:
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
        with patch("app.web.blueprints.settings.container") as mock_container:
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
        with patch("app.web.blueprints.settings.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings = mock_settings
            
            response = client.post("/settings/ragflow", data={
                "default_embedding_model": "test_model",
                "default_chunk_method": "paper"
            })
            assert response.status_code == 200
            mock_settings.update_section.assert_called_once()


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
