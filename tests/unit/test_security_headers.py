import pytest
from app.main import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_security_headers(client):
    response = client.get('/')
    headers = response.headers

    # Check for security headers
    assert 'X-Content-Type-Options' in headers
    assert headers['X-Content-Type-Options'] == 'nosniff'

    assert 'X-Frame-Options' in headers
    assert headers['X-Frame-Options'] in ['SAMEORIGIN', 'DENY']

    assert 'Referrer-Policy' in headers
    assert 'strict-origin-when-cross-origin' in headers['Referrer-Policy']

    assert 'Content-Security-Policy' in headers
