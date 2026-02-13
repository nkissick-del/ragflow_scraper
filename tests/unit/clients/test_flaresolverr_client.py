"""Tests for FlareSolverrClient."""

from __future__ import annotations

import time
from unittest.mock import patch, Mock

import requests

from app.services.flaresolverr_client import FlareSolverrClient


class TestSessionCacheEviction:
    """Test TTL and LRU cache eviction."""

    def _make_client(self) -> FlareSolverrClient:
        """Create a client with a configured URL (no real network needed)."""
        return FlareSolverrClient(url="http://test-flaresolverr:8191")

    def test_session_cache_ttl_eviction(self):
        """Entries older than TTL should be evicted."""
        client = self._make_client()

        # Insert an old entry (2 hours ago)
        client._session_cache["old_session"] = {
            "cookies": [],
            "user_agent": "test",
            "_cached_at": time.time() - 7200,
        }
        # Insert a fresh entry
        client._session_cache["fresh_session"] = {
            "cookies": [],
            "user_agent": "test",
            "_cached_at": time.time(),
        }

        client._evict_stale_sessions()

        assert "old_session" not in client._session_cache
        assert "fresh_session" in client._session_cache

    def test_session_cache_max_size_eviction(self):
        """Cache should be trimmed to max size, removing oldest entries."""
        client = self._make_client()
        now = time.time()

        # Insert 55 entries (5 over max of 50), all within TTL
        for i in range(55):
            client._session_cache[f"session_{i:03d}"] = {
                "cookies": [],
                "user_agent": "test",
                "_cached_at": now - (55 - i),  # oldest first
            }

        assert len(client._session_cache) == 55

        client._evict_stale_sessions()

        assert len(client._session_cache) == 50
        # The 5 oldest should be removed
        for i in range(5):
            assert f"session_{i:03d}" not in client._session_cache
        # The 50 newest should remain
        for i in range(5, 55):
            assert f"session_{i:03d}" in client._session_cache

    def test_cache_stores_timestamp(self):
        """Cache entries should have _cached_at set after caching."""
        client = self._make_client()

        before = time.time()
        # Simulate what get_page() does when caching
        client._session_cache["test_session"] = {
            "cookies": [{"name": "cf", "value": "abc"}],
            "user_agent": "Mozilla/5.0",
            "_cached_at": time.time(),
        }
        after = time.time()

        entry = client._session_cache["test_session"]
        assert "_cached_at" in entry
        assert before <= entry["_cached_at"] <= after


# ── TestProperties ──────────────────────────────────────────────────────


class TestProperties:
    """Tests for is_configured and is_enabled properties."""

    def test_is_configured_true(self):
        """is_configured returns True when URL is set."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        assert client.is_configured is True

    @patch("app.services.flaresolverr_client.Config")
    def test_is_configured_false(self, mock_config):
        """is_configured returns False when URL is empty."""
        mock_config.FLARESOLVERR_URL = ""
        client = FlareSolverrClient(url="")
        assert client.is_configured is False

    @patch("app.services.flaresolverr_client.get_settings")
    def test_is_enabled_requires_settings_and_url(self, mock_get_settings):
        """is_enabled requires flaresolverr_enabled=True AND is_configured."""
        mock_settings = Mock()
        mock_settings.flaresolverr_enabled = True
        mock_get_settings.return_value = mock_settings

        client = FlareSolverrClient(url="http://flaresolverr:8191")
        assert client.is_enabled is True

    @patch("app.services.flaresolverr_client.get_settings")
    @patch("app.services.flaresolverr_client.Config")
    def test_is_enabled_false_without_url(self, mock_config, mock_get_settings):
        """is_enabled is False when URL is empty."""
        mock_config.FLARESOLVERR_URL = ""
        mock_settings = Mock()
        mock_settings.flaresolverr_enabled = True
        mock_get_settings.return_value = mock_settings

        client = FlareSolverrClient(url="")
        assert client.is_enabled is False


# ── TestGetPage ─────────────────────────────────────────────────────────


class TestGetPage:
    """Tests for get_page() method."""

    @patch("app.services.flaresolverr_client.requests.post")
    def test_success(self, mock_post):
        """Successful response extracts HTML, URL, and cookies."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {
                "status": 200,
                "url": "http://example.com/final",
                "response": "<html>content</html>",
                "cookies": [{"name": "cf", "value": "abc"}],
                "userAgent": "Mozilla/5.0",
            },
        }
        mock_post.return_value = mock_resp

        result = client.get_page("http://example.com")

        assert result.success is True
        assert "content" in result.html
        assert result.url == "http://example.com/final"
        assert len(result.cookies) == 1
        assert result.user_agent == "Mozilla/5.0"

    @patch("app.services.flaresolverr_client.requests.post")
    def test_url_field_default_empty(self, mock_post):
        """URL field defaults to empty string when not in solution."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {
                "status": 200,
                "response": "<html></html>",
                "cookies": [],
                "userAgent": "",
            },
        }
        mock_post.return_value = mock_resp

        result = client.get_page("http://example.com")

        assert result.success is True
        assert result.url == ""

    @patch("app.services.flaresolverr_client.requests.post")
    def test_backend_error(self, mock_post):
        """Backend error (status != ok) returns failure."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "status": "error",
            "message": "Challenge failed",
        }
        mock_post.return_value = mock_resp

        result = client.get_page("http://example.com")

        assert result.success is False
        assert "Challenge failed" in result.error

    @patch("app.services.flaresolverr_client.requests.post")
    def test_http_error(self, mock_post):
        """HTTP error raises and returns failure."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        result = client.get_page("http://example.com")

        assert result.success is False

    @patch("app.services.flaresolverr_client.requests.post")
    def test_timeout(self, mock_post):
        """Timeout returns failure with timeout error."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_post.side_effect = requests.Timeout("Timed out")

        result = client.get_page("http://example.com")

        assert result.success is False
        assert "timed out" in result.error.lower()

    @patch("app.services.flaresolverr_client.requests.post")
    def test_generic_exception(self, mock_post):
        """Generic exception returns failure."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_post.side_effect = ConnectionError("Connection refused")

        result = client.get_page("http://example.com")

        assert result.success is False

    @patch("app.services.flaresolverr_client.Config")
    def test_unconfigured_returns_failure(self, mock_config):
        """get_page with unconfigured client returns error."""
        mock_config.FLARESOLVERR_URL = ""
        client = FlareSolverrClient(url="")

        result = client.get_page("http://example.com")

        assert result.success is False
        assert "not configured" in result.error.lower()

    @patch("app.services.flaresolverr_client.requests.post")
    def test_session_cache_populated_on_success(self, mock_post):
        """Session cache is populated after successful get_page with session_id."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {
                "status": 200,
                "response": "<html></html>",
                "cookies": [{"name": "cf", "value": "xyz"}],
                "userAgent": "UA",
            },
        }
        mock_post.return_value = mock_resp

        client.get_page("http://example.com", session_id="sess-1")

        assert "sess-1" in client._session_cache
        assert client._session_cache["sess-1"]["user_agent"] == "UA"


