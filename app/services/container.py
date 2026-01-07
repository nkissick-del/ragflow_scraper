"""
Service container for dependency injection.

Manages creation and lifecycle of all application services.
Provides lazy-loading and singleton pattern for efficiency.
"""

from __future__ import annotations

from typing import Optional

from app.config import Config
from app.orchestrator.scheduler import Scheduler
from app.services.settings_manager import get_settings, SettingsManager
from app.services.ragflow_client import RAGFlowClient
from app.services.flaresolverr_client import FlareSolverrClient
from app.services.state_tracker import StateTracker
from app.utils import get_logger


class ServiceContainer:
    """
    Dependency injection container for application services.

    Provides centralized access to all external services (RAGFlow, FlareSolverr, etc.)
    with consistent initialization and error handling.

    Usage:
        container = get_container()
        client = container.ragflow_client
        tracker = container.state_tracker("aemo")
    """

    _instance: Optional[ServiceContainer] = None

    def __init__(self):
        """Initialize service container (singleton)."""
        # Skip re-initialization if already initialized
        if hasattr(self, "logger"):
            return

        self.logger = get_logger("container")

        # Service instances (lazy-loaded)
        self._settings: Optional[SettingsManager] = None
        self._ragflow_client: Optional[RAGFlowClient] = None
        self._flaresolverr_client: Optional[FlareSolverrClient] = None
        self._scheduler: Optional[Scheduler] = None

        # State trackers (cached by scraper name)
        self._state_trackers: dict[str, StateTracker] = {}

    def __new__(cls) -> ServiceContainer:
        """Ensure singleton pattern (minimal implementation)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def settings(self) -> SettingsManager:
        """
        Get settings manager (lazy-loaded singleton).

        Returns:
            SettingsManager instance
        """
        if self._settings is None:
            self._settings = get_settings()
            self.logger.debug("Initialized SettingsManager")
        return self._settings

    @property
    def ragflow_client(self) -> RAGFlowClient:
        """
        Get RAGFlow client (lazy-loaded singleton).

        Raises:
            ValueError: If RAGFlow configuration is missing

        Returns:
            RAGFlowClient instance
        """
        if self._ragflow_client is None:
            if not Config.RAGFLOW_API_URL or not Config.RAGFLOW_API_KEY:
                raise ValueError("RAGFlow configuration missing: RAGFLOW_API_URL and RAGFLOW_API_KEY are required")

            self._ragflow_client = RAGFlowClient(
                api_url=Config.RAGFLOW_API_URL,
                api_key=Config.RAGFLOW_API_KEY,
                username=Config.RAGFLOW_USERNAME,
                password=Config.RAGFLOW_PASSWORD,
            )
            self.logger.debug("Initialized RAGFlowClient")
        return self._ragflow_client

    @property
    def flaresolverr_client(self) -> FlareSolverrClient:
        """
        Get FlareSolverr client (lazy-loaded singleton).

        Note: FlareSolverr is optional. Check is_configured/is_enabled before use.

        Returns:
            FlareSolverrClient instance
        """
        if self._flaresolverr_client is None:
            settings = self.settings
            self._flaresolverr_client = FlareSolverrClient(
                url=Config.FLARESOLVERR_URL,
                timeout=settings.flaresolverr_timeout,
                max_timeout=settings.flaresolverr_max_timeout,
            )
            self.logger.debug("Initialized FlareSolverrClient")
        return self._flaresolverr_client

    @property
    def scheduler(self) -> Scheduler:
        """Get scheduler singleton."""
        if self._scheduler is None:
            self._scheduler = Scheduler()
            self.logger.debug("Initialized Scheduler")
        return self._scheduler

    def state_tracker(self, scraper_name: str) -> StateTracker:
        """
        Get or create state tracker for a scraper (factory pattern).

        Args:
            scraper_name: Name of the scraper (e.g., "aemo")

        Returns:
            StateTracker instance (cached per scraper)
        """
        if scraper_name not in self._state_trackers:
            tracker = StateTracker(scraper_name)
            self._state_trackers[scraper_name] = tracker
            self.logger.debug(f"Initialized StateTracker for {scraper_name}")
        return self._state_trackers[scraper_name]

    def reset(self):
        """
        Reset all cached service instances.

        Useful for testing and debugging. Forces re-initialization on next access.
        """
        self._settings = None
        self._ragflow_client = None
        self._flaresolverr_client = None
        self._state_trackers = {}
        self._scheduler = None
        self.logger.debug("Service container reset")


# Module-level singleton accessor
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """
    Get the global service container instance.

    Returns:
        ServiceContainer singleton
    """
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container():
    """Reset the global service container (for testing)."""
    global _container
    if _container:
        _container.reset()
    _container = None
