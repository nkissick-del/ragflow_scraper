"""Integration tests for web interface."""

import pytest
from pathlib import Path
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
        """Test root route redirects to scrapers."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/scrapers" in response.location
    
    def test_static_files_accessible(self, app, client):
        """Test static file serving works."""
        # Create a temporary test file in the static folder
        static_folder = Path(app.static_folder)
        test_file = static_folder / "test_file.txt"
        test_content = "test static content"
        
        try:
            # Write test file
            test_file.write_text(test_content, encoding="utf-8")
            
            # Request the file via the client
            response = client.get("/static/test_file.txt")
            
            # Verify successful response and correct content
            assert response.status_code == 200
            assert response.data.decode("utf-8") == test_content
        finally:
            # Clean up test file
            if test_file.exists():
                test_file.unlink()
