"""Authentication hooks for the web app."""

from __future__ import annotations

import base64
import secrets
from flask import Blueprint, Response, request

from app.config import Config
from app.utils.logging_config import log_event
from app.utils import get_logger

bp = Blueprint("auth", __name__)
logger = get_logger("web.auth")


def _auth_failed() -> Response:
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": "Basic realm=\"PDF Scraper\""},
    )


@bp.before_app_request
def enforce_basic_auth():
    if not Config.BASIC_AUTH_ENABLED:
        return None

    # Validate auth credentials are configured
    if not Config.BASIC_AUTH_USERNAME or not Config.BASIC_AUTH_PASSWORD:
        logger.error(
            "BASIC_AUTH_ENABLED is True but credentials are not configured. "
            "Set BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD environment variables."
        )
        return Response(
            "Authentication misconfigured - missing credentials",
            500,
        )

    endpoint = (request.endpoint or "").split(".")[-1]
    if endpoint == "static":
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return _auth_failed()

    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return _auth_failed()

    # Use constant-time comparison to prevent timing attacks
    if (
        username
        and password
        and secrets.compare_digest(username, Config.BASIC_AUTH_USERNAME)
        and secrets.compare_digest(password, Config.BASIC_AUTH_PASSWORD)
    ):
        return None

    log_event(logger, "warning", "auth.failure", endpoint=request.endpoint)
    return _auth_failed()
