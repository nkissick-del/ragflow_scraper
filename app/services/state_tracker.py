"""
State tracking service for tracking processed URLs and preventing duplicates.

When a StateStore (PostgreSQL) is injected, all operations delegate to
the database.  Otherwise falls back to JSON file storage.  On first
access with a store, existing JSON state is auto-imported and the file
renamed to ``*.json.migrated``.
"""

from __future__ import annotations

import copy
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from app.config import Config
from app.utils import get_logger

if TYPE_CHECKING:
    from app.services.state_store import StateStore


class StateTracker:
    """
    State tracking for scrapers with optional PostgreSQL persistence.

    When ``state_store`` is provided, all reads/writes go to PostgreSQL.
    Otherwise uses JSON files in ``STATE_DIR``.
    """

    def __init__(
        self,
        scraper_name: str,
        state_store: Optional[StateStore] = None,
    ):
        self.scraper_name = scraper_name
        self.logger = get_logger(f"state.{scraper_name}")
        self.state_file = Config.STATE_DIR / f"{scraper_name}_state.json"
        self._lock = threading.RLock()
        self._store = state_store
        self._migrated = False

        if self._store is not None:
            self._maybe_migrate_json()
            # No need to load file state when using store
            self._state: dict[str, Any] = {}
        else:
            self._state = self._load_state()

    # ── JSON migration ──────────────────────────────────────────────

    def _maybe_migrate_json(self) -> None:
        """Auto-import existing JSON state to PostgreSQL on first access."""
        if self._migrated or self._store is None:
            return
        self._migrated = True

        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)

            count = self._store.import_from_json(self.scraper_name, state)
            # Rename to .migrated so we don't re-import
            migrated_path = self.state_file.with_suffix(".json.migrated")
            self.state_file.rename(migrated_path)
            self.logger.info(
                f"Migrated {count} URLs from JSON to PostgreSQL "
                f"(renamed to {migrated_path.name})"
            )
        except Exception as e:
            self.logger.warning(f"JSON migration failed (will retry): {e}")
            self._migrated = False  # Allow retry

    # ── file-based helpers ──────────────────────────────────────────

    def _load_state(self) -> dict:
        """Load state from file or create empty state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    self.logger.debug(
                        f"Loaded state with {len(state.get('processed_urls', {}))} processed URLs"
                    )
                    return state
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load state file, starting fresh: {e}")

        return {
            "scraper_name": self.scraper_name,
            "created_at": datetime.now().isoformat(),
            "last_updated": None,
            "processed_urls": {},
            "statistics": {
                "total_processed": 0,
                "total_downloaded": 0,
                "total_skipped": 0,
                "total_failed": 0,
            },
        }

    def save(self):
        """Save current state to file (no-op when using store)."""
        if self._store is not None:
            return
        with self._lock:
            self._state["last_updated"] = datetime.now().isoformat()
            try:
                with open(self.state_file, "w") as f:
                    json.dump(self._state, f, indent=2)
                self.logger.debug("State saved successfully")
            except IOError as e:
                self.logger.error(f"Failed to save state: {e}")

    # ── public API ──────────────────────────────────────────────────

    def is_processed(self, url: str) -> bool:
        """Check if a URL has been processed."""
        if self._store is not None:
            return self._store.is_processed(self.scraper_name, url)
        with self._lock:
            return url in self._state["processed_urls"]

    def mark_processed(
        self,
        url: str,
        metadata: Optional[dict] = None,
        status: str = "downloaded",
    ):
        """Mark a URL as processed."""
        if self._store is not None:
            self._store.mark_processed(
                self.scraper_name, url, status=status, metadata=metadata,
            )
            return

        with self._lock:
            self._state["processed_urls"][url] = {
                "processed_at": datetime.now().isoformat(),
                "status": status,
                "metadata": metadata or {},
            }
            stats = self._state["statistics"]
            stats["total_processed"] += 1
            if status == "downloaded":
                stats["total_downloaded"] += 1
            elif status == "skipped":
                stats["total_skipped"] += 1
            elif status == "failed":
                stats["total_failed"] += 1

    def get_processed_urls(self) -> list[str]:
        """Get list of all processed URLs."""
        if self._store is not None:
            return self._store.get_processed_urls(self.scraper_name)
        with self._lock:
            return list(self._state["processed_urls"].keys())

    def get_statistics(self) -> dict:
        """Get processing statistics."""
        if self._store is not None:
            return self._store.get_statistics(self.scraper_name)
        with self._lock:
            return copy.deepcopy(self._state["statistics"])

    def get_url_info(self, url: str) -> Optional[dict]:
        """Get information about a processed URL."""
        if self._store is not None:
            return self._store.get_url_info(self.scraper_name, url)
        with self._lock:
            info = self._state["processed_urls"].get(url)
            return copy.deepcopy(info) if info else None

    def clear(self):
        """Clear all state (use with caution)."""
        if self._store is not None:
            self._store.clear(self.scraper_name)
            self.logger.warning("Clearing all state (PostgreSQL)")
            return
        with self._lock:
            self.logger.warning("Clearing all state")
            self._state["processed_urls"] = {}
            self._state["statistics"] = {
                "total_processed": 0,
                "total_downloaded": 0,
                "total_skipped": 0,
                "total_failed": 0,
            }
            self.save()

    def purge(self) -> dict[str, int]:
        """Full local reset: clear state and delete downloaded/metadata files."""
        if self._store is not None:
            with self._lock:
                # Count URLs before clearing
                urls = self._store.get_processed_urls(self.scraper_name)
                urls_cleared = len(urls)
                self._store.delete_scraper(self.scraper_name)
        else:
            with self._lock:
                urls_cleared = len(self._state.get("processed_urls", {}))
                self.clear()

        files_deleted = self._delete_directory_contents(
            Config.DOWNLOAD_DIR / self.scraper_name
        )
        metadata_deleted = self._delete_directory_contents(
            Config.METADATA_DIR / self.scraper_name
        )

        self.logger.warning(
            f"Purged: {urls_cleared} URLs cleared, "
            f"{files_deleted} files deleted, "
            f"{metadata_deleted} metadata files deleted"
        )

        return {
            "urls_cleared": urls_cleared,
            "files_deleted": files_deleted,
            "metadata_deleted": metadata_deleted,
        }

    @staticmethod
    def _delete_directory_contents(directory: Path) -> int:
        """Delete all files in a directory."""
        if not directory.is_dir():
            return 0
        count = 0
        for item in directory.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    count += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    count += 1
            except OSError:
                pass
        return count

    def remove_url(self, url: str) -> bool:
        """Remove a URL from processed state."""
        if self._store is not None:
            return self._store.remove_url(self.scraper_name, url)
        with self._lock:
            if url in self._state["processed_urls"]:
                del self._state["processed_urls"][url]
                return True
            return False

    def get_last_run_info(self) -> Optional[dict]:
        """Get information about the last scraping run."""
        if self._store is not None:
            return self._store.get_last_run_info(self.scraper_name)
        with self._lock:
            return {
                "last_updated": self._state.get("last_updated"),
                "statistics": copy.deepcopy(self._state["statistics"]),
                "processed_count": len(self._state["processed_urls"]),
            }

    def get_state(self) -> dict[str, Any]:
        """Get the full state dictionary."""
        if self._store is not None:
            return self._store.get_state(self.scraper_name)
        with self._lock:
            return copy.deepcopy(self._state)

    def set_value(self, key: str, value: Any) -> None:
        """Set a custom value in the state."""
        if self._store is not None:
            self._store.set_value(self.scraper_name, key, value)
            return
        with self._lock:
            self._state[key] = value

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a custom value from the state."""
        if self._store is not None:
            return self._store.get_value(self.scraper_name, key, default)
        with self._lock:
            value = self._state.get(key, default)
            return copy.deepcopy(value)
