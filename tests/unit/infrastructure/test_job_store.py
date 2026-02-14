"""Tests for app.services.job_store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.job_store import JobStore


def _make_pool():
    """Create a mock pool with connection/cursor context managers."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    return mock_pool, mock_conn, mock_cursor


class TestJobStoreSchema:
    """Test schema creation."""

    def test_ensure_schema_creates_table(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)

        store.ensure_schema()

        # Should have executed CREATE TABLE, two CREATE INDEX, and commit
        assert cur.execute.call_count >= 3
        first_sql = cur.execute.call_args_list[0][0][0]
        assert "CREATE TABLE IF NOT EXISTS scraper_jobs" in first_sql
        conn.commit.assert_called_once()

    def test_ensure_schema_idempotent(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)

        store.ensure_schema()
        initial_calls = cur.execute.call_count

        store.ensure_schema()
        # No additional SQL calls on second invocation
        assert cur.execute.call_count == initial_calls


class TestJobStoreUpsert:
    """Test upsert method."""

    def test_upsert_calls_insert(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        store.upsert("test_job", "test_scraper", preview=True, dry_run=False, max_pages=5)

        # Find the INSERT call (skip schema calls)
        insert_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "INSERT INTO scraper_jobs" in str(c[0][0])
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0][0][1]
        assert params[0] == "test_job"
        assert params[1] == "test_scraper"
        assert params[2] == "queued"
        assert params[3] is True  # preview
        assert params[4] is False  # dry_run
        assert params[5] == 5  # max_pages
        conn.commit.assert_called()


class TestJobStoreUpdateStatus:
    """Test update_status method."""

    def test_update_status_basic(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        store.update_status("test_job", "running", started_at="2024-01-01T00:00:00")

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "UPDATE scraper_jobs" in str(c[0][0])
        ]
        assert len(update_calls) == 1
        params = update_calls[0][0][1]
        assert params[0] == "running"
        assert params[3] == "2024-01-01T00:00:00"

    def test_update_status_with_result(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        result = {"docs_processed": 5, "docs_skipped": 2}
        store.update_status("test_job", "completed", result=result)

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "UPDATE scraper_jobs" in str(c[0][0])
        ]
        params = update_calls[0][0][1]
        assert params[0] == "completed"
        assert json.loads(params[2]) == result

    def test_update_status_with_error(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        store.update_status("test_job", "failed", error="Traceback: ...")

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "UPDATE scraper_jobs" in str(c[0][0])
        ]
        params = update_calls[0][0][1]
        assert params[0] == "failed"
        assert params[1] == "Traceback: ..."


class TestJobStoreGet:
    """Test get method."""

    def test_get_existing_job(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        now = datetime.now(timezone.utc)
        cur.fetchone.return_value = (
            "test_job", "test_scraper", "completed", True, False,
            5, None, {"docs": 3}, now, now, now, now,
        )

        result = store.get("test_job")

        assert result is not None
        assert result["id"] == "test_job"
        assert result["scraper_name"] == "test_scraper"
        assert result["status"] == "completed"
        assert result["preview"] is True
        assert result["max_pages"] == 5
        assert result["result"] == {"docs": 3}

    def test_get_nonexistent_returns_none(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        cur.fetchone.return_value = None

        result = store.get("nonexistent")
        assert result is None


class TestJobStoreDelete:
    """Test delete method."""

    def test_delete_existing_job(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True
        cur.rowcount = 1

        result = store.delete("test_job")

        assert result is True
        delete_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "DELETE FROM scraper_jobs" in str(c[0][0])
        ]
        assert len(delete_calls) == 1

    def test_delete_nonexistent_returns_false(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True
        cur.rowcount = 0

        result = store.delete("nonexistent")
        assert result is False


class TestJobStoreListByStatus:
    """Test list_by_status method."""

    def test_list_by_status_with_filter(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True

        now = datetime.now(timezone.utc)
        cur.fetchall.return_value = [
            ("j1", "s1", "completed", False, False, None, None, None,
             now, now, now, now),
            ("j2", "s2", "completed", False, False, None, None, None,
             now, now, now, now),
        ]

        results = store.list_by_status("completed")

        assert len(results) == 2
        assert results[0]["id"] == "j1"
        assert results[1]["id"] == "j2"

    def test_list_by_status_no_filter(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True
        cur.fetchall.return_value = []

        results = store.list_by_status()
        assert results == []

    def test_list_by_status_multiple_statuses(self):
        pool, conn, cur = _make_pool()
        store = JobStore(pool)
        store._schema_ensured = True
        cur.fetchall.return_value = []

        store.list_by_status("completed", "failed", limit=10)

        select_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "status = ANY" in str(c[0][0])
        ]
        assert len(select_calls) == 1
        params = select_calls[0][0][1]
        assert params[0] == ["completed", "failed"]
        assert params[1] == 10


class TestJobStoreRowToDict:
    """Test _row_to_dict helper."""

    def test_row_to_dict_with_timestamps(self):
        now = datetime.now(timezone.utc)
        row = (
            "id1", "scraper1", "completed", True, False,
            5, None, {"x": 1}, now, now, now, now,
        )
        result = JobStore._row_to_dict(row)

        assert result["id"] == "id1"
        assert result["started_at"] == now.isoformat()
        assert result["result"] == {"x": 1}

    def test_row_to_dict_with_none_timestamps(self):
        row = (
            "id1", "scraper1", "queued", False, False,
            None, None, None, None, None, None, None,
        )
        result = JobStore._row_to_dict(row)

        assert result["started_at"] is None
        assert result["completed_at"] is None
        assert result["max_pages"] is None
