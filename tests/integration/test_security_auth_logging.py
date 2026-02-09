"""Integration tests for auth bypass/failure logging."""

import base64
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
        patch.object(Config, "BASIC_AUTH_ENABLED", True),
        patch.object(Config, "BASIC_AUTH_USERNAME", "admin"),
        patch.object(Config, "BASIC_AUTH_PASSWORD", "secret"),
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


def _basic_auth_header(username, password):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


class TestAuthLogging:

    def test_malformed_header_logs_warning(self, client):
        """Malformed base64 auth header should log warning and return 401."""
        with patch("app.web.blueprints.auth.log_event") as mock_log:
            response = client.get("/", headers={"Authorization": "Basic %%%notbase64"})
            assert response.status_code == 401
            mock_log.assert_any_call(
                pytest.importorskip("app.web.blueprints.auth").logger,
                "warning",
                "auth.header.malformed",
                remote_addr="127.0.0.1",
                endpoint="scrapers.index",
            )

    def test_wrong_creds_logs_auth_failure(self, client):
        """Wrong credentials should log auth.failure warning."""
        with patch("app.web.blueprints.auth.log_event") as mock_log:
            response = client.get("/", headers=_basic_auth_header("wrong", "creds"))
            assert response.status_code == 401
            mock_log.assert_any_call(
                pytest.importorskip("app.web.blueprints.auth").logger,
                "warning",
                "auth.failure",
                endpoint="scrapers.index",
            )

    def test_valid_auth_passes(self, client):
        """Valid credentials should return 200."""
        response = client.get("/", headers=_basic_auth_header("admin", "secret"))
        assert response.status_code == 200
