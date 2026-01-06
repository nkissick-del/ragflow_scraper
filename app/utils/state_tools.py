"""
State validation and repair helpers for local maintenance.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.config import Config
from app.utils.file_utils import get_file_hash

StateDict = Dict[str, Any]


STATE_TEMPLATE: StateDict = {
    "scraper_name": "",
    "created_at": None,
    "last_updated": None,
    "processed_urls": {},
    "statistics": {
        "total_processed": 0,
        "total_downloaded": 0,
        "total_skipped": 0,
        "total_failed": 0,
    },
}


def _fresh_state(scraper_name: str) -> StateDict:
    state = copy.deepcopy(STATE_TEMPLATE)
    state["scraper_name"] = scraper_name
    state["created_at"] = datetime.now().isoformat()
    return state


def _is_int(value: Any) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_state_dict(state: StateDict, scraper_name: str) -> List[str]:
    """Return a list of human-readable validation errors for a state dict."""
    errors: List[str] = []

    if not isinstance(state, dict):
        return ["State is not a JSON object"]

    if state.get("scraper_name") not in {scraper_name, None, ""}:
        errors.append(f"Unexpected scraper_name '{state.get('scraper_name')}' (expected '{scraper_name}')")

    processed_urls = state.get("processed_urls", {})
    if not isinstance(processed_urls, dict):
        errors.append("processed_urls must be an object mapping URLs to metadata")

    stats = state.get("statistics", {})
    if not isinstance(stats, dict):
        errors.append("statistics must be an object")
    else:
        for key in STATE_TEMPLATE["statistics"].keys():
            if not _is_int(stats.get(key, 0)):
                errors.append(f"statistics.{key} must be an integer")

    created_at = state.get("created_at")
    if created_at and not isinstance(created_at, str):
        errors.append("created_at must be an ISO string if present")
    last_updated = state.get("last_updated")
    if last_updated and not isinstance(last_updated, str):
        errors.append("last_updated must be an ISO string if present")

    return errors


def repair_state_dict(state: StateDict, scraper_name: str) -> StateDict:
    """Return a repaired state dict with required keys and sanitized counters."""
    base = _fresh_state(scraper_name)

    # Preserve created_at if reasonable
    if isinstance(state, dict):
        if isinstance(state.get("created_at"), str):
            base["created_at"] = state["created_at"]
        if isinstance(state.get("last_updated"), str):
            base["last_updated"] = state["last_updated"]

        if isinstance(state.get("processed_urls"), dict):
            base["processed_urls"] = state["processed_urls"]

        # Merge statistics, coercing to int with floor at 0
        stats = state.get("statistics", {}) if isinstance(state.get("statistics"), dict) else {}
        repaired_stats = {}
        for key, default_val in STATE_TEMPLATE["statistics"].items():
            raw_val = stats.get(key, default_val)
            try:
                repaired_stats[key] = max(int(raw_val), 0)
            except (TypeError, ValueError):
                repaired_stats[key] = default_val
        base["statistics"] = repaired_stats

        # Preserve any auxiliary keys (except ones we manage)
        for key, value in state.items():
            if key not in base:
                base[key] = value

    return base


def summarize_state(state: StateDict) -> Dict[str, Any]:
    stats = state.get("statistics", {}) if isinstance(state, dict) else {}
    processed = state.get("processed_urls", {}) if isinstance(state, dict) else {}
    return {
        "processed_count": len(processed) if isinstance(processed, dict) else 0,
        "statistics": {k: stats.get(k, 0) for k in STATE_TEMPLATE["statistics"].keys()},
    }


def load_state_file(path: Path) -> Tuple[StateDict, List[str]]:
    try:
        with path.open("r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, ["File not found"]
    except json.JSONDecodeError as exc:
        return {}, [f"JSON decode error: {exc}"]

    scraper_name = path.stem.replace("_state", "")
    errors = validate_state_dict(data, scraper_name)
    return data, errors


def scan_state_files(scraper: str | None = None) -> List[Path]:
    pattern = f"{scraper}_state.json" if scraper else "*_state.json"
    return sorted(Config.STATE_DIR.glob(pattern))


def build_state_report(path: Path, repair: bool = False, write: bool = False) -> Dict[str, Any]:
    state, errors = load_state_file(path)
    scraper_name = path.stem.replace("_state", "")
    repaired = None

    if repair:
        repaired = repair_state_dict(state, scraper_name)
        if write and repaired:
            path.write_text(json.dumps(repaired, indent=2))
            state = repaired
            errors = validate_state_dict(state, scraper_name)

    hash_value = get_file_hash(path) if path.exists() else None

    return {
        "file": str(path),
        "scraper": scraper_name,
        "errors": errors,
        "hash": hash_value,
        "summary": summarize_state(repaired or state),
        "repaired": bool(repaired) if repair else False,
    }