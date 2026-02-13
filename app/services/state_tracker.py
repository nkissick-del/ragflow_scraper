"""
State tracking service for tracking processed URLs and preventing duplicates.
"""

from __future__ import annotations

import copy
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import Config
from app.utils import get_logger


class StateTracker:
    """
    File-based state tracking for scrapers.

    Tracks which URLs have been processed to prevent duplicate downloads.
    State is persisted to JSON files in the state directory.
    """

    def __init__(self, scraper_name: str):
        """
        Initialize state tracker for a scraper.

        Args:
            scraper_name: Name of the scraper (used for state file naming)
        """
        self.scraper_name = scraper_name
        self.logger = get_logger(f"state.{scraper_name}")
        self.state_file = Config.STATE_DIR / f"{scraper_name}_state.json"
        self._lock = threading.RLock()
        self._state: dict[str, Any] = self._load_state()

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
        """Save current state to file."""
        with self._lock:
            self._state["last_updated"] = datetime.now().isoformat()
            try:
                with open(self.state_file, "w") as f:
                    json.dump(self._state, f, indent=2)
                self.logger.debug("State saved successfully")
            except IOError as e:
                self.logger.error(f"Failed to save state: {e}")

    def is_processed(self, url: str) -> bool:
        """
        Check if a URL has been processed.

        Args:
            url: URL to check

        Returns:
            True if URL has been processed before
        """
        with self._lock:
            return url in self._state["processed_urls"]

    def mark_processed(
        self,
        url: str,
        metadata: Optional[dict] = None,
        status: str = "downloaded",
    ):
        """
        Mark a URL as processed.

        Args:
            url: URL that was processed
            metadata: Optional metadata about the processing
            status: Status of processing ("downloaded", "skipped", "failed")
        """
        with self._lock:
            self._state["processed_urls"][url] = {
                "processed_at": datetime.now().isoformat(),
                "status": status,
                "metadata": metadata or {},
            }

            # Update statistics
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
        with self._lock:
            return list(self._state["processed_urls"].keys())

    def get_statistics(self) -> dict:
        """Get processing statistics."""
        with self._lock:
            return copy.deepcopy(self._state["statistics"])

    def get_url_info(self, url: str) -> Optional[dict]:
        """
        Get information about a processed URL.

        Args:
            url: URL to look up

        Returns:
            Processing info dict (deep copy) or None if not processed
        """
        with self._lock:
            info = self._state["processed_urls"].get(url)
            return copy.deepcopy(info) if info else None

    def clear(self):
        """Clear all state (use with caution)."""
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
        """
        Full local reset: clear state and delete downloaded/metadata files.

        Returns:
            Dict with counts: urls_cleared, files_deleted, metadata_deleted
        """
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
        """Delete all files in a directory (non-recursive into subdirs).

        Args:
            directory: Path to the directory.

        Returns:
            Number of files deleted.
        """
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
        """
        Remove a URL from processed state.

        Args:
            url: URL to remove

        Returns:
            True if URL was removed, False if it wasn't in state
        """
        with self._lock:
            if url in self._state["processed_urls"]:
                del self._state["processed_urls"][url]
                return True
            return False

    def get_last_run_info(self) -> Optional[dict]:
        """Get information about the last scraping run."""
        with self._lock:
            return {
                "last_updated": self._state.get("last_updated"),
                "statistics": copy.deepcopy(self._state["statistics"]),
                "processed_count": len(self._state["processed_urls"]),
            }

    def get_state(self) -> dict[str, Any]:
        """
        Get the full state dictionary.

        Returns:
            Deep copy of the internal state dictionary
        """
        with self._lock:
            return copy.deepcopy(self._state)

    def set_value(self, key: str, value: Any) -> None:
        """
        Set a custom value in the state.

        Allows scrapers to store arbitrary metadata like last scrape date.

        Args:
            key: Key to store value under
            value: Value to store
        """
        with self._lock:
            self._state[key] = value

    def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a custom value from the state.

        Args:
            key: Key to retrieve
            default: Default value if key doesn't exist

        Returns:
            Deep copy of stored value or default
        """
        with self._lock:
            value = self._state.get(key, default)
            return copy.deepcopy(value)
