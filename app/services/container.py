"""
Service container for dependency injection.

Manages creation and lifecycle of all application services.
Provides lazy-loading and singleton pattern for efficiency.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from app.config import Config
from app.orchestrator.scheduler import Scheduler
from app.services.settings_manager import get_settings, SettingsManager
from app.services.ragflow_client import RAGFlowClient
from app.services.flaresolverr_client import FlareSolverrClient
from app.services.state_tracker import StateTracker
from app.utils import get_logger

if TYPE_CHECKING:
    from app.backends import ParserBackend, ArchiveBackend, RAGBackend
    from app.services.gotenberg_client import GotenbergClient
    from app.services.tika_client import TikaClient


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

        # Backend instances (lazy-loaded)
        self._parser_backend: Optional[ParserBackend] = None
        self._archive_backend: Optional[ArchiveBackend] = None
        self._rag_backend: Optional[RAGBackend] = None

        # Service client instances (lazy-loaded)
        self._gotenberg_client: Optional[GotenbergClient] = None
        self._tika_client: Optional[TikaClient] = None

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
                raise ValueError(
                    "RAGFlow configuration missing: RAGFLOW_API_URL and RAGFLOW_API_KEY are required"
                )

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

    def _get_effective_backend(self, backend_type: str) -> str:
        """Get effective backend name from settings override or Config fallback."""
        override = self.settings.get(f"pipeline.{backend_type}_backend", "")
        if override:
            return override
        config_attr = f"{backend_type.upper()}_BACKEND"
        return getattr(Config, config_attr, "")

    def _get_effective_url(self, service: str, config_attr: str) -> str:
        """Get effective service URL from settings override or Config fallback."""
        override = self.settings.get(f"services.{service}_url", "")
        if override:
            return override
        return getattr(Config, config_attr, "")

    def _get_effective_timeout(self, service: str, config_attr: str) -> int:
        """Get effective timeout from settings override (if >0) or Config fallback."""
        override = self.settings.get(f"services.{service}_timeout", 0)
        if override and override > 0:
            return override
        return getattr(Config, config_attr, 60)

    def reset_services(self):
        """
        Reset cached service/backend instances so they pick up new settings.

        More targeted than reset() — leaves settings, scheduler, state_trackers intact.
        """
        self._parser_backend = None
        self._archive_backend = None
        self._rag_backend = None
        self._gotenberg_client = None
        self._tika_client = None
        self._ragflow_client = None
        self._flaresolverr_client = None
        self.logger.debug("Service/backend instances reset (settings preserved)")

    @property
    def parser_backend(self) -> ParserBackend:
        """
        Get parser backend (lazy-loaded singleton).

        Raises:
            ValueError: If backend name is invalid or backend is unavailable

        Returns:
            ParserBackend instance
        """
        if self._parser_backend is None:
            backend_name = self._get_effective_backend("parser")

            if backend_name == "docling":
                from app.backends.parsers.docling_parser import DoclingParser

                candidate = DoclingParser()
            elif backend_name == "docling_serve":
                from app.backends.parsers.docling_serve_parser import (
                    DoclingServeParser,
                )

                candidate = DoclingServeParser(
                    url=self._get_effective_url("docling_serve", "DOCLING_SERVE_URL"),
                    timeout=self._get_effective_timeout("docling_serve", "DOCLING_SERVE_TIMEOUT"),
                )
            elif backend_name == "mineru":
                raise ValueError(f"Parser backend '{backend_name}' not yet implemented")
            elif backend_name == "tika":
                from app.backends.parsers.tika_parser import TikaParser

                candidate = TikaParser(
                    url=self._get_effective_url("tika", "TIKA_SERVER_URL"),
                    timeout=self._get_effective_timeout("tika", "TIKA_TIMEOUT"),
                )
            else:
                raise ValueError(f"Unknown parser backend: {backend_name}")

            if not candidate.is_available():
                raise ValueError(
                    f"Parser backend '{backend_name}' not available "
                    "(check dependencies)"
                )

            self._parser_backend = candidate
            self.logger.info(f"Initialized parser backend: {backend_name}")
        return self._parser_backend

    @property
    def archive_backend(self) -> ArchiveBackend:
        """
        Get archive backend (lazy-loaded singleton).

        Raises:
            ValueError: If backend name is invalid or backend is unavailable

        Returns:
            ArchiveBackend instance
        """
        if self._archive_backend is None:
            backend_name = self._get_effective_backend("archive")

            if backend_name == "paperless":
                from app.backends.archives.paperless_adapter import (
                    PaperlessArchiveBackend,
                )

                candidate = PaperlessArchiveBackend()
            elif backend_name == "s3":
                raise ValueError(
                    f"Archive backend '{backend_name}' not yet implemented"
                )
            elif backend_name == "local":
                raise ValueError(
                    f"Archive backend '{backend_name}' not yet implemented"
                )
            else:
                raise ValueError(f"Unknown archive backend: {backend_name}")

            if not candidate.is_available():
                raise ValueError(
                    f"Archive backend '{backend_name}' not available "
                    "(check dependencies and configuration)"
                )

            self._archive_backend = candidate
            self.logger.info(f"Initialized archive backend: {backend_name}")
        return self._archive_backend

    @property
    def rag_backend(self) -> RAGBackend:
        """
        Get RAG backend (lazy-loaded singleton).

        Raises:
            ValueError: If backend name is invalid

        Returns:
            RAGBackend instance
        """
        if self._rag_backend is None:
            backend_name = self._get_effective_backend("rag")

            if backend_name == "ragflow":
                ragflow_url = self._get_effective_url("ragflow", "RAGFLOW_API_URL")
                if not ragflow_url or not Config.RAGFLOW_API_KEY:
                    raise ValueError(
                        "RAGFlow configuration missing: "
                        "RAGFLOW_API_URL and RAGFLOW_API_KEY are required"
                    )

                from app.backends.rag.ragflow_adapter import RAGFlowBackend

                candidate = RAGFlowBackend()
            elif backend_name == "anythingllm":
                anythingllm_url = self._get_effective_url("anythingllm", "ANYTHINGLLM_API_URL")
                if not anythingllm_url or not Config.ANYTHINGLLM_API_KEY:
                    raise ValueError(
                        "AnythingLLM configuration missing: "
                        "ANYTHINGLLM_API_URL and ANYTHINGLLM_API_KEY are required"
                    )

                from app.backends.rag.anythingllm_adapter import AnythingLLMBackend

                candidate = AnythingLLMBackend(
                    api_url=anythingllm_url,
                    api_key=Config.ANYTHINGLLM_API_KEY,
                    workspace_id=Config.ANYTHINGLLM_WORKSPACE_ID,
                )
            else:
                raise ValueError(f"Unknown RAG backend: {backend_name}")

            if not candidate.is_available():
                raise ValueError(
                    f"RAG backend '{backend_name}' not available "
                    "(check configuration or connectivity)"
                )

            self._rag_backend = candidate
            self.logger.info(f"Initialized RAG backend: {backend_name}")
        return self._rag_backend

    @property
    def gotenberg_client(self) -> "GotenbergClient":
        """
        Get Gotenberg client (lazy-loaded singleton).

        Returns:
            GotenbergClient instance
        """
        if self._gotenberg_client is None:
            from app.services.gotenberg_client import GotenbergClient

            self._gotenberg_client = GotenbergClient(
                url=self._get_effective_url("gotenberg", "GOTENBERG_URL"),
                timeout=self._get_effective_timeout("gotenberg", "GOTENBERG_TIMEOUT"),
            )
            self.logger.debug("Initialized GotenbergClient")
        return self._gotenberg_client

    @property
    def tika_client(self) -> "TikaClient":
        """
        Get Tika client (lazy-loaded singleton).

        Returns:
            TikaClient instance
        """
        if self._tika_client is None:
            from app.services.tika_client import TikaClient

            self._tika_client = TikaClient(
                url=self._get_effective_url("tika", "TIKA_SERVER_URL"),
                timeout=self._get_effective_timeout("tika", "TIKA_TIMEOUT"),
            )
            self.logger.debug("Initialized TikaClient")
        return self._tika_client

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
        self._parser_backend = None
        self._archive_backend = None
        self._rag_backend = None
        self._gotenberg_client = None
        self._tika_client = None
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
