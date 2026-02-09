"""Integration tests for security headers."""

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


def test_security_headers_present(client):
    """Verify that essential security headers are present in responses."""
    response = client.get("/")

    expected_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-XSS-Protection": "0",
    }

    for header, value in expected_headers.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == value, f"Incorrect value for {header}"


def test_csp_header_present(client):
    """Verify Content-Security-Policy header is set."""
    response = client.get("/")
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline' https://unpkg.com" in csp
    assert "object-src 'none'" in csp


def test_permissions_policy_present(client):
    """Verify Permissions-Policy header is set."""
    response = client.get("/")
    assert "Permissions-Policy" in response.headers
    pp = response.headers["Permissions-Policy"]
    assert "camera=()" in pp
    assert "microphone=()" in pp
    assert "geolocation=()" in pp


def test_hsts_not_set_on_http(client):
    """HSTS should NOT be set on plain HTTP requests."""
    response = client.get("/")
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_set_on_https():
    """HSTS should be set when request arrives via HTTPS (proxied)."""
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
        patch.object(Config, "TRUST_PROXY_COUNT", 1),
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
        test_client = application.test_client()
        response = test_client.get("/", headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == 200
        assert "Strict-Transport-Security" in response.headers
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    finally:
        for p in reversed(started):
            p.stop()
