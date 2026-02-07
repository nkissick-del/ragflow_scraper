"""
Settings manager for runtime-configurable settings.

These settings can be modified via the web UI without restarting the application.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, cast

import jsonschema

from app.utils.errors import ValidationError

from app.config import Config, CONFIG_DIR
from app.utils import get_logger

SETTINGS_FILE = CONFIG_DIR / "settings.json"

# Default settings structure
# NOTE: Secrets and URLs come from environment variables (.env)
# This file only stores behavioral/tuning settings that can be changed via UI
DEFAULT_SETTINGS = {
    "flaresolverr": {
        # URL comes from Config.FLARESOLVERR_URL (env var)
        "enabled": False,
        "timeout": 60,
        "max_timeout": 120,
    },
    "ragflow": {
        # URL, API key, username/password come from Config (env vars)
        "default_dataset_id": "",
        "auto_upload": False,
        "auto_create_dataset": True,
        "default_embedding_model": "",  # Empty = user must select
        "default_chunk_method": "paper",
        "wait_for_parsing": True,
        "parser_config": {
            "chunk_token_num": 128,
            "layout_recognize": "DeepDOC",
        },
    },
    "scraping": {
        "default_request_delay": 2.0,
        "default_timeout": 60,
        "default_retry_attempts": 3,
        "use_flaresolverr_by_default": False,
        "max_concurrent_downloads": 3,
    },
    "scrapers": {
        # Per-scraper settings stored here dynamically
        # e.g., "aemo": {"cloudflare_enabled": True}
        # RAGFlow overrides: ragflow_dataset_id, ragflow_embedding_model, ragflow_chunk_method
    },
    "application": {
        "name": "PDF Scraper",
        "version": "0.1.0",
    },
    "scheduler": {
        "enabled": False,
        "run_on_startup": False,
    },
    "pipeline": {
        "metadata_merge_strategy": "",  # Empty = use Config.METADATA_MERGE_STRATEGY
        "filename_template": "",        # Empty = use Config.FILENAME_TEMPLATE
        "parser_backend": "",           # Empty = use Config.PARSER_BACKEND
        "archive_backend": "",          # Empty = use Config.ARCHIVE_BACKEND
        "rag_backend": "",              # Empty = use Config.RAG_BACKEND
    },
    "services": {
        "gotenberg_url": "",            # Empty = use Config.GOTENBERG_URL
        "gotenberg_timeout": 0,         # 0 = use Config.GOTENBERG_TIMEOUT
        "tika_url": "",
        "tika_timeout": 0,
        "docling_serve_url": "",
        "docling_serve_timeout": 0,
        "paperless_url": "",
        "ragflow_url": "",
        "anythingllm_url": "",
    },
}

SETTINGS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "flaresolverr": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "timeout": {"type": "integer", "minimum": 1},
                "max_timeout": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "ragflow": {
            "type": "object",
            "properties": {
                "default_dataset_id": {"type": "string"},
                "auto_upload": {"type": "boolean"},
                "auto_create_dataset": {"type": "boolean"},
                "default_embedding_model": {"type": "string"},
                "default_chunk_method": {"type": "string"},
                "wait_for_parsing": {"type": "boolean"},
                "parser_config": {
                    "type": "object",
                    "properties": {
                        "chunk_token_num": {"type": "integer", "minimum": 1},
                        "layout_recognize": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        "scraping": {
            "type": "object",
            "properties": {
                "default_request_delay": {"type": "number", "minimum": 0},
                "default_timeout": {"type": "integer", "minimum": 1},
                "default_retry_attempts": {"type": "integer", "minimum": 0},
                "use_flaresolverr_by_default": {"type": "boolean"},
                "max_concurrent_downloads": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "scrapers": {"type": "object"},
        "application": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "scheduler": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "run_on_startup": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "pipeline": {
            "type": "object",
            "properties": {
                "metadata_merge_strategy": {"type": "string"},
                "filename_template": {"type": "string"},
                "parser_backend": {"type": "string"},
                "archive_backend": {"type": "string"},
                "rag_backend": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "services": {
            "type": "object",
            "properties": {
                "gotenberg_url": {"type": "string"},
                "gotenberg_timeout": {"type": "integer", "minimum": 0, "maximum": 600},
                "tika_url": {"type": "string"},
                "tika_timeout": {"type": "integer", "minimum": 0, "maximum": 600},
                "docling_serve_url": {"type": "string"},
                "docling_serve_timeout": {"type": "integer", "minimum": 0, "maximum": 600},
                "paperless_url": {"type": "string"},
                "ragflow_url": {"type": "string"},
                "anythingllm_url": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


class SettingsManager:
    """
    Manager for runtime-configurable settings.

    Settings are stored in a JSON file and can be modified via the web UI.
    """

    _instance: Optional["SettingsManager"] = None
    _settings: dict = DEFAULT_SETTINGS.copy()

    def __new__(cls) -> "SettingsManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = get_logger("settings")
        if self._settings is None:
            self._load()

    def _load(self):
        """Load settings from file."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r") as f:
                    self._settings = json.load(f)
                if self._settings is None:
                    raise ValueError("settings JSON is null or empty")
                self._validate(cast(dict, self._settings))
                self.logger.debug("Settings loaded from file")
            except (json.JSONDecodeError, IOError, ValueError) as e:
                self.logger.warning(f"Failed to load settings: {e}")
                self._settings = DEFAULT_SETTINGS.copy()
                self.logger.debug("Using default settings")
            except jsonschema.ValidationError as e:
                self.logger.warning(f"Settings validation failed; using defaults: {e.message}")
                self._settings = DEFAULT_SETTINGS.copy()
        else:
            self._settings = DEFAULT_SETTINGS.copy()
            self._save()

        # Merge with defaults to ensure all keys exist
        self._settings = self._merge_defaults(cast(dict, self._settings or {}), DEFAULT_SETTINGS)

    def _merge_defaults(self, settings: Optional[dict], defaults: dict) -> dict:
        """Merge settings with defaults, adding missing keys."""
        result = defaults.copy()
        settings = settings or {}
        for key, value in settings.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(value, result[key])
            else:
                result[key] = value
        return result

    def _save(self):
        """Save settings to file."""
        assert self._settings is not None
        try:
            self._validate(self._settings)
        except jsonschema.ValidationError as e:
            self.logger.error(f"Refusing to save invalid settings: {e.message}")
            raise ValidationError(f"Invalid settings: {e.message}") from e
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self._settings, f, indent=2)
            self.logger.debug("Settings saved to file")
        except IOError as e:
            self.logger.error(f"Failed to save settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value by dot-notation key.

        Args:
            key: Setting key (e.g., "flaresolverr.url")
            default: Default value if key not found

        Returns:
            Setting value
        """
        assert self._settings is not None
        keys = key.split(".")
        value = self._settings
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        """
        Set a setting value by dot-notation key.

        Args:
            key: Setting key (e.g., "flaresolverr.url")
            value: Value to set
        """
        assert self._settings is not None
        keys = key.split(".")
        target = self._settings
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self._save()

    def get_section(self, section: str) -> dict:
        """
        Get all settings in a section.

        Args:
            section: Section name (e.g., "flaresolverr")

        Returns:
            Dict of settings in the section
        """
        assert self._settings is not None
        return self._settings.get(section, {}).copy()

    def update_section(self, section: str, values: dict):
        """
        Update multiple settings in a section.

        Args:
            section: Section name
            values: Dict of key-value pairs to update
        """
        assert self._settings is not None
        if section not in self._settings:
            self._settings[section] = {}
        self._settings[section].update(values)
        self._save()

    def get_all(self) -> dict:
        """Get all settings."""
        assert self._settings is not None
        return self._settings.copy()

    def reload(self):
        """Reload settings from file."""
        self._load()

    def _validate(self, settings: dict):
        """Validate settings against JSON schema."""
        jsonschema.validate(instance=(settings or {}), schema=SETTINGS_SCHEMA)

    # Convenience properties for commonly accessed settings
    @property
    def flaresolverr_enabled(self) -> bool:
        """Check if FlareSolverr is enabled (requires URL to be configured)."""
        return self.get("flaresolverr.enabled", False) and bool(Config.FLARESOLVERR_URL)

    @property
    def flaresolverr_timeout(self) -> int:
        return self.get("flaresolverr.timeout", 60)

    @property
    def flaresolverr_max_timeout(self) -> int:
        return self.get("flaresolverr.max_timeout", 120)

    @property
    def use_flaresolverr_by_default(self) -> bool:
        return self.get("scraping.use_flaresolverr_by_default", False)

    # Per-scraper settings methods
    def get_scraper_cloudflare_enabled(self, scraper_name: str) -> bool:
        """
        Check if FlareSolverr/Cloudflare bypass is enabled for a specific scraper.

        Args:
            scraper_name: Name of the scraper (e.g., "aemo")

        Returns:
            True if cloudflare bypass is enabled for this scraper
        """
        # Must have global FlareSolverr enabled and configured
        if not self.flaresolverr_enabled:
            return False
        return self.get(f"scrapers.{scraper_name}.cloudflare_enabled", False)

    def set_scraper_cloudflare_enabled(self, scraper_name: str, enabled: bool):
        """
        Set FlareSolverr/Cloudflare bypass for a specific scraper.

        Args:
            scraper_name: Name of the scraper (e.g., "aemo")
            enabled: Whether to enable cloudflare bypass
        """
        assert self._settings is not None
        # Ensure scrapers section exists
        if "scrapers" not in self._settings:
            self._settings["scrapers"] = {}
        if scraper_name not in self._settings["scrapers"]:
            self._settings["scrapers"][scraper_name] = {}
        self._settings["scrapers"][scraper_name]["cloudflare_enabled"] = enabled
        self._save()

    def get_scraper_settings(self, scraper_name: str) -> dict:
        """
        Get all settings for a specific scraper.

        Args:
            scraper_name: Name of the scraper

        Returns:
            Dict of scraper-specific settings
        """
        return self.get(f"scrapers.{scraper_name}", {})

    # RAGFlow settings methods
    @property
    def ragflow_session_configured(self) -> bool:
        """Check if RAGFlow session auth is configured."""
        # Config values may be None at import-time; coerce to bool safely.
        return bool(Config.RAGFLOW_USERNAME and Config.RAGFLOW_PASSWORD)  # type: ignore

    def get_scraper_ragflow_settings(self, scraper_name: str, scraper_defaults: Optional[dict] = None) -> dict:
        """
        Get RAGFlow settings for a scraper (with fallback to defaults).

        Args:
            scraper_name: Name of the scraper
            scraper_defaults: Optional scraper-specific defaults (default_chunk_method, default_parser)

        Returns:
            Dict with ingestion_mode, dataset_id, embedding_model, chunk_method, pdf_parser,
            pipeline_id, auto_upload, auto_create_dataset, wait_for_parsing
        """
        scraper_settings = cast(dict, self.get(f"scrapers.{scraper_name}", {}))
        defaults = cast(dict, self.get_section("ragflow"))
        scraper_defaults = dict(scraper_defaults or {})

        # Determine chunk_method default: scraper-specific > global > "naive"
        default_chunk_method = scraper_defaults.get("default_chunk_method") or defaults.get("default_chunk_method", "naive")

        # Determine pdf_parser default: scraper-specific > global > "DeepDOC"
        default_pdf_parser = scraper_defaults.get("default_parser") or defaults.get("default_parser", "DeepDOC")

        return {
            "ingestion_mode": scraper_settings.get("ragflow_ingestion_mode", "builtin"),
            "dataset_id": scraper_settings.get("ragflow_dataset_id") or defaults.get("default_dataset_id", ""),
            "embedding_model": scraper_settings.get("ragflow_embedding_model") or defaults.get("default_embedding_model", ""),
            "chunk_method": scraper_settings.get("ragflow_chunk_method") or default_chunk_method,
            "pdf_parser": scraper_settings.get("ragflow_pdf_parser") or default_pdf_parser,
            "pipeline_id": scraper_settings.get("ragflow_pipeline_id", ""),
            "auto_upload": defaults.get("auto_upload", False),
            "auto_create_dataset": defaults.get("auto_create_dataset", True),
            "wait_for_parsing": defaults.get("wait_for_parsing", True),
        }

    def set_scraper_ragflow_settings(self, scraper_name: str, settings: dict):
        """
        Set RAGFlow settings for a specific scraper.

        Args:
            scraper_name: Name of the scraper
            settings: Dict with ingestion_mode, dataset_id, embedding_model, chunk_method,
                      pdf_parser, pipeline_id
        """
        assert self._settings is not None
        # Ensure scrapers section exists
        if "scrapers" not in self._settings:
            self._settings["scrapers"] = {}
        if scraper_name not in self._settings["scrapers"]:
            self._settings["scrapers"][scraper_name] = {}

        scraper = self._settings["scrapers"][scraper_name]

        if "ingestion_mode" in settings:
            scraper["ragflow_ingestion_mode"] = settings["ingestion_mode"]
        if "dataset_id" in settings:
            scraper["ragflow_dataset_id"] = settings["dataset_id"]
        if "embedding_model" in settings:
            scraper["ragflow_embedding_model"] = settings["embedding_model"]
        if "chunk_method" in settings:
            scraper["ragflow_chunk_method"] = settings["chunk_method"]
        if "pdf_parser" in settings:
            scraper["ragflow_pdf_parser"] = settings["pdf_parser"]
        if "pipeline_id" in settings:
            scraper["ragflow_pipeline_id"] = settings["pipeline_id"]

        self._save()


# Global instance
_settings_manager: Optional[SettingsManager] = None


def get_settings() -> SettingsManager:
    """Get the global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
