"""Tests for app.services.db_pool."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config


class TestDbPool:
    """Unit tests for the shared database connection pool."""

    def setup_method(self):
        """Reset module-level state before each test."""
        import app.services.db_pool as mod

        mod._pool = None

    def teardown_method(self):
        import app.services.db_pool as mod

        mod._pool = None

    def test_is_configured_true(self):
        from app.services import db_pool

        with patch.object(Config, "DATABASE_URL", "postgresql://localhost/test"):
            assert db_pool.is_configured() is True

    def test_is_configured_false(self):
        from app.services import db_pool

        with patch.object(Config, "DATABASE_URL", ""):
            assert db_pool.is_configured() is False

    def test_get_pool_creates_pool(self):
        import app.services.db_pool as mod

        mock_pool_instance = MagicMock()
        mock_pool_cls = MagicMock(return_value=mock_pool_instance)

        with (
            patch.object(Config, "DATABASE_URL", "postgresql://localhost/test"),
            patch("psycopg_pool.ConnectionPool", mock_pool_cls),
        ):
            mod._pool = None
            result = mod.get_pool()

            assert result is mock_pool_instance
            mock_pool_cls.assert_called_once_with(
                "postgresql://localhost/test",
                min_size=2,
                max_size=10,
                open=True,
            )

    def test_get_pool_raises_when_unconfigured(self):
        from app.services import db_pool

        with patch.object(Config, "DATABASE_URL", ""):
            with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
                db_pool.get_pool()

    def test_get_pool_returns_same_instance(self):
        from app.services import db_pool

        mock_pool_instance = MagicMock()
        mock_pool_cls = MagicMock(return_value=mock_pool_instance)

        with (
            patch.object(Config, "DATABASE_URL", "postgresql://localhost/test"),
            patch("psycopg_pool.ConnectionPool", mock_pool_cls),
        ):
            pool1 = db_pool.get_pool()
            pool2 = db_pool.get_pool()
            assert pool1 is pool2
            # Constructor should be called only once
            mock_pool_cls.assert_called_once()

    def test_close_pool_closes_and_resets(self):
        from app.services import db_pool

        mock_pool_instance = MagicMock()
        db_pool._pool = mock_pool_instance

        db_pool.close_pool()

        mock_pool_instance.close.assert_called_once()
        assert db_pool._pool is None

    def test_close_pool_noop_when_none(self):
        from app.services import db_pool

        db_pool._pool = None
        db_pool.close_pool()  # Should not raise
        assert db_pool._pool is None
