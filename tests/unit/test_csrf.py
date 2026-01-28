import pytest
from app.web import create_app
from flask_wtf.csrf import CSRFError

def test_csrf_extension_registered():
    app = create_app()
    assert "csrf" in app.extensions

def test_csrf_rejects_post_without_token():
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["TESTING"] = False # Force CSRF check
    app.config["SECRET_KEY"] = "test-secret"

    client = app.test_client()

    # Attempt POST request without token
    # Using a known route. 404 comes after CSRF check usually?
    # Actually, CSRF check happens before route matching? No, usually after.
    # But if I use a route that exists, e.g. /scrapers/test/run

    # We mock ScraperRegistry to avoid 404/500
    # But even 404 should be protected if it matches a route pattern?
    # Flask-WTF protects all views.

    resp = client.post("/scrapers/test/run")

    # Should be 400 CSRF Error
    assert resp.status_code == 400
    assert b"The CSRF token is missing" in resp.data
