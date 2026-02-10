"""
FlareSolverr client for bypassing Cloudflare and other anti-bot protections.

FlareSolverr is a proxy server to bypass Cloudflare and DDoS-GUARD protection.
https://github.com/FlareSolverr/FlareSolverr
"""

from __future__ import annotations

import time
from typing import Optional
from dataclasses import dataclass, field

import requests

from app.config import Config
from app.utils import get_logger
from app.utils.logging_config import log_event, log_exception
from app.services.settings_manager import get_settings


@dataclass
class FlareSolverResult:
    """Result from a FlareSolverr request."""

    success: bool
    status: int = 0
    html: str = ""
    url: str = ""
    cookies: list[dict[str, str]] = field(default_factory=list)
    user_agent: str = ""
    error: str = ""


class FlareSolverrClient:
    """
    Client for interacting with FlareSolverr.

    FlareSolverr can solve Cloudflare challenges and return the page content
    along with cookies that can be used for subsequent requests.
    """

    _CACHE_TTL_SECONDS: int = 3600
    _CACHE_MAX_SIZE: int = 50

    def __init__(
        self,
        url: Optional[str] = None,
        timeout: int = 60,
        max_timeout: int = 120,
    ):
        """
        Initialize the FlareSolverr client.

        Args:
            url: FlareSolverr URL (defaults to config)
            timeout: Request timeout in seconds
            max_timeout: Maximum time to wait for challenge solving
        """
        self.url = (url or Config.FLARESOLVERR_URL).rstrip("/")
        self.timeout = timeout
        self.max_timeout = max_timeout
        self.logger = get_logger("flaresolverr")
        self._success_count = 0
        self._failure_count = 0
        self._timeout_count = 0

        # Cache for sessions (cookies + user agent)
        self._session_cache: dict[str, dict] = {}

    @property
    def is_configured(self) -> bool:
        """Check if FlareSolverr is configured."""
        return bool(self.url)

    @property
    def is_enabled(self) -> bool:
        """Check if FlareSolverr is enabled (via UI settings)."""
        settings = get_settings()
        return settings.flaresolverr_enabled and self.is_configured

    def test_connection(self) -> bool:
        """
        Test the connection to FlareSolverr.

        Returns:
            True if connection is successful
        """
        if not self.is_configured:
            self.logger.warning("FlareSolverr URL not configured")
            return False

        try:
            response = requests.get(
                f"{self.url}/health",
                timeout=10,
            )
            if response.status_code == 200:
                self.logger.info("FlareSolverr connection successful")
                return True
            else:
                self.logger.warning(f"FlareSolverr health check returned {response.status_code}")
                return False
        except Exception as e:
            log_exception(self.logger, e, "flaresolverr.health.failed")
            return False

    def get_page(
        self,
        url: str,
        session_id: Optional[str] = None,
        max_timeout: Optional[int] = None,
    ) -> FlareSolverResult:
        """
        Get a page through FlareSolverr, solving any challenges.

        Args:
            url: URL to fetch
            session_id: Optional session ID to reuse cookies
            max_timeout: Max time to wait for challenge solving

        Returns:
            FlareSolverResult with HTML content and cookies
        """
        if not self.is_configured:
            return FlareSolverResult(
                success=False,
                error="FlareSolverr URL not configured",
            )

        self._evict_stale_sessions()

        effective_timeout_seconds = max_timeout or self.max_timeout
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": effective_timeout_seconds * 1000,
        }

        if session_id and session_id in self._session_cache:
            cached = self._session_cache[session_id]
            payload["cookies"] = cached.get("cookies", [])

        start = time.time()

        try:
            data, status_code = self._execute_request(payload, effective_timeout_seconds)
            if data.get("status") == "ok":
                return self._handle_success_response(data, session_id, start)
            else:
                return self._handle_error_response(data, status_code, start)
        except requests.Timeout:
            return self._handle_request_failure(None, start, is_timeout=True)
        except Exception as e:
            return self._handle_request_failure(e, start, is_timeout=False)

    def _execute_request(
        self, payload: dict, effective_timeout_seconds: int
    ) -> tuple[dict, int]:
        """POST to FlareSolverr and return (response_data, status_code).

        Raises on HTTP errors or connection failures.
        """
        request_timeout = effective_timeout_seconds + 30
        url = payload.get("url", "")
        self.logger.info(f"FlareSolverr request: {url} (timeout: {request_timeout}s)")

        response = requests.post(
            f"{self.url}/v1",
            json=payload,
            timeout=request_timeout,
        )

        if response.status_code != 200:
            self.logger.error(
                f"FlareSolverr returned {response.status_code}: {response.text[:500]}"
            )

        response.raise_for_status()
        return response.json(), response.status_code

    def _handle_success_response(
        self, data: dict, session_id: Optional[str], start: float
    ) -> FlareSolverResult:
        """Parse solution from a successful FlareSolverr response."""
        solution = data.get("solution", {})
        result = FlareSolverResult(
            success=True,
            status=solution.get("status", 200),
            html=solution.get("response", ""),
            url=solution.get("url", ""),
            cookies=solution.get("cookies", []),
            user_agent=solution.get("userAgent", ""),
        )

        if session_id:
            self._session_cache[session_id] = {
                "cookies": result.cookies,
                "user_agent": result.user_agent,
                "_cached_at": time.time(),
            }

        self.logger.info(f"FlareSolverr success: {len(result.html)} bytes")
        self._success_count += 1
        log_event(
            self.logger,
            "info",
            "flaresolverr.request.complete",
            duration_s=round(time.time() - start, 2),
            success=self._success_count,
            failure=self._failure_count,
            timeout=self._timeout_count,
            success_rate=self._compute_success_rate(),
        )
        return result

    def _handle_error_response(
        self, data: dict, status_code: int, start: float
    ) -> FlareSolverResult:
        """Handle a non-ok status from FlareSolverr."""
        error_msg = data.get("message", "Unknown error")
        log_event(
            self.logger,
            "warning",
            "flaresolverr.request.backend_failed",
            status_code=status_code,
            error=error_msg,
        )
        self._failure_count += 1
        log_event(
            self.logger,
            "warning",
            "flaresolverr.request.failed",
            duration_s=round(time.time() - start, 2),
            success=self._success_count,
            failure=self._failure_count,
            timeout=self._timeout_count,
            success_rate=self._compute_success_rate(),
            error=error_msg,
        )
        return FlareSolverResult(success=False, error=error_msg)

    def _handle_request_failure(
        self,
        exc: Optional[Exception],
        start: float,
        *,
        is_timeout: bool,
    ) -> FlareSolverResult:
        """Unified handler for timeout and general request exceptions."""
        if is_timeout:
            self.logger.error("FlareSolverr request timed out")
            self._timeout_count += 1
            log_event(
                self.logger,
                "warning",
                "flaresolverr.request.timeout",
                duration_s=round(time.time() - start, 2),
                success=self._success_count,
                failure=self._failure_count,
                timeout=self._timeout_count,
                success_rate=self._compute_success_rate(),
            )
            return FlareSolverResult(success=False, error="Request timed out")

        assert exc is not None
        log_exception(self.logger, exc, "flaresolverr.request.exception_raw")
        self._failure_count += 1
        log_event(
            self.logger,
            "error",
            "flaresolverr.request.exception",
            duration_s=round(time.time() - start, 2),
            success=self._success_count,
            failure=self._failure_count,
            timeout=self._timeout_count,
            success_rate=self._compute_success_rate(),
            error=str(exc),
        )
        return FlareSolverResult(success=False, error=str(exc))

    def create_session(self, session_id: str) -> bool:
        """
        Create a new FlareSolverr session.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session was created successfully
        """
        if not self.is_configured:
            return False

        try:
            response = requests.post(
                f"{self.url}/v1",
                json={
                    "cmd": "sessions.create",
                    "session": session_id,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                self.logger.info(f"Created FlareSolverr session: {session_id}")
                return True
            else:
                self.logger.error(f"Failed to create session: {data.get('message')}")
                return False

        except Exception as e:
            log_exception(self.logger, e, "flaresolverr.session.create_failed", session_id=session_id)
            return False

    def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a FlareSolverr session.

        Args:
            session_id: Session identifier to destroy

        Returns:
            True if session was destroyed successfully
        """
        if not self.is_configured:
            return False

        # Clear local cache
        self._session_cache.pop(session_id, None)

        try:
            response = requests.post(
                f"{self.url}/v1",
                json={
                    "cmd": "sessions.destroy",
                    "session": session_id,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                self.logger.info(f"Destroyed FlareSolverr session: {session_id}")
                return True
            return False

        except Exception as e:
            log_exception(self.logger, e, "flaresolverr.session.destroy_failed", session_id=session_id)
            return False

    def list_sessions(self) -> list[str]:
        """
        List active FlareSolverr sessions.

        Returns:
            List of session IDs
        """
        if not self.is_configured:
            return []

        try:
            response = requests.post(
                f"{self.url}/v1",
                json={"cmd": "sessions.list"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                return data.get("sessions", [])
            return []

        except Exception as e:
            log_exception(self.logger, e, "flaresolverr.session.list_failed")
            return []

    def get_cookies_for_requests(self, session_id: str) -> dict:
        """
        Get cookies in a format suitable for the requests library.

        Args:
            session_id: Session ID to get cookies for

        Returns:
            Dict of cookie name -> value
        """
        if session_id not in self._session_cache:
            return {}

        cookies = self._session_cache[session_id].get("cookies", [])
        return {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}

    def get_user_agent(self, session_id: str) -> str:
        """
        Get the user agent for a session.

        Args:
            session_id: Session ID

        Returns:
            User agent string
        """
        if session_id not in self._session_cache:
            return ""
        return self._session_cache[session_id].get("user_agent", "")

    def get_metrics(self) -> dict[str, float | int]:
        """Expose simple counters and success rate for observability."""
        total = self._success_count + self._failure_count + self._timeout_count
        success_rate = self._compute_success_rate()
        return {
            "success": self._success_count,
            "failure": self._failure_count,
            "timeout": self._timeout_count,
            "total": total,
            "success_rate": success_rate,
        }

    def _evict_stale_sessions(self) -> None:
        """Remove expired cache entries and enforce max size (LRU)."""
        now = time.time()

        # 1. Remove entries older than TTL
        expired = [
            sid for sid, data in self._session_cache.items()
            if now - data.get("_cached_at", 0) > self._CACHE_TTL_SECONDS
        ]
        for sid in expired:
            del self._session_cache[sid]

        # 2. If still over max size, remove oldest entries
        if len(self._session_cache) > self._CACHE_MAX_SIZE:
            sorted_entries = sorted(
                self._session_cache.items(),
                key=lambda item: item[1].get("_cached_at", 0),
            )
            to_remove = len(self._session_cache) - self._CACHE_MAX_SIZE
            for sid, _data in sorted_entries[:to_remove]:
                del self._session_cache[sid]

    def _compute_success_rate(self) -> float:
        total = self._success_count + self._failure_count + self._timeout_count
        if total == 0:
            return 0.0
        return round(self._success_count / total, 3)
