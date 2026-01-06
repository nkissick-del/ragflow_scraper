"""
JSON schema validation and migration helpers for settings and scraper configs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from jsonschema import Draft202012Validator


def _collect_errors(validator: Draft202012Validator, data: Dict[str, Any]) -> List[str]:
    return [f"{error.message} (at {'/'.join(str(p) for p in error.absolute_path)})" for error in validator.iter_errors(data)]


SETTINGS_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["flaresolverr", "ragflow", "scraping", "scrapers", "application", "scheduler"],
    "additionalProperties": True,
    "properties": {
        "flaresolverr": {
            "type": "object",
            "required": ["enabled", "timeout", "max_timeout", "url"],
            "properties": {
                "enabled": {"type": "boolean"},
                "timeout": {"type": "number", "minimum": 1},
                "max_timeout": {"type": "number", "minimum": 1},
                "url": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "ragflow": {
            "type": "object",
            "required": [
                "default_dataset_id",
                "auto_upload",
                "auto_create_dataset",
                "default_embedding_model",
                "default_chunk_method",
                "wait_for_parsing",
                "parser_config",
                "api_url",
                "api_key",
            ],
            "properties": {
                "default_dataset_id": {"type": "string"},
                "auto_upload": {"type": "boolean"},
                "auto_create_dataset": {"type": "boolean"},
                "default_embedding_model": {"type": "string"},
                "default_chunk_method": {"type": "string"},
                "wait_for_parsing": {"type": "boolean"},
                "parser_config": {"type": "object"},
                "api_url": {"type": "string"},
                "api_key": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "scraping": {
            "type": "object",
            "required": [
                "default_request_delay",
                "default_timeout",
                "default_retry_attempts",
                "use_flaresolverr_by_default",
                "max_concurrent_downloads",
            ],
            "properties": {
                "default_request_delay": {"type": "number", "minimum": 0},
                "default_timeout": {"type": "number", "minimum": 1},
                "default_retry_attempts": {"type": "integer", "minimum": 0},
                "use_flaresolverr_by_default": {"type": "boolean"},
                "max_concurrent_downloads": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": True,
        },
        "scrapers": {"type": "object", "additionalProperties": True},
        "application": {
            "type": "object",
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "scheduler": {
            "type": "object",
            "required": ["enabled", "run_on_startup"],
            "properties": {
                "enabled": {"type": "boolean"},
                "run_on_startup": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
    },
}


SCRAPER_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["name", "description", "enabled", "base_url", "settings", "filters", "schedule"],
    "additionalProperties": True,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "enabled": {"type": "boolean"},
        "base_url": {"type": "string"},
        "settings": {
            "type": "object",
            "required": ["documents_per_page", "total_pages", "request_delay", "download_timeout", "retry_attempts"],
            "properties": {
                "documents_per_page": {"type": "integer", "minimum": 0},
                "total_pages": {"type": ["integer", "null"], "minimum": 0},
                "request_delay": {"type": "number", "minimum": 0},
                "download_timeout": {"type": "integer", "minimum": 1},
                "retry_attempts": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "filters": {
            "type": "object",
            "required": ["excluded_tags", "include_extensions", "min_file_size", "max_file_size"],
            "properties": {
                "excluded_tags": {"type": "array", "items": {"type": "string"}},
                "include_extensions": {"type": "array", "items": {"type": "string"}},
                "min_file_size": {"type": ["integer", "null"], "minimum": 0},
                "max_file_size": {"type": ["integer", "null"], "minimum": 0},
            },
            "additionalProperties": True,
        },
        "schedule": {
            "type": "object",
            "required": ["enabled", "cron", "description"],
            "properties": {
                "enabled": {"type": "boolean"},
                "cron": {"type": "string"},
                "description": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
}


DEFAULT_SETTINGS: Dict[str, Any] = {
    "flaresolverr": {"enabled": False, "timeout": 60, "max_timeout": 120, "url": ""},
    "ragflow": {
        "default_dataset_id": "",
        "auto_upload": False,
        "auto_create_dataset": True,
        "default_embedding_model": "",
        "default_chunk_method": "paper",
        "wait_for_parsing": False,
        "parser_config": {},
        "api_url": "",
        "api_key": "",
    },
    "scraping": {
        "default_request_delay": 2.0,
        "default_timeout": 60,
        "default_retry_attempts": 3,
        "use_flaresolverr_by_default": False,
        "max_concurrent_downloads": 3,
    },
    "scrapers": {},
    "application": {"name": "PDF Scraper", "version": "0.0.0"},
    "scheduler": {"enabled": False, "run_on_startup": False},
}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as f:
        return json.load(f)


def validate_settings(data: Dict[str, Any]) -> List[str]:
    validator = Draft202012Validator(SETTINGS_SCHEMA)
    return _collect_errors(validator, data)


def validate_scraper(data: Dict[str, Any]) -> List[str]:
    validator = Draft202012Validator(SCRAPER_SCHEMA)
    return _collect_errors(validator, data)


def validate_settings_file(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    data = load_json(path)
    return data, validate_settings(data)


def validate_scraper_file(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    data = load_json(path)
    return data, validate_scraper(data)


def migrate_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    migrated = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy via json round-trip
    for section, value in data.items():
        if isinstance(value, dict) and section in migrated:
            migrated[section].update(value)
        else:
            migrated[section] = value
    return migrated


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2))