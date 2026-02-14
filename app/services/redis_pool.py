"""
Singleton Redis/Valkey client.

Uses valkey-py (wire-compatible with Redis) for connection pooling.
When REDIS_URL is empty, is_configured() returns False and callers
should fall back to in-memory dispatch.
"""

from __future__ import annotations

import threading

from app.config import Config


_client = None
_client_lock = threading.Lock()


def is_configured() -> bool:
    """Return True when REDIS_URL is set."""
    return bool(Config.REDIS_URL)


def get_redis():
    """Get or create the shared Redis client (lazy, thread-safe).

    Raises:
        ValueError: If REDIS_URL is not configured.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not is_configured():
                    raise ValueError("REDIS_URL is not configured")
                import valkey

                _client = valkey.from_url(
                    Config.REDIS_URL,
                    decode_responses=True,
                )
    return _client


def is_available() -> bool:
    """Check if Redis is configured and reachable."""
    if not is_configured():
        return False
    try:
        client = get_redis()
        client.ping()
        return True
    except Exception:
        return False


def close_redis() -> None:
    """Close the shared client (idempotent, thread-safe)."""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None
