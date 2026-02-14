"""
PostgreSQL persistence for scraper job metadata.

Stores job status, error, result, and timestamps so that job history
survives container restarts.  The in-memory threading.Queue remains
the dispatch mechanism — this module only handles durable state.

When DATABASE_URL is empty the store is never created.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils import get_logger


class JobStore:
    """CRUD layer over the ``scraper_jobs`` table."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self.logger = get_logger("job_store")
        self._schema_ensured = False

    # ── schema ──────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        """Create the scraper_jobs table and indexes if they don't exist."""
        if self._schema_ensured:
            return
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scraper_jobs (
                        id              TEXT PRIMARY KEY,
                        scraper_name    TEXT NOT NULL,
                        status          TEXT NOT NULL DEFAULT 'queued',
                        preview         BOOLEAN NOT NULL DEFAULT FALSE,
                        dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
                        max_pages       INTEGER,
                        error           TEXT,
                        result          JSONB,
                        started_at      TIMESTAMPTZ,
                        completed_at    TIMESTAMPTZ,
                        created_at      TIMESTAMPTZ DEFAULT NOW(),
                        updated_at      TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_scraper_jobs_status "
                    "ON scraper_jobs (status)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_scraper_jobs_created_at "
                    "ON scraper_jobs (created_at DESC)"
                )
            conn.commit()
        self._schema_ensured = True
        self.logger.debug("scraper_jobs schema ensured")

    # ── CRUD ────────────────────────────────────────────────────────

    def upsert(
        self,
        job_id: str,
        scraper_name: str,
        *,
        preview: bool = False,
        dry_run: bool = False,
        max_pages: Optional[int] = None,
        status: str = "queued",
    ) -> None:
        """Insert or update a job row."""
        self.ensure_schema()
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scraper_jobs "
                    "  (id, scraper_name, status, preview, dry_run, max_pages, "
                    "   created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  status = EXCLUDED.status, "
                    "  preview = EXCLUDED.preview, "
                    "  dry_run = EXCLUDED.dry_run, "
                    "  max_pages = EXCLUDED.max_pages, "
                    "  error = NULL, "
                    "  result = NULL, "
                    "  started_at = NULL, "
                    "  completed_at = NULL, "
                    "  updated_at = EXCLUDED.updated_at",
                    (job_id, scraper_name, status, preview, dry_run,
                     max_pages, now, now),
                )
            conn.commit()

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        result: Any = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Update status and optional fields on a job row."""
        self.ensure_schema()
        result_json = json.dumps(result) if result is not None else None
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scraper_jobs "
                    "SET status = %s, error = %s, result = %s::jsonb, "
                    "    started_at = %s, completed_at = %s, updated_at = %s "
                    "WHERE id = %s",
                    (status, error, result_json, started_at, completed_at,
                     now, job_id),
                )
            conn.commit()

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single job row as a dict, or None."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, scraper_name, status, preview, dry_run, "
                    "       max_pages, error, result, "
                    "       started_at, completed_at, created_at, updated_at "
                    "FROM scraper_jobs WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def delete(self, job_id: str) -> bool:
        """Delete a job row. Returns True if a row was deleted."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM scraper_jobs WHERE id = %s", (job_id,)
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def list_by_status(
        self, *statuses: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List jobs filtered by one or more statuses (most recent first)."""
        self.ensure_schema()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if statuses:
                    cur.execute(
                        "SELECT id, scraper_name, status, preview, dry_run, "
                        "       max_pages, error, result, "
                        "       started_at, completed_at, created_at, updated_at "
                        "FROM scraper_jobs WHERE status = ANY(%s) "
                        "ORDER BY created_at DESC LIMIT %s",
                        (list(statuses), limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, scraper_name, status, preview, dry_run, "
                        "       max_pages, error, result, "
                        "       started_at, completed_at, created_at, updated_at "
                        "FROM scraper_jobs "
                        "ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: tuple) -> dict[str, Any]:
        """Convert a DB row tuple to a dict."""
        return {
            "id": row[0],
            "scraper_name": row[1],
            "status": row[2],
            "preview": row[3],
            "dry_run": row[4],
            "max_pages": row[5],
            "error": row[6],
            "result": row[7],
            "started_at": row[8].isoformat() if row[8] else None,
            "completed_at": row[9].isoformat() if row[9] else None,
            "created_at": row[10].isoformat() if row[10] else None,
            "updated_at": row[11].isoformat() if row[11] else None,
        }
