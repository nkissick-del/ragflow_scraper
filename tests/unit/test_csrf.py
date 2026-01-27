import pytest
import re
from app.web import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "SECRET_KEY": "test-secret"
    })
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_csrf_protection_missing_token(client):
    """Test that POST requests without CSRF token are rejected."""
    # We use a scraper run endpoint as a target
    response = client.post("/scrapers/aemo/run", data={"dry_run": "true"})
    assert response.status_code == 400

def test_csrf_protection_with_valid_token(client):
    """Test that POST requests with valid CSRF token are accepted."""
    # 1. Get the page to get the CSRF token
    response = client.get("/settings")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', html)
    assert match is not None, "CSRF token meta tag not found"
    csrf_token = match.group(1)

    # 2. Send POST with token in header (HTMX style)
    # We use /settings/scraping which is a valid POST endpoint
    response = client.post(
        "/settings/scraping",
        data={"default_timeout": "60"},
        headers={"X-CSRFToken": csrf_token}
    )

    assert response.status_code != 400, f"Should not return 400 CSRF error. Response: {response.data}"
    # In a successful case it might return 200 or the swapped HTML
    assert response.status_code == 200
