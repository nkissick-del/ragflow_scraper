"""Integration tests for HTMX requests with Basic Auth."""

import base64

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


def _basic_auth_header(username, password):
    """Build a Basic Auth header value."""
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {creds}"


@pytest.fixture
def auth_app():
    """Create test Flask app with Basic Auth ENABLED."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    mock_container.state_tracker.return_value.get_status.return_value = {
        "scraper": "test", "status": "idle", "is_running": False
    }
    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", True),
        patch.object(Config, "BASIC_AUTH_USERNAME", "testuser"),
        patch.object(Config, "BASIC_AUTH_PASSWORD", "testpass"),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
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
def noauth_app():
    """Create test Flask app with Basic Auth DISABLED."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    mock_container.state_tracker.return_value.get_status.return_value = {
        "scraper": "test", "status": "idle", "is_running": False
    }
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
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["RATELIMIT_ENABLED"] = False
        yield app
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


@pytest.fixture
def noauth_client(noauth_app):
    return noauth_app.test_client()


class TestHTMXBasicAuth:
    """Verify the server returns correct 401 responses to HTMX requests.

    The JS-side window.location.reload() behavior on 401 cannot be tested
    server-side; these tests confirm the prerequisite: HTMX requests get
    a proper 401 + WWW-Authenticate header when credentials are missing.
    """

    def test_htmx_request_without_credentials_returns_401(self, auth_client):
        """HTMX request without credentials should get 401 + WWW-Authenticate."""
        response = auth_client.get(
            "/scrapers",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert "Basic" in response.headers["WWW-Authenticate"]

    def test_htmx_request_with_valid_credentials_returns_200(self, auth_client):
        """HTMX request with correct credentials should succeed."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.list_scrapers") as mock_list, \
             patch("app.web.blueprints.scrapers.load_scraper_configs"):
            mock_list.return_value = []
            response = auth_client.get(
                "/scrapers",
                headers={
                    "HX-Request": "true",
                    "Authorization": _basic_auth_header("testuser", "testpass"),
                },
            )
            assert response.status_code == 200

    def test_htmx_request_with_bad_credentials_returns_401(self, auth_client):
        """HTMX request with wrong credentials should get 401."""
        response = auth_client.get(
            "/scrapers",
            headers={
                "HX-Request": "true",
                "Authorization": _basic_auth_header("wrong", "creds"),
            },
        )
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_htmx_request_auth_disabled_no_credentials_needed(self, noauth_client):
        """When auth is disabled, HTMX requests work without credentials."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.list_scrapers") as mock_list, \
             patch("app.web.blueprints.scrapers.load_scraper_configs"):
            mock_list.return_value = []
            response = noauth_client.get(
                "/scrapers",
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200


class TestAuthEdgeCases:
    """Test additional authentication edge cases."""

    def test_health_endpoint_exempt_from_auth(self, auth_client):
        """The /health endpoint should bypass auth and return 200."""
        response = auth_client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"

    def test_static_endpoint_exempt_from_auth(self, auth_client):
        """Static file requests should bypass auth (even if file not found)."""
        response = auth_client.get("/static/nonexistent.css")
        # Should NOT be 401 — static is exempt from auth
        assert response.status_code != 401

    def test_malformed_auth_header_returns_401(self, auth_client):
        """A malformed Authorization header should still return 401."""
        response = auth_client.get(
            "/scrapers",
            headers={"Authorization": "Basic !!!invalid-base64!!!"},
        )
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_missing_credentials_config_returns_500(self):
        """Auth enabled but no username/password configured should return 500."""
        mock_container = MagicMock()
        mock_container.settings.get_all.return_value = {}
        mock_container.state_tracker.return_value.get_all_status.return_value = {}
        patches = [
            patch("app.web.blueprints.scrapers.container", mock_container),
            patch("app.web.blueprints.scrapers.job_queue"),
            patch("app.web.blueprints.api_scrapers.job_queue"),
            patch("app.web.helpers.container", mock_container),
            patch("app.web.helpers.job_queue"),
            patch.object(Config, "BASIC_AUTH_ENABLED", True),
            patch.object(Config, "BASIC_AUTH_USERNAME", ""),
            patch.object(Config, "BASIC_AUTH_PASSWORD", ""),
            patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
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
            client = app.test_client()

            response = client.get(
                "/scrapers",
                headers={"Authorization": _basic_auth_header("any", "thing")},
            )
            assert response.status_code == 500
        finally:
            for p in reversed(started):
                p.stop()

    def test_non_htmx_request_also_requires_auth(self, auth_client):
        """Regular (non-HTMX) requests should also require auth when enabled."""
        response = auth_client.get("/scrapers")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
