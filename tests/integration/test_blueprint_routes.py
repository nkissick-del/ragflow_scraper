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
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestScraperEndpoints:
    """Test scraper blueprint endpoints."""
    
    def test_index_redirect(self, client):
        """Test index redirects to scrapers page."""
        response = client.get("/")
        assert response.status_code == 302
        assert "/scrapers" in response.location
    
    def test_scrapers_page_loads(self, client):
        """Test scrapers page renders."""
        with patch.object(ScraperRegistry, "get_all_scrapers") as mock_get_all:
            mock_get_all.return_value = ["test_scraper"]
            response = client.get("/scrapers")
            assert response.status_code == 200
            assert b"Scrapers" in response.data
    
    def test_scraper_status_endpoint(self, client):
        """Test scraper status HTMX endpoint."""
        with patch("app.web.runtime.container") as mock_container:
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
        with patch("app.web.runtime.job_queue") as mock_queue:
            mock_queue.enqueue.return_value = None
            
            response = client.post("/scrapers/test_scraper/run")
            assert response.status_code == 200
            mock_queue.enqueue.assert_called_once()
    
    def test_cancel_scraper_endpoint(self, client):
        """Test cancel scraper endpoint."""
        with patch("app.web.runtime.job_queue") as mock_queue:
            mock_queue.cancel_scraper.return_value = True
            
            response = client.post("/scrapers/test_scraper/cancel")
            assert response.status_code == 200
            mock_queue.cancel_scraper.assert_called_once_with("test_scraper")
    
    def test_preview_scraper_endpoint(self, client):
        """Test scraper preview endpoint initiates dry run."""
        with patch("app.web.runtime.job_queue") as mock_queue:
            mock_queue.enqueue.return_value = None
            
            response = client.post("/scrapers/test_scraper/preview")
            assert response.status_code == 200
            mock_queue.enqueue.assert_called_once()
    
    def test_scraper_card_endpoint(self, client):
        """Test scraper card HTMX endpoint."""
        with patch.object(ScraperRegistry, "get_scraper_class") as mock_get_class:
            mock_class = MagicMock()
            mock_class.NAME = "Test Scraper"
            mock_class.DESCRIPTION = "Test description"
            mock_get_class.return_value = mock_class
            
            response = client.get("/scrapers/test_scraper/card")
            assert response.status_code == 200
            assert b"Test Scraper" in response.data
    
    def test_save_ragflow_settings_endpoint(self, client):
        """Test save RAGFlow settings endpoint."""
        with patch("app.web.runtime.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings_manager.return_value = mock_settings
            
            response = client.post("/scrapers/ragflow/save", data={
                "ragflow_api_url": "http://test",
                "ragflow_api_key": "test_key",
                "ragflow_dataset_id": "test_dataset"
            })
            assert response.status_code == 200
            mock_settings.update_settings.assert_called_once()
    
    def test_toggle_cloudflare_bypass(self, client):
        """Test toggle cloudflare bypass endpoint."""
        with patch("app.web.runtime.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings_manager.return_value = mock_settings
            
            response = client.post("/scrapers/cloudflare/toggle")
            assert response.status_code == 200
            mock_settings.update_settings.assert_called_once()


class TestSettingsEndpoints:
    """Test settings blueprint endpoints."""
    
    def test_settings_page_loads(self, client):
        """Test settings page renders."""
        response = client.get("/settings")
        assert response.status_code == 200
        assert b"Settings" in response.data
    
    def test_test_ragflow_connection(self, client):
        """Test RAGFlow connection test endpoint."""
        with patch("app.web.runtime.container") as mock_container:
            mock_ragflow = MagicMock()
            mock_ragflow.test_connection.return_value = True
            mock_container.ragflow_client.return_value = mock_ragflow
            
            response = client.post("/settings/test/ragflow")
            assert response.status_code == 200
            assert b"success" in response.data.lower()
    
    def test_test_flaresolverr_connection(self, client):
        """Test FlareSolverr connection test endpoint."""
        with patch("app.web.runtime.container") as mock_container:
            mock_flaresolverr = MagicMock()
            mock_flaresolverr.test_connection.return_value = True
            mock_container.flaresolverr_client.return_value = mock_flaresolverr
            
            response = client.post("/settings/test/flaresolverr")
            assert response.status_code == 200
            assert b"success" in response.data.lower()
    
    def test_save_flaresolverr_settings(self, client):
        """Test save FlareSolverr settings."""
        with patch("app.web.runtime.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings_manager.return_value = mock_settings
            
            response = client.post("/settings/flaresolverr/save", data={
                "flaresolverr_api_url": "http://test:8191"
            })
            assert response.status_code == 200
            mock_settings.update_settings.assert_called_once()
    
    def test_save_scraping_settings(self, client):
        """Test save scraping settings."""
        with patch("app.web.runtime.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings_manager.return_value = mock_settings
            
            response = client.post("/settings/scraping/save", data={
                "cloudflare_bypass": "on",
                "max_retries": "3"
            })
            assert response.status_code == 200
            mock_settings.update_settings.assert_called_once()
    
    def test_save_ragflow_settings(self, client):
        """Test save RAGFlow settings."""
        with patch("app.web.runtime.container") as mock_container:
            mock_settings = MagicMock()
            mock_container.settings_manager.return_value = mock_settings
            
            response = client.post("/settings/ragflow/save", data={
                "ragflow_api_url": "http://test",
                "ragflow_api_key": "test_key"
            })
            assert response.status_code == 200
            mock_settings.update_settings.assert_called_once()


class TestMetricsLogsEndpoints:
    """Test metrics and logs blueprint endpoints."""
    
    def test_logs_page_loads(self, client):
        """Test logs page renders."""
        response = client.get("/logs")
        assert response.status_code == 200
        assert b"Logs" in response.data or b"logs" in response.data
    
    def test_log_stream_endpoint(self, client):
        """Test log stream SSE endpoint."""
        response = client.get("/logs/stream")
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
    
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
        response = client.get("/metrics/pipeline")
        assert response.status_code == 200


class TestAPIEndpoints:
    """Test API blueprint endpoints."""
    
    def test_api_list_scrapers(self, client):
        """Test API list scrapers endpoint."""
        with patch.object(ScraperRegistry, "get_all_scrapers") as mock_get_all:
            mock_get_all.return_value = ["test_scraper"]
            
            response = client.get("/api/scrapers")
            assert response.status_code == 200
            assert response.json == ["test_scraper"]
