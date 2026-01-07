"""
Shared web-layer runtime objects.
"""

import os
from app.container import get_container
from app.web.job_queue import JobQueue

container = get_container()
# Use daemon=True during testing to avoid hanging after tests complete.
# In production (PYTEST_CURRENT_TEST not set), use daemon=False for graceful shutdown.
is_testing = bool(os.getenv("PYTEST_CURRENT_TEST"))
job_queue = JobQueue(daemon=is_testing)
