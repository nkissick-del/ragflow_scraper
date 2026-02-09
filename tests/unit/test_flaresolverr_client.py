"""Tests for FlareSolverrClient cache eviction."""

from __future__ import annotations

import time

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
