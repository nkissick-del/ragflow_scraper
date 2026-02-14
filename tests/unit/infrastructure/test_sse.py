"""Tests for SSE blueprint."""

from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestSSEEndpoint:
    """Test /api/events SSE endpoint."""

    def test_returns_204_when_redis_unavailable(self):
        """Should return 204 when Redis is not available."""
        from flask import Flask
        from app.web.blueprints.sse import bp

        app = Flask(__name__)
        app.register_blueprint(bp)

        with patch("app.services.redis_pool.is_available", return_value=False):
            with app.test_client() as client:
                response = client.get("/api/events")
                assert response.status_code == 204

    def test_returns_event_stream_when_redis_available(self):
        """Should return text/event-stream content type when Redis works."""
        from flask import Flask
        from app.web.blueprints.sse import bp

        app = Flask(__name__)
        app.register_blueprint(bp)

        mock_pubsub = MagicMock()
        # Simulate one message then stop
        mock_pubsub.listen.return_value = iter([
            {"type": "subscribe", "data": None},
            {"type": "message", "data": '{"type":"running","scraper_name":"test"}'},
        ])

        mock_client = MagicMock()

        mock_dispatch_instance = MagicMock()
        mock_dispatch_instance.subscribe_events.return_value = mock_pubsub

        mock_dispatch_cls = MagicMock(return_value=mock_dispatch_instance)

        with (
            patch("app.services.redis_pool.is_available", return_value=True),
            patch("app.services.redis_pool.get_redis", return_value=mock_client),
            patch(
                "app.services.redis_job_dispatch.RedisJobDispatch",
                mock_dispatch_cls,
            ),
        ):
            with app.test_client() as client:
                response = client.get("/api/events")
                assert response.content_type.startswith("text/event-stream")
                # Read the streamed data
                data = response.get_data(as_text=True)
                assert "running" in data
