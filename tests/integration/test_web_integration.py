"""Integration tests for web interface."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


@pytest.fixture
def app():
    """Create test Flask app with mocked container/job_queue.

    Patches get_container() before app.web.runtime is imported so the
    module-level ``container = get_container()`` call uses the mock
    instead of hitting the real ServiceContainer (which requires
    /app/data/logs/ to exist).
    """
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    patches = [
        # Must come first — prevents runtime.py from creating a real container
        patch("app.container.get_container", return_value=mock_container),
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.settings.container", mock_container),
        patch("app.web.blueprints.metrics_logs.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["RATELIMIT_ENABLED"] = False
        yield app
    finally:
        for p in reversed(started):
            p.stop()


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
        """Test root route renders the scraper dashboard."""
        response = client.get("/")
        assert response.status_code == 200
    
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
