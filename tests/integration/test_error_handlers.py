"""Integration tests for custom error handlers."""

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


@pytest.fixture
def app():
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        application = create_app()
        application.config["TESTING"] = True
        application.config["WTF_CSRF_ENABLED"] = False
        application.config["RATELIMIT_ENABLED"] = False
        yield application
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestErrorHandlers:

    def test_404_returns_html(self, client):
        """404 for browser request returns HTML error page."""
        resp = client.get("/nonexistent-page")
        assert resp.status_code == 404
        assert b"404 Not Found" in resp.data
        assert b"text/html" in resp.content_type.encode()

    def test_404_returns_json_for_api(self, client):
        """404 for JSON accept header returns JSON."""
        resp = client.get(
            "/nonexistent-page",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "Not found"

    def test_csrf_error_returns_400(self, app):
        """CSRF error returns 400 with custom page."""
        # Enable CSRF for this specific test
        app.config["WTF_CSRF_ENABLED"] = True
        test_client = app.test_client()
        resp = test_client.post("/settings/flaresolverr", data={"timeout": "60"})
        assert resp.status_code == 400
        assert b"Request Rejected" in resp.data or b"CSRF" in resp.data

    def test_csrf_error_returns_json_for_api(self, app):
        """CSRF error returns JSON for API clients."""
        app.config["WTF_CSRF_ENABLED"] = True
        test_client = app.test_client()
        resp = test_client.post(
            "/settings/flaresolverr",
            data={"timeout": "60"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "CSRF" in data["error"]
