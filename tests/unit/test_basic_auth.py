import base64
import importlib

import pytest

from app.config import Config
from app.web import create_app
import app.web.blueprints.auth as auth_bp


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_basic_auth_disabled_allows_requests(monkeypatch):
    # Ensure auth is off
    monkeypatch.setattr(Config, "BASIC_AUTH_ENABLED", False)
    importlib.reload(auth_bp)

    app = create_app()
    client = app.test_client()

    resp = client.get("/logs")
    assert resp.status_code == 200


def test_basic_auth_blocks_without_credentials(monkeypatch):
    monkeypatch.setattr(Config, "BASIC_AUTH_ENABLED", True)
    monkeypatch.setattr(Config, "BASIC_AUTH_USERNAME", "user")
    monkeypatch.setattr(Config, "BASIC_AUTH_PASSWORD", "pass")
    importlib.reload(auth_bp)

    app = create_app()
    client = app.test_client()

    resp = client.get("/logs")
    assert resp.status_code == 401


def test_basic_auth_allows_with_valid_credentials(monkeypatch):
    monkeypatch.setattr(Config, "BASIC_AUTH_ENABLED", True)
    monkeypatch.setattr(Config, "BASIC_AUTH_USERNAME", "user")
    monkeypatch.setattr(Config, "BASIC_AUTH_PASSWORD", "pass")
    importlib.reload(auth_bp)

    app = create_app()
    client = app.test_client()

    resp = client.get("/logs", headers=_auth_header("user", "pass"))
    assert resp.status_code == 200
