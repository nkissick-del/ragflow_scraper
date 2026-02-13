"""Unit tests for FlareSolverrPageFetchMixin."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.config import Config
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin
from app.services.flaresolverr_client import FlareSolverResult


class MixinHost(FlareSolverrPageFetchMixin):
    """Minimal host class to test the mixin in isolation."""

    def __init__(self):
        self.logger = Mock()


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def host():
    return MixinHost()


# ── Init / Cleanup ────────────────────────────────────────────────────


class TestInit:
    """Tests for _init_flaresolverr_page_fetch()."""

    @patch("app.scrapers.flaresolverr_mixin.FlareSolverrClient")
    @patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    @patch.object(Config, "FLARESOLVERR_TIMEOUT", 60)
    @patch.object(Config, "FLARESOLVERR_MAX_TIMEOUT", 120)
    def test_creates_client_and_session(self, mock_client_cls, host):
        """Init creates a FlareSolverr client and session."""
        mock_client = Mock()
        mock_client.create_session.return_value = True
        mock_client_cls.return_value = mock_client

        host._init_flaresolverr_page_fetch()

        assert host._fs_client is mock_client
        assert host._fs_session_id is not None
        mock_client.create_session.assert_called_once_with(host._fs_session_id)

    @patch("app.scrapers.flaresolverr_mixin.FlareSolverrClient")
    @patch.object(Config, "FLARESOLVERR_URL", "http://flaresolverr:8191")
    @patch.object(Config, "FLARESOLVERR_TIMEOUT", 60)
    @patch.object(Config, "FLARESOLVERR_MAX_TIMEOUT", 120)
    def test_session_creation_failure_sets_none(self, mock_client_cls, host):
        """If session creation fails, _fs_session_id is set to None."""
        mock_client = Mock()
        mock_client.create_session.return_value = False
        mock_client_cls.return_value = mock_client

        host._init_flaresolverr_page_fetch()

        assert host._fs_client is mock_client
        assert host._fs_session_id is None
        host.logger.warning.assert_called_once()


class TestCleanup:
    """Tests for _cleanup_flaresolverr_page_fetch()."""

    def test_destroys_session(self, host):
        """Cleanup destroys the session and clears state."""
        mock_client = Mock()
        host._fs_client = mock_client
        host._fs_session_id = "test-session"

        host._cleanup_flaresolverr_page_fetch()

        mock_client.destroy_session.assert_called_once_with("test-session")
        assert host._fs_client is None
        assert host._fs_session_id is None

    def test_cleanup_without_session(self, host):
        """Cleanup with no session_id still clears state."""
        mock_client = Mock()
        host._fs_client = mock_client
        host._fs_session_id = None

        host._cleanup_flaresolverr_page_fetch()

        mock_client.destroy_session.assert_not_called()
        assert host._fs_client is None

    def test_cleanup_without_client(self, host):
        """Cleanup with no client does not raise."""
        host._fs_client = None
        host._fs_session_id = None

        # Should not raise
        host._cleanup_flaresolverr_page_fetch()

    def test_cleanup_ignores_destroy_exception(self, host):
        """Cleanup swallows exceptions from destroy_session."""
        mock_client = Mock()
        mock_client.destroy_session.side_effect = Exception("network error")
        host._fs_client = mock_client
        host._fs_session_id = "test-session"

        # Should not raise
        host._cleanup_flaresolverr_page_fetch()
        assert host._fs_client is None


# ── fetch_rendered_page ───────────────────────────────────────────────


class TestFetchRenderedPage:
    """Tests for fetch_rendered_page()."""

    def test_returns_html_on_success(self, host):
        """Returns HTML string when FlareSolverr succeeds."""
        mock_client = Mock()
        mock_client.get_page.return_value = FlareSolverResult(
            success=True,
            html="<html>test</html>",
            url="http://example.com",
        )
        host._fs_client = mock_client
        host._fs_session_id = "sess"

        result = host.fetch_rendered_page("http://example.com")

        assert result == "<html>test</html>"
        mock_client.get_page.assert_called_once_with(
            "http://example.com", session_id="sess"
        )

    def test_returns_empty_on_failure(self, host):
        """Returns empty string when FlareSolverr fails."""
        mock_client = Mock()
        mock_client.get_page.return_value = FlareSolverResult(
            success=False,
            error="Challenge failed",
        )
        host._fs_client = mock_client
        host._fs_session_id = "sess"

        result = host.fetch_rendered_page("http://example.com")

        assert result == ""

    def test_returns_empty_without_client(self, host):
        """Returns empty string when client is not initialized."""
        host._fs_client = None

        result = host.fetch_rendered_page("http://example.com")

        assert result == ""


# ── fetch_rendered_page_full ──────────────────────────────────────────


class TestFetchRenderedPageFull:
    """Tests for fetch_rendered_page_full()."""

    def test_returns_full_result(self, host):
        """Returns complete FlareSolverResult."""
        expected = FlareSolverResult(
            success=True,
            html="<html>full</html>",
            url="http://example.com/final",
            cookies=[{"name": "cf", "value": "abc"}],
            user_agent="Mozilla/5.0",
        )
        mock_client = Mock()
        mock_client.get_page.return_value = expected
        host._fs_client = mock_client
        host._fs_session_id = "sess"

        result = host.fetch_rendered_page_full("http://example.com")

        assert result is expected
        assert result.url == "http://example.com/final"
        assert result.cookies == [{"name": "cf", "value": "abc"}]

    def test_returns_failure_without_client(self, host):
        """Returns failure result when client is not initialized."""
        host._fs_client = None

        result = host.fetch_rendered_page_full("http://example.com")

        assert result.success is False
        assert "not initialized" in result.error

    def test_passes_session_id_none(self, host):
        """Passes None session_id when no session was created."""
        mock_client = Mock()
        mock_client.get_page.return_value = FlareSolverResult(
            success=True, html="<html></html>"
        )
        host._fs_client = mock_client
        host._fs_session_id = None

        host.fetch_rendered_page_full("http://example.com")

        mock_client.get_page.assert_called_once_with(
            "http://example.com", session_id=None
        )
