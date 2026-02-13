"""Tests for PgVectorVectorStore."""

import pytest
from unittest.mock import patch, MagicMock

from app.backends.vectorstores.pgvector_store import ANYTHINGLLM_VIEW_NAME, PgVectorVectorStore


class TestPgVectorVectorStoreConfig:
    """Test configuration and connectivity checks."""

    def test_is_configured_true(self):
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        assert store.is_configured() is True

    def test_is_configured_false(self):
        store = PgVectorVectorStore(database_url="")
        assert store.is_configured() is False

    def test_not_configured_returns_false_for_test_connection(self):
        store = PgVectorVectorStore(database_url="")
        assert store.test_connection() is False

    def test_name_property(self):
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        assert store.name == "pgvector"

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_test_connection_success(self, mock_get_pool):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        assert store.test_connection() is True

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_test_connection_failure(self, mock_get_pool):
        mock_get_pool.side_effect = Exception("Connection refused")
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        assert store.test_connection() is False


class TestPgVectorVectorStoreSchema:
    """Test schema creation."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_ready_creates_extension_and_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=768)
        store.ensure_ready()

        # CREATE EXTENSION + dimension check + CREATE TABLE + CREATE INDEX + CREATE VIEW
        calls = mock_cursor.execute.call_args_list
        assert len(calls) >= 5

        # Verify CREATE EXTENSION
        assert "CREATE EXTENSION IF NOT EXISTS vector" in str(calls[0])

        # Verify table creation with correct dimensions (after dimension check)
        assert "vector(768)" in str(calls[2])

        # Should commit
        mock_conn.commit.assert_called_once()

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_ready_idempotent(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store.ensure_ready()
        store.ensure_ready()  # Second call should be no-op

        # Pool should only be called once (first invocation)
        assert mock_pool.connection.call_count == 1

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_schema_alias(self, mock_get_pool):
        """ensure_schema should be an alias for ensure_ready."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store.ensure_schema()

        # Should have the same effect as ensure_ready
        assert store._schema_ensured is True


class TestPgVectorVectorStorePartitions:
    """Test partition management."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_partition_creates_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Partition doesn't exist
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store._ensure_partition("aemo", mock_conn)

        # Should check if partition exists, create it, and create HNSW index
        assert mock_cursor.execute.call_count >= 3
        assert "aemo" in store._known_partitions

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_partition_skip_if_known(self, mock_get_pool):
        mock_conn = MagicMock()
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store._known_partitions.add("aemo")
        store._ensure_partition("aemo", mock_conn)

        # Should not query the database
        mock_conn.cursor.assert_not_called()

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_partition_existing_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # Partition exists
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store._ensure_partition("aemo", mock_conn)

        # Should check pg_tables + ensure index exists (CREATE INDEX IF NOT EXISTS)
        assert mock_cursor.execute.call_count == 2
        assert "aemo" in store._known_partitions


class TestPgVectorVectorStoreStore:
    """Test chunk storage."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._ensure_partition")
    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore.ensure_ready")
    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_store_chunks(self, mock_get_pool, mock_ensure_ready, mock_ensure_partition):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")

        chunks = [
            {"content": "hello", "embedding": [0.1, 0.2], "chunk_index": 0, "metadata": {}},
            {"content": "world", "embedding": [0.3, 0.4], "chunk_index": 1, "metadata": {}},
        ]

        with patch("pgvector.psycopg.register_vector"):
            count = store.store_chunks("aemo", "test.md", chunks)

        assert count == 2
        # SAVEPOINT + DELETE + RELEASE SAVEPOINT (execute calls) + batch INSERT (executemany)
        assert mock_cursor.execute.call_count == 3  # SAVEPOINT, DELETE, RELEASE
        mock_cursor.executemany.assert_called_once()  # batch INSERT

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._ensure_partition")
    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore.ensure_ready")
    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_store_empty_chunks(self, mock_get_pool, mock_ensure_ready, mock_ensure_partition):
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        count = store.store_chunks("aemo", "test.md", [])
        assert count == 0


class TestPgVectorVectorStoreSearch:
    """Test similarity search."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_search_basic(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("aemo", "doc.md", 0, "hello world", {"title": "test"}, 0.95),
        ]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            results = store.search([0.1, 0.2, 0.3])

        assert len(results) == 1
        assert results[0]["source"] == "aemo"
        assert results[0]["content"] == "hello world"
        assert results[0]["score"] == 0.95

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_search_with_source_filter(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            store.search([0.1], sources=["aemo", "guardian"])

        # Verify the SQL contains source filter
        sql = mock_cursor.execute.call_args[0][0]
        assert "source = ANY" in sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_search_with_metadata_filter(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            store.search([0.1], metadata_filter={"org": "AEMO"})

        sql = mock_cursor.execute.call_args[0][0]
        assert "metadata @>" in sql


class TestPgVectorVectorStoreStats:
    """Test stats and sources."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_get_sources(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("aemo", 100),
            ("guardian", 50),
        ]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        sources = store.get_sources()

        assert len(sources) == 2
        assert sources[0]["source"] == "aemo"
        assert sources[0]["chunk_count"] == 100

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_get_stats(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(150,), (10,), (2,)]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        stats = store.get_stats()

        assert stats["total_chunks"] == 150
        assert stats["total_documents"] == 10
        assert stats["total_sources"] == 2


