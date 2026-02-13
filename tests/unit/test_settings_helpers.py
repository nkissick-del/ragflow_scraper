"""Tests for settings helper functions (app/web/blueprints/settings/helpers.py).

Most tests call helper functions directly (no Flask app needed).
Only tests that need `container.settings` require patching.
"""

from unittest.mock import patch, MagicMock

from app.config import Config


# ---------------------------------------------------------------------------
# _check_service_status
# ---------------------------------------------------------------------------


class TestCheckServiceStatus:
    """Tests for _check_service_status helper."""

    def test_success_returns_connected(self):
        from app.web.blueprints.settings.helpers import _check_service_status
        result = _check_service_status(lambda: True, "test_service")
        assert result == "connected"

    def test_failure_returns_disconnected(self):
        from app.web.blueprints.settings.helpers import _check_service_status
        result = _check_service_status(lambda: False, "test_service")
        assert result == "disconnected"

    def test_exception_returns_error(self):
        from app.web.blueprints.settings.helpers import _check_service_status

        def _raise():
            raise ConnectionError("refused")

        result = _check_service_status(_raise, "test_service")
        assert result == "error"


# ---------------------------------------------------------------------------
# _get_effective_url
# ---------------------------------------------------------------------------


class TestGetEffectiveUrl:
    """Tests for _get_effective_url helper."""

    def test_settings_override(self):
        from app.web.blueprints.settings.helpers import _get_effective_url

        mock_container = MagicMock()
        mock_container.settings.get.return_value = "http://override:3000"

        with patch("app.web.blueprints.settings.helpers.container", mock_container):
            result = _get_effective_url("gotenberg", "GOTENBERG_URL")

        assert result == "http://override:3000"

    def test_config_fallback(self):
        from app.web.blueprints.settings.helpers import _get_effective_url

        mock_container = MagicMock()
        mock_container.settings.get.return_value = ""

        with patch("app.web.blueprints.settings.helpers.container", mock_container), \
             patch.object(Config, "GOTENBERG_URL", "http://config:3000"):
            result = _get_effective_url("gotenberg", "GOTENBERG_URL")

        assert result == "http://config:3000"

    def test_empty_override_returns_config(self):
        from app.web.blueprints.settings.helpers import _get_effective_url

        mock_container = MagicMock()
        mock_container.settings.get.return_value = ""

        with patch("app.web.blueprints.settings.helpers.container", mock_container), \
             patch.object(Config, "TIKA_SERVER_URL", "http://tika:9998"):
            result = _get_effective_url("tika", "TIKA_SERVER_URL")

        assert result == "http://tika:9998"

    def test_no_config_attr_returns_empty(self):
        from app.web.blueprints.settings.helpers import _get_effective_url

        mock_container = MagicMock()
        mock_container.settings.get.return_value = ""

        with patch("app.web.blueprints.settings.helpers.container", mock_container):
            result = _get_effective_url("nonexistent", "NONEXISTENT_URL")

        assert result == ""


# ---------------------------------------------------------------------------
# _get_effective_timeout
# ---------------------------------------------------------------------------


class TestGetEffectiveTimeout:
    """Tests for _get_effective_timeout helper."""

    def test_settings_override_positive(self):
        from app.web.blueprints.settings.helpers import _get_effective_timeout

        mock_container = MagicMock()
        mock_container.settings.get.return_value = 30

        with patch("app.web.blueprints.settings.helpers.container", mock_container):
            result = _get_effective_timeout("gotenberg", "GOTENBERG_TIMEOUT")

        assert result == 30

    def test_zero_falls_to_config(self):
        from app.web.blueprints.settings.helpers import _get_effective_timeout

        mock_container = MagicMock()
        mock_container.settings.get.return_value = 0

        with patch("app.web.blueprints.settings.helpers.container", mock_container), \
             patch.object(Config, "GOTENBERG_TIMEOUT", 90):
            result = _get_effective_timeout("gotenberg", "GOTENBERG_TIMEOUT")

        assert result == 90

    def test_no_override_uses_config(self):
        from app.web.blueprints.settings.helpers import _get_effective_timeout

        mock_container = MagicMock()
        mock_container.settings.get.return_value = 0

        with patch("app.web.blueprints.settings.helpers.container", mock_container), \
             patch.object(Config, "TIKA_TIMEOUT", 120):
            result = _get_effective_timeout("tika", "TIKA_TIMEOUT")

        assert result == 120


# ---------------------------------------------------------------------------
# _get_effective_backend
# ---------------------------------------------------------------------------


class TestGetEffectiveBackend:
    """Tests for _get_effective_backend helper."""

    def test_settings_override(self):
        from app.web.blueprints.settings.helpers import _get_effective_backend

        mock_container = MagicMock()
        mock_container.settings.get.return_value = "docling"

        with patch("app.web.blueprints.settings.helpers.container", mock_container):
            result = _get_effective_backend("parser")

        assert result == "docling"

    def test_config_fallback(self):
        from app.web.blueprints.settings.helpers import _get_effective_backend

        mock_container = MagicMock()
        mock_container.settings.get.return_value = ""

        with patch("app.web.blueprints.settings.helpers.container", mock_container), \
             patch.object(Config, "PARSER_BACKEND", "tika"):
            result = _get_effective_backend("parser")

        assert result == "tika"


# ---------------------------------------------------------------------------
# _validate_url_ssrf
# ---------------------------------------------------------------------------


class TestValidateUrlSsrf:
    """Tests for _validate_url_ssrf helper."""

    def test_clean_url_returns_none(self):
        from app.web.blueprints.settings.helpers import _validate_url_ssrf

        # Patch socket.getaddrinfo to return a non-blocked IP
        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 80)),
            ]
            result = _validate_url_ssrf("http://example.com")

        assert result is None

    def test_link_local_address_blocked(self):
        from app.web.blueprints.settings.helpers import _validate_url_ssrf

        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_gai:
            # 169.254.x.x is link-local, which is blocked
            mock_gai.return_value = [
                (2, 1, 6, "", ("169.254.169.254", 80)),
            ]
            result = _validate_url_ssrf("http://metadata.internal")

        assert result is not None
        assert "blocked address range" in result

    def test_hostname_not_found(self):
        from app.web.blueprints.settings.helpers import _validate_url_ssrf
        import socket

        with patch("app.web.blueprints.settings.helpers.socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = socket.gaierror("Name or service not known")
            result = _validate_url_ssrf("http://nonexistent.invalid")

        assert result is not None
        assert "could not be resolved" in result

    def test_no_hostname_returns_error(self):
        from app.web.blueprints.settings.helpers import _validate_url_ssrf

        result = _validate_url_ssrf("://no-hostname")
        assert result is not None


# ---------------------------------------------------------------------------
# _validate_scraper_name
# ---------------------------------------------------------------------------


class TestValidateScraperName:
    """Tests for _validate_scraper_name helper."""

    def test_valid_names(self):
        from app.web.blueprints.settings.helpers import _validate_scraper_name

        assert _validate_scraper_name("my_scraper") is True
        assert _validate_scraper_name("my-scraper") is True
        assert _validate_scraper_name("Scraper123") is True
        assert _validate_scraper_name("a") is True

    def test_invalid_names(self):
        from app.web.blueprints.settings.helpers import _validate_scraper_name

        assert _validate_scraper_name("bad name") is False
        assert _validate_scraper_name("bad.name") is False
        assert _validate_scraper_name("../etc/passwd") is False
        assert _validate_scraper_name("") is False
        assert _validate_scraper_name("name;rm -rf") is False
