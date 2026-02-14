"""Tests for app.services.redis_job_dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.services.redis_job_dispatch import (
    RedisJobDispatch,
    QUEUE_KEY,
    CANCEL_KEY_PREFIX,
    CANCEL_TTL,
    EVENTS_CHANNEL,
)


class TestRedisJobDispatchPush:
    """Test push (enqueue) operations."""

    def test_push_serializes_and_lpushes(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        descriptor = {"scraper_name": "test", "dry_run": True}
        dispatch.push(descriptor)

        redis.lpush.assert_called_once_with(QUEUE_KEY, json.dumps(descriptor))

    def test_push_multiple_jobs(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        dispatch.push({"name": "a"})
        dispatch.push({"name": "b"})

        assert redis.lpush.call_count == 2


class TestRedisJobDispatchPop:
    """Test pop (dequeue) operations."""

    def test_pop_returns_deserialized_descriptor(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        descriptor = {"scraper_name": "test", "max_pages": 5}
        redis.brpop.return_value = (QUEUE_KEY, json.dumps(descriptor))

        result = dispatch.pop(timeout=1)
        assert result == descriptor
        redis.brpop.assert_called_once_with(QUEUE_KEY, timeout=1)

    def test_pop_returns_none_on_timeout(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)
        redis.brpop.return_value = None

        result = dispatch.pop(timeout=1)
        assert result is None

    def test_queue_length(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)
        redis.llen.return_value = 3

        assert dispatch.queue_length() == 3
        redis.llen.assert_called_once_with(QUEUE_KEY)


class TestRedisJobDispatchCancel:
    """Test cancellation operations."""

    def test_request_cancel_sets_key(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        dispatch.request_cancel("my_scraper")

        redis.setex.assert_called_once_with(
            f"{CANCEL_KEY_PREFIX}my_scraper", CANCEL_TTL, "1"
        )

    def test_is_cancel_requested_true(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)
        redis.exists.return_value = 1

        assert dispatch.is_cancel_requested("my_scraper") is True
        redis.exists.assert_called_once_with(f"{CANCEL_KEY_PREFIX}my_scraper")

    def test_is_cancel_requested_false(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)
        redis.exists.return_value = 0

        assert dispatch.is_cancel_requested("my_scraper") is False

    def test_clear_cancel(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        dispatch.clear_cancel("my_scraper")

        redis.delete.assert_called_once_with(f"{CANCEL_KEY_PREFIX}my_scraper")


class TestRedisJobDispatchEvents:
    """Test pub/sub event operations."""

    def test_publish_event(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        dispatch.publish_event("running", "my_scraper", {"page": 1})

        expected = json.dumps({
            "type": "running",
            "scraper_name": "my_scraper",
            "data": {"page": 1},
        })
        redis.publish.assert_called_once_with(EVENTS_CHANNEL, expected)

    def test_publish_event_no_data(self):
        redis = MagicMock()
        dispatch = RedisJobDispatch(redis)

        dispatch.publish_event("completed", "my_scraper")

        expected = json.dumps({
            "type": "completed",
            "scraper_name": "my_scraper",
            "data": {},
        })
        redis.publish.assert_called_once_with(EVENTS_CHANNEL, expected)

    def test_subscribe_events(self):
        redis = MagicMock()
        pubsub = MagicMock()
        redis.pubsub.return_value = pubsub
        dispatch = RedisJobDispatch(redis)

        result = dispatch.subscribe_events()

        assert result is pubsub
        pubsub.subscribe.assert_called_once_with(EVENTS_CHANNEL)