# ── TestSessionManagement ──────────────────────────────────────────────


class TestSessionManagement:
    """Tests for create/destroy/list sessions."""

    @patch("app.services.flaresolverr_client.requests.post")
    def test_create_session_success(self, mock_post):
        """create_session returns True on success."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_resp

        assert client.create_session("sess-1") is True

    @patch("app.services.flaresolverr_client.requests.post")
    def test_destroy_session_success(self, mock_post):
        """destroy_session returns True on success."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_resp

        assert client.destroy_session("sess-1") is True

    @patch("app.services.flaresolverr_client.requests.post")
    def test_list_sessions_success(self, mock_post):
        """list_sessions returns session IDs."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {"status": "ok", "sessions": ["s1", "s2"]}
        mock_post.return_value = mock_resp

        result = client.list_sessions()
        assert result == ["s1", "s2"]

    @patch("app.services.flaresolverr_client.Config")
    def test_session_operations_return_false_unconfigured(self, mock_config):
        """Session ops return False/empty when unconfigured."""
        mock_config.FLARESOLVERR_URL = ""
        client = FlareSolverrClient(url="")

        assert client.create_session("s") is False
        assert client.destroy_session("s") is False
        assert client.list_sessions() == []


# ── TestTestConnection ──────────────────────────────────────────────────


class TestTestConnection:
    """Tests for test_connection()."""

    @patch("app.services.flaresolverr_client.requests.get")
    def test_success(self, mock_get):
        """Returns True on 200 health check."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert client.test_connection() is True

    @patch("app.services.flaresolverr_client.requests.get")
    def test_failure(self, mock_get):
        """Returns False on exception."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_get.side_effect = ConnectionError("refused")

        assert client.test_connection() is False

    @patch("app.services.flaresolverr_client.Config")
    def test_not_configured(self, mock_config):
        """Returns False when not configured."""
        mock_config.FLARESOLVERR_URL = ""
        client = FlareSolverrClient(url="")
        assert client.test_connection() is False


# ── TestMetrics ─────────────────────────────────────────────────────────


class TestMetrics:
    """Tests for metrics and cache accessors."""

    def test_initial_metrics_zero(self):
        """All metrics start at zero."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        metrics = client.get_metrics()

        assert metrics["success"] == 0
        assert metrics["failure"] == 0
        assert metrics["timeout"] == 0
        assert metrics["total"] == 0
        assert metrics["success_rate"] == 0.0

    @patch("app.services.flaresolverr_client.requests.post")
    def test_metrics_incremented_after_success(self, mock_post):
        """Success counter incremented after successful get_page."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {"status": 200, "response": "", "cookies": [], "userAgent": ""},
        }
        mock_post.return_value = mock_resp

        client.get_page("http://example.com")
        metrics = client.get_metrics()

        assert metrics["success"] == 1
        assert metrics["total"] == 1

    def test_get_cookies_from_cache(self):
        """get_cookies_for_requests extracts name/value dict."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        client._session_cache["s1"] = {
            "cookies": [
                {"name": "cf_clearance", "value": "abc"},
                {"name": "session", "value": "xyz"},
            ],
            "user_agent": "UA",
            "_cached_at": time.time(),
        }

        cookies = client.get_cookies_for_requests("s1")
        assert cookies == {"cf_clearance": "abc", "session": "xyz"}

    def test_get_user_agent_from_cache(self):
        """get_user_agent returns cached user agent."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        client._session_cache["s1"] = {
            "cookies": [],
            "user_agent": "Mozilla/5.0 Test",
            "_cached_at": time.time(),
        }

        assert client.get_user_agent("s1") == "Mozilla/5.0 Test"

    def test_get_cookies_missing_session(self):
        """get_cookies_for_requests returns empty for missing session."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        assert client.get_cookies_for_requests("nonexistent") == {}

    def test_get_user_agent_missing_session(self):
        """get_user_agent returns empty for missing session."""
        client = FlareSolverrClient(url="http://flaresolverr:8191")
        assert client.get_user_agent("nonexistent") == ""
