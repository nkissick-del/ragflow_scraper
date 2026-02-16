"""Rate limiting singleton for the Flask app."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import Config


def _get_storage_uri() -> str:
    """Select Redis/Valkey when available, else in-memory."""
    if Config.REDIS_URL:
        return Config.REDIS_URL
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_get_storage_uri(),
)
