import pytest
from app.web import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Disable CSRF for testing
    })
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_security_headers_present(client):
    """Verify that essential security headers are present in responses."""
    response = client.get("/")

    # Headers we expect
    expected_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }

    for header, value in expected_headers.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == value, f"Incorrect value for {header}"
