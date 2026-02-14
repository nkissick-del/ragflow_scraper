"""
Shared web-layer runtime objects.
"""

import os
from app.config import Config
from app.container import get_container
from app.web.job_queue import JobQueue


def _create_job_store():
    """Create a JobStore if DATABASE_URL is configured, else return None."""
    from app.services import db_pool

    if not db_pool.is_configured():
        return None
    try:
        from app.services.job_store import JobStore

        pool = db_pool.get_pool()
        store = JobStore(pool)
        store.ensure_schema()
        return store
    except Exception:
        return None


def _create_redis_dispatch():
    """Create a RedisJobDispatch if REDIS_URL is configured, else return None."""
    from app.services import redis_pool

    if not redis_pool.is_available():
        return None
    try:
        from app.services.redis_job_dispatch import RedisJobDispatch

        client = redis_pool.get_redis()
        return RedisJobDispatch(client)
    except Exception:
        return None


container = get_container()
# Use daemon=True during testing to avoid hanging after tests complete.
# In production (PYTEST_CURRENT_TEST not set), use daemon=False for graceful shutdown.
is_testing = bool(os.getenv("PYTEST_CURRENT_TEST"))
job_queue = JobQueue(
    daemon=is_testing,
    max_workers=Config.MAX_CONCURRENT_DOWNLOADS if not is_testing else 1,
    job_store=_create_job_store(),
    redis_dispatch=_create_redis_dispatch(),
)
