"""
Shared web-layer runtime objects.
"""

from app.container import get_container
from app.web.job_queue import JobQueue

container = get_container()
job_queue = JobQueue()
