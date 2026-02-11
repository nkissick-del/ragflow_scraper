"""
Service container for dependency injection.

Manages creation and lifecycle of all application services.
Provides lazy-loading and singleton pattern for efficiency.
"""

from __future__ import annotations

import threading
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
    from app.services.embedding_client import EmbeddingClient
    from app.services.pgvector_client import PgVectorClient
    from app.services.llm_client import LLMClient


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
    _instance_lock: threading.Lock = threading.Lock()
    _trackers_lock: threading.Lock = threading.Lock()

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
        self._embedding_client: Optional[EmbeddingClient] = None
        self._pgvector_client: Optional[PgVectorClient] = None
        self._llm_client: Optional[LLMClient] = None

        # State trackers (cached by scraper name)
        self._state_trackers: dict[str, StateTracker] = {}

    def __new__(cls) -> ServiceContainer:
        """Ensure singleton pattern with double-checked locking."""
        if cls._instance is None:
            with cls._instance_lock:
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
        with self._trackers_lock:
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

    def _get_config_attr(self, attr: str, default: str = "") -> str:
        """Get a Config attribute value."""
        return getattr(Config, attr, default)

    def _safe_int(self, value: str, default: int) -> int:
        """Safely convert string to int with fallback."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

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
        self._embedding_client = None
        self._pgvector_client = None
        self._llm_client = None
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
            from app.services.backend_registry import get_backend_registry

            backend_name = self._get_effective_backend("parser")
            candidate = get_backend_registry().create("parser", backend_name, self)

            if not candidate.is_available():
                raise ValueError(
                    f"Parser backend '{backend_name}' not available "
                    "(check dependencies)"
                )

            self._parser_backend = candidate
            self.logger.info(f"Initialized parser backend: {backend_name}")
        assert self._parser_backend is not None
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
            from app.services.backend_registry import get_backend_registry

            backend_name = self._get_effective_backend("archive")
            candidate = get_backend_registry().create("archive", backend_name, self)

            if not candidate.is_available():
                raise ValueError(
                    f"Archive backend '{backend_name}' not available "
                    "(check dependencies and configuration)"
                )

            self._archive_backend = candidate
            self.logger.info(f"Initialized archive backend: {backend_name}")
        assert self._archive_backend is not None
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
            from app.services.backend_registry import get_backend_registry

            backend_name = self._get_effective_backend("rag")
            candidate = get_backend_registry().create("rag", backend_name, self)

            if not candidate.is_available():
                raise ValueError(
                    f"RAG backend '{backend_name}' not available "
                    "(check configuration or connectivity)"
                )

            self._rag_backend = candidate
            self.logger.info(f"Initialized RAG backend: {backend_name}")
        assert self._rag_backend is not None
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

    @property
    def embedding_client(self) -> "EmbeddingClient":
        """
        Get embedding client (lazy-loaded singleton).

        Returns:
            EmbeddingClient instance
        """
        if self._embedding_client is None:
            from app.services.embedding_client import create_embedding_client

            self._embedding_client = create_embedding_client(
                backend=self._get_config_attr("EMBEDDING_BACKEND", "ollama"),
                model=self._get_config_attr("EMBEDDING_MODEL", "nomic-embed-text"),
                url=self._get_effective_url("embedding", "EMBEDDING_URL"),
                api_key=self._get_config_attr("EMBEDDING_API_KEY", ""),
                dimensions=self._safe_int(self._get_config_attr("EMBEDDING_DIMENSIONS", "768"), 768),
                timeout=self._get_effective_timeout("embedding", "EMBEDDING_TIMEOUT"),
            )
            self.logger.debug("Initialized EmbeddingClient")
        return self._embedding_client

    @property
    def llm_client(self) -> "LLMClient":
        """
        Get LLM client (lazy-loaded singleton).

        LLM_URL falls back to EMBEDDING_URL if not set (same Ollama server).

        Returns:
            LLMClient instance
        """
        if self._llm_client is None:
            from app.services.llm_client import create_llm_client

            # URL fallback: LLM_URL → settings override → EMBEDDING_URL
            llm_url = self._get_effective_url("llm", "LLM_URL")
            if not llm_url:
                llm_url = self._get_effective_url("embedding", "EMBEDDING_URL")

            self._llm_client = create_llm_client(
                backend=self._get_config_attr("LLM_BACKEND", "ollama"),
                model=self._get_config_attr("LLM_MODEL", "llama3.1:8b"),
                url=llm_url,
                api_key=self._get_config_attr("LLM_API_KEY", ""),
                timeout=self._get_effective_timeout("llm", "LLM_TIMEOUT"),
            )
            self.logger.debug("Initialized LLMClient")
        return self._llm_client

    @property
    def pgvector_client(self) -> "PgVectorClient":
        """
        Get pgvector client (lazy-loaded singleton).

        Returns:
            PgVectorClient instance
        """
        if self._pgvector_client is None:
            from app.services.pgvector_client import PgVectorClient

            db_url = self._get_effective_url("pgvector", "DATABASE_URL")
            if not db_url:
                raise ValueError(
                    "PgVector configuration missing: DATABASE_URL is required"
                )
            dims = self._safe_int(self._get_config_attr("EMBEDDING_DIMENSIONS", "768"), 768)
            view_name = self._get_config_attr("ANYTHINGLLM_VIEW_NAME", "anythingllm_document_view")
            self._pgvector_client = PgVectorClient(
                database_url=db_url,
                dimensions=dims,
                view_name=view_name,
            )
            self.logger.debug("Initialized PgVectorClient")
        return self._pgvector_client

    def reset(self):
        """
        Reset all cached service instances.

        Useful for testing and debugging. Forces re-initialization on next access.
        """
        with self._trackers_lock:
            self._state_trackers = {}
        self._settings = None
        self._ragflow_client = None
        self._flaresolverr_client = None
        self._scheduler = None
        self._parser_backend = None
        self._archive_backend = None
        self._rag_backend = None
        self._gotenberg_client = None
        self._tika_client = None
        self._embedding_client = None
        self._pgvector_client = None
        self._llm_client = None
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
    with ServiceContainer._instance_lock:
        if _container:
            _container.reset()
        _container = None
        ServiceContainer._instance = None
