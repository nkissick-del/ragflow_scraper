"""
Lightweight service container to centralize shared service construction.
"""

from __future__ import annotations

import threading
from typing import Optional

from app.orchestrator.scheduler import Scheduler
from app.services import FlareSolverrClient, RAGFlowClient, StateTracker
from app.services.settings_manager import SettingsManager
from app.utils import get_logger


class ServiceContainer:
    """Simple container providing shared services and factories."""

    def __init__(self):
        self.logger = get_logger("container")
        self._settings: Optional[SettingsManager] = None
        self._scheduler: Optional[Scheduler] = None
        self._init_lock = threading.Lock()

    def get_settings_manager(self) -> SettingsManager:
        if self._settings is None:
            with self._init_lock:
                if self._settings is None:
                    self._settings = SettingsManager()
        return self._settings

    def get_ragflow_client(self) -> RAGFlowClient:
        return RAGFlowClient()

    def get_state_tracker(self, scraper_name: str) -> StateTracker:
        return StateTracker(scraper_name)

    def get_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            with self._init_lock:
                if self._scheduler is None:
                    self._scheduler = Scheduler()
        return self._scheduler

    def get_flaresolverr_client(self) -> FlareSolverrClient:
        return FlareSolverrClient()


_container = ServiceContainer()


def get_container() -> ServiceContainer:
    return _container
