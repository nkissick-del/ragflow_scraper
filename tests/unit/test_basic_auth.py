"""Unit tests for HTTP Basic Authentication."""

import base64

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _make_app(auth_enabled: bool, username: str = "user", password: str = "pass"):
    """Create a Flask app with proper mocks and auth configuration."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}
    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", auth_enabled),
        patch.object(Config, "BASIC_AUTH_USERNAME", username),
        patch.object(Config, "BASIC_AUTH_PASSWORD", password),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-unit-tests"),
    ]
    started = []
    for p in patches:
        p.start()
        started.append(p)
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["RATELIMIT_ENABLED"] = False
    return app, started


@pytest.fixture
def auth_disabled_app():
    app, started = _make_app(auth_enabled=False)
    yield app
    for p in reversed(started):
        p.stop()


@pytest.fixture
def auth_enabled_app():
    app, started = _make_app(auth_enabled=True, username="user", password="pass")
    yield app
    for p in reversed(started):
        p.stop()


def test_basic_auth_disabled_allows_requests(auth_disabled_app):
    client = auth_disabled_app.test_client()
    resp = client.get("/logs")
    assert resp.status_code == 200


def test_basic_auth_blocks_without_credentials(auth_enabled_app):
    client = auth_enabled_app.test_client()
    resp = client.get("/logs")
    assert resp.status_code == 401


def test_basic_auth_allows_with_valid_credentials(auth_enabled_app):
    client = auth_enabled_app.test_client()
    resp = client.get("/logs", headers=_auth_header("user", "pass"))
    assert resp.status_code == 200
