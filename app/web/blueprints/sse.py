"""
Server-Sent Events (SSE) endpoint for real-time scraper status updates.

Subscribes to Redis Pub/Sub channel ``scraper:events`` and streams
events to the browser as ``text/event-stream``.  When Redis is
unavailable, returns an empty 204 response.
"""

from __future__ import annotations

from flask import Blueprint, Response

bp = Blueprint("sse", __name__)


@bp.route("/api/events")
def events():
    """SSE endpoint — streams scraper status events in real time.

    Returns 204 No Content when Redis is unavailable so the UI
    can gracefully fall back to polling.
    """
    from app.services import redis_pool

    if not redis_pool.is_available():
        return Response(status=204)

    from app.services.redis_job_dispatch import RedisJobDispatch, EVENTS_CHANNEL

    def _stream():
        client = redis_pool.get_redis()
        dispatch = RedisJobDispatch(client)
        pubsub = dispatch.subscribe_events()
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        except GeneratorExit:
            pass
        finally:
            try:
                pubsub.unsubscribe(EVENTS_CHANNEL)
                pubsub.close()
            except Exception:
                pass

    return Response(
        _stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
