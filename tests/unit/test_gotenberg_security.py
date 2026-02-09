"""Security tests for GotenbergClient."""

from unittest.mock import patch, Mock
import pytest
from app.services.gotenberg_client import GotenbergClient

@pytest.fixture
def client():
    return GotenbergClient(url="http://test-gotenberg:3156", timeout=30)

class TestGotenbergSecurity:
    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_sanitizes_script(self, mock_post, client):
        """Ensure <script> tags are removed from HTML before conversion."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4"
        mock_post.return_value = mock_resp

        malicious_html = "<html><body><p>Safe</p><script>alert('XSS')</script></body></html>"
        client.convert_html_to_pdf(malicious_html, title="Test")

        call_args = mock_post.call_args
        files = call_args[1]["files"]
        # content is bytes, decode to check
        content = files["files"][1].decode("utf-8")

        assert "<script>" not in content
        assert "alert('XSS')" not in content

    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_sanitizes_iframe(self, mock_post, client):
        """Ensure <iframe> tags are removed."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4"
        mock_post.return_value = mock_resp

        malicious_html = '<iframe src="http://evil.com"></iframe>'
        client.convert_html_to_pdf(malicious_html, title="Test")

        call_args = mock_post.call_args
        content = call_args[1]["files"]["files"][1].decode("utf-8")

        assert "<iframe" not in content
        assert "evil.com" not in content

    @patch("app.services.gotenberg_client.requests.post")
    def test_html_to_pdf_sanitizes_event_handlers(self, mock_post, client):
        """Ensure on* attributes are removed."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-1.4"
        mock_post.return_value = mock_resp

        malicious_html = '<img src="x" onerror="alert(1)">'
        client.convert_html_to_pdf(malicious_html, title="Test")

        call_args = mock_post.call_args
        content = call_args[1]["files"]["files"][1].decode("utf-8")

        assert "onerror" not in content
