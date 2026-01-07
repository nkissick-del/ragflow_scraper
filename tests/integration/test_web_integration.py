"""Integration tests for web interface."""

import pytest
from unittest.mock import patch, MagicMock

from app.web import create_app


@pytest.fixture
def app():
    """Create test Flask app."""
    # Patch runtime dependencies before importing blueprints
    with patch("app.web.runtime.container"), \
         patch("app.web.runtime.job_queue"):
        app = create_app()
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestBlueprintRegistration:
    """Test that all blueprints are registered correctly."""
    
    def test_app_creation(self, app):
        """Test Flask app creates successfully."""
        assert app is not None
        assert app.config["TESTING"] is True
    
    def test_blueprints_registered(self, app):
        """Test all expected blueprints are registered."""
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        
        # Verify key blueprints are registered
        assert "scrapers" in blueprint_names
        assert "settings" in blueprint_names
        assert "metrics_logs" in blueprint_names
        assert "api_scrapers" in blueprint_names
    
    def test_root_renders(self, client):
        """Test root route renders."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry") as mock_registry:
            mock_registry.list_scrapers.return_value = []
            response = client.get("/", follow_redirects=False)
            assert response.status_code == 200
    
    def test_static_files_accessible(self, client):
        """Test static file serving works."""
        # Just verify the static folder is configured
        from app.web import create_app
        app = create_app()
        assert app.static_folder is not None
