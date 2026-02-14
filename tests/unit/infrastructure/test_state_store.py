"""Tests for app.services.state_store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.state_store import StateStore


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


class TestStateStoreSchema:
    """Test schema creation."""

    def test_ensure_schema_creates_tables(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)

        store.ensure_schema()

        # Should create both tables + indexes
        assert cur.execute.call_count >= 4
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("scraper_state" in s for s in sqls)
        assert any("processed_urls" in s for s in sqls)
        conn.commit.assert_called_once()

    def test_ensure_schema_idempotent(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)

        store.ensure_schema()
        count = cur.execute.call_count
        store.ensure_schema()
        assert cur.execute.call_count == count


class TestIsProcessed:
    """Test is_processed method."""

    def test_url_exists(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = (1,)

        assert store.is_processed("scraper1", "https://example.com") is True

    def test_url_not_exists(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        assert store.is_processed("scraper1", "https://example.com") is False


class TestMarkProcessed:
    """Test mark_processed method."""

    def test_mark_processed_inserts_url(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        store.mark_processed("scraper1", "https://example.com", status="downloaded")

        insert_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "INSERT INTO processed_urls" in str(c[0][0])
        ]
        assert len(insert_calls) == 1

    def test_mark_processed_updates_stats(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        store.mark_processed("scraper1", "https://example.com", status="skipped")

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "UPDATE scraper_state" in str(c[0][0])
        ]
        # Should have at least the stats update (plus possibly ensure_scraper_row)
        assert len(update_calls) >= 1

    def test_mark_processed_with_metadata(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        meta = {"title": "Test Document"}
        store.mark_processed("scraper1", "https://example.com", metadata=meta)

        insert_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "INSERT INTO processed_urls" in str(c[0][0])
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0][0][1]
        assert json.loads(params[3]) == meta


class TestGetProcessedUrls:
    """Test get_processed_urls method."""

    def test_returns_url_list(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchall.return_value = [
            ("https://a.com",),
            ("https://b.com",),
        ]

        urls = store.get_processed_urls("scraper1")
        assert urls == ["https://a.com", "https://b.com"]

    def test_empty_returns_empty_list(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchall.return_value = []

        urls = store.get_processed_urls("scraper1")
        assert urls == []


class TestRemoveUrl:
    """Test remove_url method."""

    def test_remove_existing(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.rowcount = 1

        assert store.remove_url("scraper1", "https://example.com") is True

    def test_remove_nonexistent(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.rowcount = 0

        assert store.remove_url("scraper1", "https://example.com") is False


class TestGetStatistics:
    """Test get_statistics method."""

    def test_existing_scraper(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        stats = {
            "total_processed": 10,
            "total_downloaded": 8,
            "total_skipped": 1,
            "total_failed": 1,
        }
        cur.fetchone.return_value = (stats,)

        result = store.get_statistics("scraper1")
        assert result == stats

    def test_nonexistent_scraper_returns_zeros(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        result = store.get_statistics("scraper1")
        assert result["total_processed"] == 0


class TestCustomValues:
    """Test set_value and get_value methods."""

    def test_set_value(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        store.set_value("scraper1", "last_date", "2024-01-01")

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "jsonb_set" in str(c[0][0])
        ]
        assert len(update_calls) >= 1

    def test_get_value_found(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = ("2024-01-01",)

        result = store.get_value("scraper1", "last_date")
        assert result == "2024-01-01"

    def test_get_value_not_found_returns_default(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        result = store.get_value("scraper1", "missing", default="fallback")
        assert result == "fallback"

    def test_get_value_null_returns_default(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = (None,)

        result = store.get_value("scraper1", "missing", default="fallback")
        assert result == "fallback"


class TestClear:
    """Test clear method."""

    def test_clear_deletes_urls_and_resets_stats(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        store.clear("scraper1")

        delete_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "DELETE FROM processed_urls" in str(c[0][0])
        ]
        assert len(delete_calls) == 1

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "UPDATE scraper_state" in str(c[0][0])
        ]
        assert len(update_calls) >= 1


class TestDeleteScraper:
    """Test delete_scraper method."""

    def test_delete_scraper(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        store.delete_scraper("scraper1")

        delete_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "DELETE FROM scraper_state" in str(c[0][0])
        ]
        assert len(delete_calls) == 1
        conn.commit.assert_called()


class TestImportFromJson:
    """Test import_from_json method."""

    def test_imports_urls(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        state = {
            "scraper_name": "test",
            "created_at": "2024-01-01T00:00:00",
            "last_updated": "2024-01-02T00:00:00",
            "processed_urls": {
                "https://a.com": {
                    "processed_at": "2024-01-01T00:00:00",
                    "status": "downloaded",
                    "metadata": {"title": "A"},
                },
                "https://b.com": {
                    "processed_at": "2024-01-02T00:00:00",
                    "status": "skipped",
                    "metadata": {},
                },
            },
            "statistics": {
                "total_processed": 2,
                "total_downloaded": 1,
                "total_skipped": 1,
                "total_failed": 0,
            },
            "_custom_key": "custom_value",
        }

        count = store.import_from_json("test", state)
        assert count == 2

        # Should have inserted both URLs
        insert_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "INSERT INTO processed_urls" in str(c[0][0])
        ]
        assert len(insert_calls) == 2

    def test_imports_custom_values(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        state = {
            "scraper_name": "test",
            "created_at": "2024-01-01T00:00:00",
            "last_updated": None,
            "processed_urls": {},
            "statistics": {"total_processed": 0, "total_downloaded": 0,
                           "total_skipped": 0, "total_failed": 0},
            "_last_scrape_date": "2024-01-01",
        }

        store.import_from_json("test", state)

        update_calls = [
            c for c in cur.execute.call_args_list
            if c[0] and "custom_values" in str(c[0][0])
        ]
        assert len(update_calls) >= 1
        # custom_values param should contain the custom key
        for call in update_calls:
            if len(call[0]) > 1:
                params = call[0][1]
                custom_json = params[1] if len(params) > 1 else ""
                if "_last_scrape_date" in str(custom_json):
                    break
        else:
            pytest.fail("Custom values not included in import")


class TestGetState:
    """Test get_state method."""

    def test_get_state_nonexistent(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        state = store.get_state("nonexistent")
        assert state["scraper_name"] == "nonexistent"
        assert state["processed_urls"] == {}
        assert state["statistics"]["total_processed"] == 0

    def test_get_state_existing(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        now = datetime.now(timezone.utc)
        stats = {"total_processed": 5, "total_downloaded": 5,
                 "total_skipped": 0, "total_failed": 0}
        custom = {"_key": "val"}

        # First fetchone for scraper_state row
        # Then fetchall for processed_urls
        cur.fetchone.return_value = (now, now, stats, custom)
        cur.fetchall.return_value = [
            ("https://a.com", now, "downloaded", {}),
        ]

        state = store.get_state("test")
        assert state["scraper_name"] == "test"
        assert len(state["processed_urls"]) == 1
        assert state["statistics"]["total_processed"] == 5
        assert state["_key"] == "val"


class TestGetUrlInfo:
    """Test get_url_info method."""

    def test_existing_url(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        now = datetime.now(timezone.utc)
        cur.fetchone.return_value = (now, "downloaded", {"title": "Test"})

        result = store.get_url_info("scraper1", "https://example.com")
        assert result is not None
        assert result["status"] == "downloaded"
        assert result["metadata"]["title"] == "Test"

    def test_nonexistent_url(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        result = store.get_url_info("scraper1", "https://missing.com")
        assert result is None


class TestGetLastRunInfo:
    """Test get_last_run_info method."""

    def test_existing_scraper(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True

        now = datetime.now(timezone.utc)
        stats = {"total_processed": 5, "total_downloaded": 5,
                 "total_skipped": 0, "total_failed": 0}

        # First fetchone for scraper_state, second for count
        cur.fetchone.side_effect = [(now, stats), (42,)]

        result = store.get_last_run_info("scraper1")
        assert result is not None
        assert result["statistics"]["total_processed"] == 5
        assert result["processed_count"] == 42

    def test_nonexistent_scraper(self):
        pool, conn, cur = _make_pool()
        store = StateStore(pool)
        store._schema_ensured = True
        cur.fetchone.return_value = None

        result = store.get_last_run_info("missing")
        assert result is None
