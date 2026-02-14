"""
Redis list-based job dispatch for scraper runs.

Uses LPUSH/BRPOP on a Redis list for reliable FIFO ordering.
Cancellation uses short-lived Redis keys with TTL.
Real-time status updates use Redis Pub/Sub on a dedicated channel.
"""

from __future__ import annotations

import json
from typing import Any, Optional


QUEUE_KEY = "scraper:job_queue"
CANCEL_KEY_PREFIX = "scraper:cancel:"
CANCEL_TTL = 3600  # 1 hour
EVENTS_CHANNEL = "scraper:events"


class RedisJobDispatch:
    """Redis list-based job dispatcher."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    # ── dispatch ────────────────────────────────────────────────────

    def push(self, job_descriptor: dict[str, Any]) -> None:
        """Push a job descriptor onto the queue (FIFO via LPUSH/BRPOP)."""
        self._redis.lpush(QUEUE_KEY, json.dumps(job_descriptor))

    def pop(self, timeout: int = 1) -> Optional[dict[str, Any]]:
        """Pop next job from the queue (blocking).

        Args:
            timeout: BRPOP timeout in seconds (0 = block forever).

        Returns:
            Job descriptor dict or None on timeout.
        """
        result = self._redis.brpop(QUEUE_KEY, timeout=timeout)
        if result is None:
            return None
        # BRPOP returns (key, value)
        _, payload = result
        return json.loads(payload)

    def queue_length(self) -> int:
        """Return the current queue length."""
        return self._redis.llen(QUEUE_KEY)

    # ── cancellation ────────────────────────────────────────────────

    def request_cancel(self, scraper_name: str) -> None:
        """Set a cancellation flag for a scraper (auto-expires)."""
        key = f"{CANCEL_KEY_PREFIX}{scraper_name}"
        self._redis.setex(key, CANCEL_TTL, "1")

    def is_cancel_requested(self, scraper_name: str) -> bool:
        """Check if cancellation was requested for a scraper."""
        key = f"{CANCEL_KEY_PREFIX}{scraper_name}"
        return self._redis.exists(key) > 0

    def clear_cancel(self, scraper_name: str) -> None:
        """Clear the cancellation flag after job completes."""
        key = f"{CANCEL_KEY_PREFIX}{scraper_name}"
        self._redis.delete(key)

    # ── events (pub/sub) ────────────────────────────────────────────

    def publish_event(
        self,
        event_type: str,
        scraper_name: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        """Publish a status event to the events channel."""
        payload = {
            "type": event_type,
            "scraper_name": scraper_name,
            "data": data or {},
        }
        self._redis.publish(EVENTS_CHANNEL, json.dumps(payload))

    def subscribe_events(self):
        """Create and return a Pub/Sub subscription to the events channel.

        Returns:
            A pubsub object — caller should iterate with .listen().
        """
        pubsub = self._redis.pubsub()
        pubsub.subscribe(EVENTS_CHANNEL)
        return pubsub
