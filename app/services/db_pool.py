"""
Shared PostgreSQL connection pool (singleton).

Provides a single psycopg ConnectionPool for all consumers
(job_store, state_store, pgvector_store) so the application
holds one pool instead of N.

When DATABASE_URL is empty the pool is not created and
is_configured() returns False — callers should check before use.
"""

from __future__ import annotations

import threading

from app.config import Config


_pool = None
_pool_lock = threading.Lock()


def is_configured() -> bool:
    """Return True when DATABASE_URL is set."""
    return bool(Config.DATABASE_URL)


def get_pool():
    """Get or create the shared ConnectionPool (lazy, thread-safe).

    Raises:
        ValueError: If DATABASE_URL is not configured.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not is_configured():
                    raise ValueError("DATABASE_URL is not configured")
                from psycopg_pool import ConnectionPool

                _pool = ConnectionPool(
                    Config.DATABASE_URL,
                    min_size=2,
                    max_size=10,
                    timeout=10.0,
                    open=True,
                    check=ConnectionPool.check_connection,
                )
    return _pool


def close_pool() -> None:
    """Close the shared pool (idempotent, thread-safe)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
