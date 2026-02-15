"""
PostgreSQL persistence for scraper state (processed URLs, statistics).

Replaces JSON file storage from StateTracker when DATABASE_URL is set.
Auto-imports existing JSON state on first access per scraper.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils import get_logger


class StateStore:
    """CRUD layer over ``scraper_state`` and ``processed_urls`` tables."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self.logger = get_logger("state_store")
        self._schema_ensured = False

    # ── schema ──────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        if self._schema_ensured:
            return
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scraper_state (
                        scraper_name    TEXT PRIMARY KEY,
                        created_at      TIMESTAMPTZ DEFAULT NOW(),
                        last_updated    TIMESTAMPTZ,
                        statistics      JSONB NOT NULL DEFAULT
                            '{"total_processed":0,"total_downloaded":0,"total_skipped":0,"total_failed":0}'::jsonb,
                        custom_values   JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed_urls (
                        id              BIGSERIAL PRIMARY KEY,
                        scraper_name    TEXT NOT NULL
                            REFERENCES scraper_state(scraper_name) ON DELETE CASCADE,
                        url             TEXT NOT NULL,
                        processed_at    TIMESTAMPTZ DEFAULT NOW(),
                        status          TEXT NOT NULL DEFAULT 'downloaded',
                        metadata        JSONB DEFAULT '{}'::jsonb,
                        UNIQUE (scraper_name, url)
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_processed_urls_scraper "
                    "ON processed_urls (scraper_name)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_processed_urls_lookup "
                    "ON processed_urls (scraper_name, url)"
                )
            conn.commit()
        self._schema_ensured = True
        self.logger.debug("State store schema ensured")

    # ── scraper_state CRUD ──────────────────────────────────────────

    def _ensure_scraper_row(self, scraper_name: str) -> None:
        """Insert a scraper_state row if it doesn't exist."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scraper_state (scraper_name) "
                    "VALUES (%s) ON CONFLICT DO NOTHING",
                    (scraper_name,),
                )
            conn.commit()

    # ── processed URLs ──────────────────────────────────────────────

    def is_processed(self, scraper_name: str, url: str) -> bool:
        """Check if a URL has been processed."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM processed_urls "
                    "WHERE scraper_name = %s AND url = %s",
                    (scraper_name, url),
                )
                return cur.fetchone() is not None

    def mark_processed(
        self,
        scraper_name: str,
        url: str,
        *,
        status: str = "downloaded",
        metadata: Optional[dict] = None,
    ) -> None:
        """Mark a URL as processed and update statistics."""
        self._ensure_scraper_row(scraper_name)
        meta_json = json.dumps(metadata or {})
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processed_urls "
                    "  (scraper_name, url, status, metadata, processed_at) "
                    "VALUES (%s, %s, %s, %s::jsonb, %s) "
                    "ON CONFLICT (scraper_name, url) DO UPDATE SET "
                    "  status = EXCLUDED.status, "
                    "  metadata = EXCLUDED.metadata, "
                    "  processed_at = EXCLUDED.processed_at",
                    (scraper_name, url, status, meta_json, now),
                )
                # Update statistics counters
                stat_key = {
                    "downloaded": "total_downloaded",
                    "skipped": "total_skipped",
                    "failed": "total_failed",
                }.get(status, "total_downloaded")
                cur.execute(
                    "UPDATE scraper_state SET "
                    "  statistics = jsonb_set("
                    "    jsonb_set(statistics, '{total_processed}', "
                    "      (COALESCE((statistics->>'total_processed')::int, 0) + 1)::text::jsonb), "
                    f"    '{{{stat_key}}}', "
                    "    (COALESCE((statistics->>%s)::int, 0) + 1)::text::jsonb"
                    "  ), "
                    "  last_updated = %s "
                    "WHERE scraper_name = %s",
                    (stat_key, now, scraper_name),
                )
            conn.commit()

    def get_processed_urls(self, scraper_name: str) -> list[str]:
        """Get list of all processed URLs for a scraper."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT url FROM processed_urls "
                    "WHERE scraper_name = %s ORDER BY processed_at",
                    (scraper_name,),
                )
                return [row[0] for row in cur.fetchall()]

    def remove_url(self, scraper_name: str, url: str) -> bool:
        """Remove a URL from processed state."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM processed_urls "
                    "WHERE scraper_name = %s AND url = %s",
                    (scraper_name, url),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def get_url_info(
        self, scraper_name: str, url: str
    ) -> Optional[dict[str, Any]]:
        """Get processing info for a specific URL."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT processed_at, status, metadata "
                    "FROM processed_urls "
                    "WHERE scraper_name = %s AND url = %s",
                    (scraper_name, url),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "processed_at": row[0].isoformat() if row[0] else None,
            "status": row[1],
            "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}"),
        }

    # ── statistics & state ──────────────────────────────────────────

    def get_statistics(self, scraper_name: str) -> dict[str, int]:
        """Get processing statistics for a scraper."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT statistics FROM scraper_state "
                    "WHERE scraper_name = %s",
                    (scraper_name,),
                )
                row = cur.fetchone()
        if row is None:
            return {
                "total_processed": 0,
                "total_downloaded": 0,
                "total_skipped": 0,
                "total_failed": 0,
            }
        stats = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        return stats

    def get_last_run_info(self, scraper_name: str) -> Optional[dict[str, Any]]:
        """Get last run info for a scraper."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_updated, statistics FROM scraper_state "
                    "WHERE scraper_name = %s",
                    (scraper_name,),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                cur.execute(
                    "SELECT COUNT(*) FROM processed_urls "
                    "WHERE scraper_name = %s",
                    (scraper_name,),
                )
                count_row = cur.fetchone()

        stats = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
        return {
            "last_updated": row[0].isoformat() if row[0] else None,
            "statistics": stats,
            "processed_count": count_row[0] if count_row else 0,
        }

    def get_all_last_run_info(
        self, scraper_names: list[str]
    ) -> dict[str, Optional[dict[str, Any]]]:
        """Batch-fetch last run info for multiple scrapers in one connection.

        Returns a dict keyed by scraper name.  Scrapers with no state row
        are mapped to ``None``.
        """
        if not scraper_names:
            return {}
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT scraper_name, last_updated, statistics "
                    "FROM scraper_state "
                    "WHERE scraper_name = ANY(%s)",
                    (scraper_names,),
                )
                state_rows = {row[0]: row for row in cur.fetchall()}

                cur.execute(
                    "SELECT scraper_name, COUNT(*) "
                    "FROM processed_urls "
                    "WHERE scraper_name = ANY(%s) "
                    "GROUP BY scraper_name",
                    (scraper_names,),
                )
                counts = {row[0]: row[1] for row in cur.fetchall()}

        result: dict[str, Optional[dict[str, Any]]] = {}
        for name in scraper_names:
            row = state_rows.get(name)
            if row is None:
                result[name] = None
                continue
            stats = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
            result[name] = {
                "last_updated": row[1].isoformat() if row[1] else None,
                "statistics": stats,
                "processed_count": counts.get(name, 0),
            }
        return result

    # ── custom values ───────────────────────────────────────────────

    def set_value(self, scraper_name: str, key: str, value: Any) -> None:
        """Set a custom value in the scraper state."""
        self._ensure_scraper_row(scraper_name)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scraper_state SET "
                    "  custom_values = jsonb_set(custom_values, %s, %s::jsonb), "
                    "  last_updated = %s "
                    "WHERE scraper_name = %s",
                    (
                        f"{{{key}}}",
                        json.dumps(value),
                        datetime.now(timezone.utc),
                        scraper_name,
                    ),
                )
            conn.commit()

    def get_value(self, scraper_name: str, key: str, default: Any = None) -> Any:
        """Get a custom value from the scraper state."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT custom_values->%s FROM scraper_state "
                    "WHERE scraper_name = %s",
                    (key, scraper_name),
                )
                row = cur.fetchone()
        if row is None or row[0] is None:
            return default
        # JSONB returns Python types directly via psycopg
        return row[0]

    # ── lifecycle ───────────────────────────────────────────────────

    def clear(self, scraper_name: str) -> None:
        """Clear processed URLs and reset statistics for a scraper."""
        self.ensure_schema()
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM processed_urls WHERE scraper_name = %s",
                    (scraper_name,),
                )
                cur.execute(
                    "UPDATE scraper_state SET "
                    "  statistics = '{\"total_processed\":0,\"total_downloaded\":0,"
                    "\"total_skipped\":0,\"total_failed\":0}'::jsonb, "
                    "  last_updated = %s "
                    "WHERE scraper_name = %s",
                    (now, scraper_name),
                )
            conn.commit()

    def delete_scraper(self, scraper_name: str) -> None:
        """Delete all state for a scraper (CASCADE deletes processed_urls)."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM scraper_state WHERE scraper_name = %s",
                    (scraper_name,),
                )
            conn.commit()

    # ── JSON migration ──────────────────────────────────────────────

    def import_from_json(self, scraper_name: str, state: dict[str, Any]) -> int:
        """Bulk-import state from a JSON dict (StateTracker format).

        Args:
            scraper_name: Scraper name.
            state: The full state dict from JSON file.

        Returns:
            Number of URLs imported.
        """
        self._ensure_scraper_row(scraper_name)

        # Update statistics
        stats = state.get("statistics", {})
        custom_values: dict[str, Any] = {}
        # Collect custom keys (everything except standard keys)
        standard_keys = {
            "scraper_name", "created_at", "last_updated",
            "processed_urls", "statistics",
        }
        for key, value in state.items():
            if key not in standard_keys:
                custom_values[key] = value

        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scraper_state SET "
                    "  statistics = %s::jsonb, "
                    "  custom_values = %s::jsonb, "
                    "  last_updated = %s "
                    "WHERE scraper_name = %s",
                    (
                        json.dumps(stats),
                        json.dumps(custom_values),
                        datetime.now(timezone.utc),
                        scraper_name,
                    ),
                )

                # Bulk-insert processed URLs
                processed = state.get("processed_urls", {})
                count = 0
                for url, info in processed.items():
                    url_status = "downloaded"
                    url_meta = {}
                    url_time = datetime.now(timezone.utc)

                    if isinstance(info, dict):
                        url_status = info.get("status", "downloaded")
                        url_meta = info.get("metadata", {})
                        ts = info.get("processed_at")
                        if ts:
                            try:
                                url_time = datetime.fromisoformat(ts)
                            except (ValueError, TypeError):
                                pass

                    cur.execute(
                        "INSERT INTO processed_urls "
                        "  (scraper_name, url, status, metadata, processed_at) "
                        "VALUES (%s, %s, %s, %s::jsonb, %s) "
                        "ON CONFLICT (scraper_name, url) DO NOTHING",
                        (scraper_name, url, url_status,
                         json.dumps(url_meta), url_time),
                    )
                    count += 1

            conn.commit()

        self.logger.info(
            f"Imported {count} URLs for scraper '{scraper_name}' from JSON"
        )
        return count

    def get_state(self, scraper_name: str) -> dict[str, Any]:
        """Get full state dict for a scraper (mirrors StateTracker.get_state)."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT created_at, last_updated, statistics, custom_values "
                    "FROM scraper_state WHERE scraper_name = %s",
                    (scraper_name,),
                )
                row = cur.fetchone()

                if row is None:
                    return {
                        "scraper_name": scraper_name,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "last_updated": None,
                        "processed_urls": {},
                        "statistics": {
                            "total_processed": 0,
                            "total_downloaded": 0,
                            "total_skipped": 0,
                            "total_failed": 0,
                        },
                    }

                cur.execute(
                    "SELECT url, processed_at, status, metadata "
                    "FROM processed_urls WHERE scraper_name = %s",
                    (scraper_name,),
                )
                url_rows = cur.fetchall()

        processed_urls = {}
        for urow in url_rows:
            processed_urls[urow[0]] = {
                "processed_at": urow[1].isoformat() if urow[1] else None,
                "status": urow[2],
                "metadata": urow[3] if isinstance(urow[3], dict) else json.loads(urow[3] or "{}"),
            }

        stats = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
        custom = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")

        result: dict[str, Any] = {
            "scraper_name": scraper_name,
            "created_at": row[0].isoformat() if row[0] else None,
            "last_updated": row[1].isoformat() if row[1] else None,
            "processed_urls": processed_urls,
            "statistics": stats,
        }
        # Merge custom values at the top level
        result.update(custom)
        return result
