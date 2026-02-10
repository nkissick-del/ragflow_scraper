"""Mixin for scrapers that use FlareSolverr for rendered page fetching."""

from __future__ import annotations

import time
from typing import Any, Optional

from app.services.flaresolverr_client import FlareSolverrClient, FlareSolverResult


class FlareSolverrPageFetchMixin:
    """Mixin providing FlareSolverr-based page fetching for scrapers.

    Replaces Selenium WebDriver page loads with FlareSolverr requests.
    Scrapers using this mixin should set ``skip_webdriver = True``.

    Provides:
    - ``_init_flaresolverr_page_fetch()`` — create client + session
    - ``_cleanup_flaresolverr_page_fetch()`` — destroy session
    - ``fetch_rendered_page(url)`` — return rendered HTML
    - ``fetch_rendered_page_full(url)`` — return full FlareSolverResult
    """

    logger: Any = None

    # Set by _init_flaresolverr_page_fetch
    _fs_client: Optional[FlareSolverrClient] = None
    _fs_session_id: Optional[str] = None

    def _init_flaresolverr_page_fetch(self) -> None:
        """Create FlareSolverr client and session for page fetching."""
        from app.config import Config

        self._fs_client = FlareSolverrClient(
            url=Config.FLARESOLVERR_URL,
            timeout=getattr(Config, "FLARESOLVERR_TIMEOUT", 60),
            max_timeout=getattr(Config, "FLARESOLVERR_MAX_TIMEOUT", 120),
        )

        self._fs_session_id = f"page_fetch_{id(self)}_{int(time.time())}"
        created = self._fs_client.create_session(self._fs_session_id)
        if not created:
            if self.logger:
                self.logger.warning(
                    "FlareSolverr session creation failed, will use sessionless requests"
                )
            self._fs_session_id = None

    def _cleanup_flaresolverr_page_fetch(self) -> None:
        """Destroy FlareSolverr session if active."""
        if self._fs_client and self._fs_session_id:
            try:
                self._fs_client.destroy_session(self._fs_session_id)
            except Exception:
                pass  # Best-effort cleanup
        self._fs_client = None
        self._fs_session_id = None

    def fetch_rendered_page(self, url: str) -> str:
        """Fetch a URL via FlareSolverr and return the rendered HTML.

        Args:
            url: URL to fetch.

        Returns:
            Rendered HTML string. Empty string on failure.
        """
        result = self.fetch_rendered_page_full(url)
        return result.html if result.success else ""

    def fetch_rendered_page_full(self, url: str) -> FlareSolverResult:
        """Fetch a URL via FlareSolverr and return the full result.

        Args:
            url: URL to fetch.

        Returns:
            FlareSolverResult with HTML, final URL, cookies, etc.
        """
        if not self._fs_client:
            return FlareSolverResult(
                success=False,
                error="FlareSolverr client not initialized",
            )

        return self._fs_client.get_page(
            url,
            session_id=self._fs_session_id,
        )
