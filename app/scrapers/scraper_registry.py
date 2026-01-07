"""
Scraper registry for auto-discovery and management of scrapers.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Optional, Type

from app.utils import get_logger

# Import will be done dynamically to avoid circular imports
_BaseScraper = None


def _get_base_scraper():
    """Lazy import of BaseScraper to avoid circular imports."""
    global _BaseScraper
    if _BaseScraper is None:
        from app.scrapers.base_scraper import BaseScraper
        _BaseScraper = BaseScraper
    return _BaseScraper


class ScraperRegistry:
    """
    Registry for auto-discovering and managing scrapers.

    Automatically scans the scrapers directory for classes that inherit
    from BaseScraper and registers them for use.
    """

    _registry: dict[str, Type["BaseScraper"]] = {}  # type: ignore[name-defined]
    _discovered: bool = False
    _logger = None

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            cls._logger = get_logger("registry")
        return cls._logger

    @classmethod
    def discover(cls) -> dict[str, Type["BaseScraper"]]:  # type: ignore[name-defined]
        """
        Discover all scrapers in the scrapers directory.

        Scans for Python modules and finds classes that inherit from BaseScraper.

        Returns:
            Dictionary mapping scraper names to scraper classes
        """
        if cls._discovered:
            return cls._registry

        logger = cls._get_logger()
        BaseScraper = _get_base_scraper()

        # Get the scrapers package directory
        scrapers_dir = Path(__file__).parent

        logger.info(f"Discovering scrapers in {scrapers_dir}")

        # Scan for Python modules
        for finder, module_name, is_pkg in pkgutil.iter_modules([str(scrapers_dir)]):
            # Skip internal modules
            if module_name.startswith("_") or module_name in ("base_scraper", "scraper_registry"):
                continue

            try:
                # Import the module
                module = importlib.import_module(f"app.scrapers.{module_name}")

                # Find classes that inherit from BaseScraper
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseScraper)
                        and obj is not BaseScraper
                        and hasattr(obj, "name")
                        and obj.name != "base"
                    ):
                        cls._registry[obj.name] = obj
                        logger.info(f"Registered scraper: {obj.name} ({name})")

            except Exception as e:
                logger.warning(f"Failed to import scraper module {module_name}: {e}")

        cls._discovered = True
        logger.info(f"Discovery complete: {len(cls._registry)} scrapers found")
        return cls._registry

    @classmethod
    def get_scraper(cls, name: str, **kwargs) -> Optional["BaseScraper"]:  # type: ignore[name-defined]
        """
        Get a scraper instance by name.

        Args:
            name: Name of the scraper
            **kwargs: Arguments to pass to the scraper constructor
                      (cloudflare_bypass_enabled is auto-injected from settings)

        Returns:
            Scraper instance, or None if not found
        """
        cls.discover()  # Ensure discovery has run

        scraper_class = cls._registry.get(name)
        if scraper_class is None:
            cls._get_logger().error(f"Scraper not found: {name}")
            return None

        # Inject per-scraper cloudflare config if not explicitly provided
        if "cloudflare_bypass_enabled" not in kwargs:
            from app.services.settings_manager import get_settings
            settings = get_settings()
            kwargs["cloudflare_bypass_enabled"] = settings.get_scraper_cloudflare_enabled(name)

        return scraper_class(**kwargs)

    @classmethod
    def get_scraper_class(cls, name: str) -> Optional[Type["BaseScraper"]]:  # type: ignore[name-defined]
        """
        Get a scraper class by name.

        Args:
            name: Name of the scraper

        Returns:
            Scraper class, or None if not found
        """
        cls.discover()
        return cls._registry.get(name)

    @classmethod
    def list_scrapers(cls) -> list[dict]:
        """
        List all registered scrapers with their metadata.

        Returns:
            List of scraper metadata dictionaries
        """
        cls.discover()
        return [
            scraper_class.get_metadata()
            for scraper_class in cls._registry.values()
        ]

    @classmethod
    def get_scraper_names(cls) -> list[str]:
        """
        Get list of all registered scraper names.

        Returns:
            List of scraper names
        """
        cls.discover()
        return list(cls._registry.keys())

    @classmethod
    def get_all_scrapers(cls) -> list[str]:
        """Alias for get_scraper_names() for backwards compatibility."""
        return cls.get_scraper_names()

    @classmethod
    def register(cls, scraper_class: Type["BaseScraper"]):  # type: ignore[name-defined]
        """
        Manually register a scraper class.

        Args:
            scraper_class: Scraper class to register
        """
        BaseScraper = _get_base_scraper()
        if not issubclass(scraper_class, BaseScraper):
            raise ValueError(f"{scraper_class} must inherit from BaseScraper")

        cls._registry[scraper_class.name] = scraper_class
        cls._get_logger().info(f"Manually registered scraper: {scraper_class.name}")

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Unregister a scraper by name.

        Args:
            name: Name of the scraper to unregister

        Returns:
            True if scraper was unregistered, False if not found
        """
        if name in cls._registry:
            del cls._registry[name]
            return True
        return False

    @classmethod
    def reset(cls):
        """Reset the registry (mainly for testing)."""
        cls._registry = {}
        cls._discovered = False
