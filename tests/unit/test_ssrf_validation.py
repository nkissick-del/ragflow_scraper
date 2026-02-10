"""Unit tests for SSRF URL validation in settings."""

import socket
from unittest.mock import patch, MagicMock


def _get_validate_fn():
    """Import _validate_url_ssrf without triggering blueprint __init__ chain."""
    # Patch get_logger to avoid /app/data/logs/ FileNotFoundError
    with patch("app.utils.get_logger", return_value=MagicMock()):
        from app.web.blueprints.settings.helpers import _validate_url_ssrf
    return _validate_url_ssrf


class TestSSRFValidation:

    def test_blocked_link_local_ip(self):
        """Link-local addresses (169.254.x.x) should be blocked."""
        validate = _get_validate_fn()
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))
            ]
            result = validate("http://metadata.example.com/")
            assert result is not None
            assert "blocked" in result.lower()

    def test_private_ip_allowed(self):
        """Private RFC1918 addresses should be ALLOWED (local-network services)."""
        validate = _get_validate_fn()
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.100", 80))
            ]
            result = validate("http://local-service.lan:8000/")
            assert result is None

    def test_dns_failure_rejects(self):
        """DNS resolution failure should return an error message."""
        validate = _get_validate_fn()
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_dns, \
             patch("app.web.blueprints.settings.helpers.log_event"):
            mock_dns.side_effect = socket.gaierror("Name resolution failed")
            result = validate("http://nonexistent.invalid/")
            assert result is not None
            assert "could not be resolved" in result

    def test_no_hostname_rejects(self):
        """URL with no hostname should be rejected."""
        validate = _get_validate_fn()
        result = validate("http:///path")
        assert result is not None
        assert "no hostname" in result.lower()

    def test_ipv6_link_local_blocked(self):
        """IPv6 link-local (fe80::/10) should be blocked."""
        validate = _get_validate_fn()
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 80, 0, 0))
            ]
            result = validate("http://[fe80::1]/")
            assert result is not None
            assert "blocked" in result.lower()

    def test_public_ip_allowed(self):
        """Public IP addresses should be allowed."""
        validate = _get_validate_fn()
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))
            ]
            result = validate("http://dns.google/")
            assert result is None
