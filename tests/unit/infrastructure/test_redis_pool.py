"""Tests for app.services.redis_pool."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config


class TestRedisPool:
    """Unit tests for the shared Redis client pool."""

    def setup_method(self):
        import app.services.redis_pool as mod

        mod._client = None

    def teardown_method(self):
        import app.services.redis_pool as mod

        mod._client = None

    def test_is_configured_true(self):
        from app.services import redis_pool

        with patch.object(Config, "REDIS_URL", "redis://localhost:6379/0"):
            assert redis_pool.is_configured() is True

    def test_is_configured_false(self):
        from app.services import redis_pool

        with patch.object(Config, "REDIS_URL", ""):
            assert redis_pool.is_configured() is False

    def test_get_redis_raises_when_unconfigured(self):
        from app.services import redis_pool

        with patch.object(Config, "REDIS_URL", ""):
            with pytest.raises(ValueError, match="REDIS_URL is not configured"):
                redis_pool.get_redis()

    def test_get_redis_creates_client(self):
        from app.services import redis_pool

        mock_client = MagicMock()
        mock_from_url = MagicMock(return_value=mock_client)

        with (
            patch.object(Config, "REDIS_URL", "redis://localhost:6379/0"),
            patch("valkey.from_url", mock_from_url),
        ):
            client = redis_pool.get_redis()
            assert client is mock_client
            mock_from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                decode_responses=True,
            )

    def test_get_redis_returns_same_instance(self):
        from app.services import redis_pool

        mock_client = MagicMock()
        mock_from_url = MagicMock(return_value=mock_client)

        with (
            patch.object(Config, "REDIS_URL", "redis://localhost:6379/0"),
            patch("valkey.from_url", mock_from_url),
        ):
            c1 = redis_pool.get_redis()
            c2 = redis_pool.get_redis()
            assert c1 is c2
            mock_from_url.assert_called_once()

    def test_is_available_true(self):
        from app.services import redis_pool

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        redis_pool._client = mock_client

        with patch.object(Config, "REDIS_URL", "redis://localhost:6379/0"):
            assert redis_pool.is_available() is True

    def test_is_available_false_when_unconfigured(self):
        from app.services import redis_pool

        with patch.object(Config, "REDIS_URL", ""):
            assert redis_pool.is_available() is False

    def test_is_available_false_on_connection_error(self):
        from app.services import redis_pool

        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("refused")
        redis_pool._client = mock_client

        with patch.object(Config, "REDIS_URL", "redis://localhost:6379/0"):
            assert redis_pool.is_available() is False

    def test_close_redis_closes_and_resets(self):
        from app.services import redis_pool

        mock_client = MagicMock()
        redis_pool._client = mock_client

        redis_pool.close_redis()

        mock_client.close.assert_called_once()
        assert redis_pool._client is None

    def test_close_redis_noop_when_none(self):
        from app.services import redis_pool

        redis_pool._client = None
        redis_pool.close_redis()  # Should not raise
        assert redis_pool._client is None