class TestPgVectorVectorStoreClose:
    """Test connection pool cleanup."""

    def test_close_with_pool(self):
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        mock_pool = MagicMock()
        store._pool = mock_pool
        store._schema_ensured = True
        store._known_partitions = {"aemo"}

        store.close()

        mock_pool.close.assert_called_once()
        assert store._pool is None
        assert store._schema_ensured is False
        assert len(store._known_partitions) == 0

    def test_close_without_pool(self):
        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store.close()  # Should not raise


class TestPgVectorVectorStoreDelete:
    """Test document deletion."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_delete_document(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        deleted = store.delete_document("aemo", "test.md")

        assert deleted == 5
        mock_conn.commit.assert_called_once()


class TestAnythingLLMView:
    """Test AnythingLLM VIEW creation in ensure_ready."""

    def test_view_name_constant(self):
        assert ANYTHINGLLM_VIEW_NAME == "anythingllm_document_view"

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_ensure_ready_creates_view(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=768)
        store.ensure_ready()

        calls = mock_cursor.execute.call_args_list
        # Last execute call before commit should be the VIEW creation
        view_call_sql = str(calls[-1])
        assert "CREATE OR REPLACE VIEW" in view_call_sql
        assert ANYTHINGLLM_VIEW_NAME in view_call_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_view_sql_maps_source_to_namespace(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test")
        store.ensure_ready()

        calls = mock_cursor.execute.call_args_list
        view_sql = str(calls[-1])
        assert "source AS namespace" in view_sql
        assert "jsonb_build_object" in view_sql
        assert "'text'" in view_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_custom_view_name(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(
            database_url="postgresql://localhost/test",
            view_name="my_custom_view",
        )
        store.ensure_ready()

        calls = mock_cursor.execute.call_args_list
        view_sql = str(calls[-1])
        assert "my_custom_view" in view_sql
        assert "CREATE OR REPLACE VIEW" in view_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_empty_view_name_skips_creation(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Table doesn't exist yet
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(
            database_url="postgresql://localhost/test",
            view_name="",
        )
        store.ensure_ready()

        # 4 calls: CREATE EXTENSION + dimension check + CREATE TABLE + CREATE INDEX (no VIEW)
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 4
        for call in calls:
            assert "CREATE OR REPLACE VIEW" not in str(call)


class TestDimensionMismatch:
    """Test embedding dimension mismatch detection and recovery."""

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_no_mismatch_when_dims_match(self, mock_get_pool):
        """Table exists with matching dimensions — no drop, normal flow."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (768,)  # Existing dims match
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=768)
        store.ensure_ready()

        # No DROP TABLE should be called
        all_sql = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "DROP TABLE" not in all_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_mismatch_empty_table_auto_drops(self, mock_get_pool):
        """Dimension mismatch + empty table -> auto-drop and recreate."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(768,), (0,)]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=4096)
        store.ensure_ready()

        all_sql = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "DROP TABLE document_chunks CASCADE" in all_sql
        assert "vector(4096)" in all_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_mismatch_with_data_raises_error(self, mock_get_pool):
        """Dimension mismatch + data in table -> raises ValueError."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(768,), (500,)]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=4096)

        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            store.ensure_ready()

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_mismatch_with_data_drops_when_opted_in(self, mock_get_pool):
        """Dimension mismatch + data + drop_on_mismatch=True -> drops and recreates."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(768,), (500,)]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(
            database_url="postgresql://localhost/test",
            dimensions=4096,
            drop_on_dimension_mismatch=True,
        )
        store.ensure_ready()

        all_sql = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "DROP TABLE document_chunks CASCADE" in all_sql
        assert "vector(4096)" in all_sql

    @patch("app.backends.vectorstores.pgvector_store.PgVectorVectorStore._get_pool")
    def test_mismatch_error_message_includes_instructions(self, mock_get_pool):
        """Error message should tell user exactly what to do."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(768,), (42,)]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        store = PgVectorVectorStore(database_url="postgresql://localhost/test", dimensions=4096)

        with pytest.raises(ValueError, match="PGVECTOR_DROP_ON_MISMATCH=true") as exc_info:
            store.ensure_ready()

        msg = str(exc_info.value)
        assert "vector(768)" in msg
        assert "4096" in msg
        assert "42 row(s)" in msg
