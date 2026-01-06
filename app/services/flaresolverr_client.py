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
from app.services.settings_manager import get_settings


@dataclass
class FlareSolverResult:
    """Result from a FlareSolverr request."""

    success: bool
    status: int = 0
    html: str = ""
    cookies: list[dict[str, str]] = field(default_factory=list)
    user_agent: str = ""
    error: str = ""


class FlareSolverrClient:
    """
    Client for interacting with FlareSolverr.

    FlareSolverr can solve Cloudflare challenges and return the page content
    along with cookies that can be used for subsequent requests.
    """

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
            self.logger.error(f"FlareSolverr connection failed: {e}")
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

        # Always work with seconds internally, convert to ms for FlareSolverr
        effective_timeout_seconds = max_timeout or self.max_timeout
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": effective_timeout_seconds * 1000,  # Convert to ms
        }

        # Use existing session if provided
        if session_id and session_id in self._session_cache:
            cached = self._session_cache[session_id]
            payload["cookies"] = cached.get("cookies", [])

        try:
            # Request timeout should be longer than FlareSolverr's maxTimeout
            request_timeout = effective_timeout_seconds + 30  # Extra buffer for network latency

            self.logger.info(f"FlareSolverr request: {url} (timeout: {request_timeout}s)")
            response = requests.post(
                f"{self.url}/v1",
                json=payload,
                timeout=request_timeout,
            )

            # Log full response for debugging if not 200
            if response.status_code != 200:
                self.logger.error(f"FlareSolverr returned {response.status_code}: {response.text[:500]}")

            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                solution = data.get("solution", {})
                result = FlareSolverResult(
                    success=True,
                    status=solution.get("status", 200),
                    html=solution.get("response", ""),
                    cookies=solution.get("cookies", []),
                    user_agent=solution.get("userAgent", ""),
                )

                # Cache session data
                if session_id:
                    self._session_cache[session_id] = {
                        "cookies": result.cookies,
                        "user_agent": result.user_agent,
                    }

                self.logger.info(f"FlareSolverr success: {len(result.html)} bytes")
                return result
            else:
                error_msg = data.get("message", "Unknown error")
                self.logger.error(f"FlareSolverr failed: {error_msg}")
                return FlareSolverResult(
                    success=False,
                    error=error_msg,
                )

        except requests.Timeout:
            self.logger.error("FlareSolverr request timed out")
            return FlareSolverResult(
                success=False,
                error="Request timed out",
            )
        except Exception as e:
            self.logger.error(f"FlareSolverr request failed: {e}")
            return FlareSolverResult(
                success=False,
                error=str(e),
            )

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
            self.logger.error(f"Failed to create session: {e}")
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
            self.logger.warning(f"Failed to destroy session: {e}")
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
            self.logger.error(f"Failed to list sessions: {e}")
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
