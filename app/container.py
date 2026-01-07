"""Compatibility wrapper exposing the global ServiceContainer singleton."""

from __future__ import annotations

from app.services.container import ServiceContainer, get_container, reset_container

__all__ = ["ServiceContainer", "get_container", "reset_container"]
