"""Standardized exception hierarchy for scrapers."""

from __future__ import annotations

from typing import Any, Optional


class ScraperError(Exception):
    """Base exception for scraper-related failures."""

    def __init__(
        self,
        message: str,
        *,
        scraper: Optional[str] = None,
        recoverable: bool = True,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.scraper = scraper
        self.recoverable = recoverable
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.scraper:
            parts.append(f"[scraper={self.scraper}]")
        if self.context:
            parts.append(f"context={self.context}")
        return " ".join(parts)


class NetworkError(ScraperError):
    """Network-related failures (timeouts, DNS, HTTP errors)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", True)
        super().__init__(message, **kwargs)


class ParsingError(ScraperError):
    """Parsing/HTML/JSON failures (non-recoverable by default)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)


class DownloadError(ScraperError):
    """Download failures (recoverable unless otherwise specified)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", True)
        super().__init__(message, **kwargs)


class ConfigurationError(ScraperError):
    """Configuration or setup issues (non-recoverable by default)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)


class StateError(ScraperError):
    """State tracking or persistence failures."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)


class ValidationError(ScraperError):
    """Validation failures for configuration or metadata."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)


class ScraperAlreadyRunningError(ScraperError):
    """Raised when attempting to start a scraper that is already running."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)
