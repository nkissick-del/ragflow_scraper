"""Ntfy push notification client.

Simple HTTP POST client for sending alerts via Ntfy (https://ntfy.sh).
Non-fatal: all failures log warnings and return False.
"""

from __future__ import annotations

import requests

from app.utils import get_logger


class NtfyClient:
    """Lightweight Ntfy notification sender."""

    def __init__(self, url: str = "", topic: str = "scraper-alerts"):
        self._url = url.rstrip("/") if url else ""
        self._topic = topic
        self.logger = get_logger("ntfy")

    def is_configured(self) -> bool:
        """Check if Ntfy URL and topic are set."""
        return bool(self._url and self._topic)

    def send(
        self,
        title: str,
        message: str,
        priority: str = "default",
        tags: list[str] | None = None,
    ) -> bool:
        """Send a push notification via Ntfy.

        Args:
            title: Notification title
            message: Notification body
            priority: Priority level (min, low, default, high, urgent)
            tags: Optional list of emoji/tag strings

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            self.logger.debug("Ntfy not configured, skipping notification")
            return False

        headers: dict[str, str] = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)

        try:
            resp = requests.post(
                f"{self._url}/{self._topic}",
                data=message.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            self.logger.debug(f"Ntfy notification sent: {title}")
            return True
        except Exception as e:
            self.logger.warning(f"Ntfy notification failed (non-fatal): {e}")
            return False
