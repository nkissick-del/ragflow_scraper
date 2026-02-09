"""Tests for PgVectorClient."""

from unittest.mock import patch, MagicMock

from app.services.pgvector_client import PgVectorClient


class TestPgVectorClientConfig:
    """Test configuration and connectivity checks."""

    def test_is_configured_true(self):
        client = PgVectorClient(database_url="postgresql://localhost/test")
        assert client.is_configured() is True

    def test_is_configured_false(self):
        client = PgVectorClient(database_url="")
        assert client.is_configured() is False

    def test_not_configured_returns_false_for_test_connection(self):
        client = PgVectorClient(database_url="")
        assert client.test_connection() is False

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")
        assert client.test_connection() is True

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_test_connection_failure(self, mock_get_pool):
        mock_get_pool.side_effect = Exception("Connection refused")
        client = PgVectorClient(database_url="postgresql://localhost/test")
        assert client.test_connection() is False


class TestPgVectorClientSchema:
    """Test schema creation."""

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_ensure_schema_creates_extension_and_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        client = PgVectorClient(database_url="postgresql://localhost/test", dimensions=768)
        client.ensure_schema()

        # Should call execute at least twice (CREATE EXTENSION + CREATE TABLE + CREATE INDEX)
        calls = mock_cursor.execute.call_args_list
        assert len(calls) >= 3

        # Verify CREATE EXTENSION
        assert "CREATE EXTENSION IF NOT EXISTS vector" in str(calls[0])

        # Verify table creation with correct dimensions
        assert "vector(768)" in str(calls[1])

        # Should commit
        mock_conn.commit.assert_called_once()

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_ensure_schema_idempotent(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        client = PgVectorClient(database_url="postgresql://localhost/test")
        client.ensure_schema()
        client.ensure_schema()  # Second call should be no-op

        # Pool should only be called once (first invocation)
        assert mock_pool.connection.call_count == 1


class TestPgVectorClientPartitions:
    """Test partition management."""

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_ensure_partition_creates_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Partition doesn't exist
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        client = PgVectorClient(database_url="postgresql://localhost/test")
        client._ensure_partition("aemo", mock_conn)

        # Should check if partition exists, create it, and create HNSW index
        assert mock_cursor.execute.call_count >= 3
        assert "aemo" in client._known_partitions

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_ensure_partition_skip_if_known(self, mock_get_pool):
        mock_conn = MagicMock()
        client = PgVectorClient(database_url="postgresql://localhost/test")
        client._known_partitions.add("aemo")
        client._ensure_partition("aemo", mock_conn)

        # Should not query the database
        mock_conn.cursor.assert_not_called()

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_ensure_partition_existing_table(self, mock_get_pool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # Partition exists
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        client = PgVectorClient(database_url="postgresql://localhost/test")
        client._ensure_partition("aemo", mock_conn)

        # Should check pg_tables + ensure index exists (CREATE INDEX IF NOT EXISTS)
        assert mock_cursor.execute.call_count == 2
        assert "aemo" in client._known_partitions


class TestPgVectorClientStore:
    """Test chunk storage."""

    @patch("app.services.pgvector_client.PgVectorClient._ensure_partition")
    @patch("app.services.pgvector_client.PgVectorClient.ensure_schema")
    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_store_chunks(self, mock_get_pool, mock_ensure_schema, mock_ensure_partition):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        client = PgVectorClient(database_url="postgresql://localhost/test")

        chunks = [
            {"content": "hello", "embedding": [0.1, 0.2], "chunk_index": 0, "metadata": {}},
            {"content": "world", "embedding": [0.3, 0.4], "chunk_index": 1, "metadata": {}},
        ]

        with patch("pgvector.psycopg.register_vector"):
            count = client.store_chunks("aemo", "test.md", chunks)

        assert count == 2
        # SAVEPOINT + DELETE + RELEASE SAVEPOINT (execute calls) + batch INSERT (executemany)
        assert mock_cursor.execute.call_count == 3  # SAVEPOINT, DELETE, RELEASE
        mock_cursor.executemany.assert_called_once()  # batch INSERT

    @patch("app.services.pgvector_client.PgVectorClient._ensure_partition")
    @patch("app.services.pgvector_client.PgVectorClient.ensure_schema")
    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
    def test_store_empty_chunks(self, mock_get_pool, mock_ensure_schema, mock_ensure_partition):
        client = PgVectorClient(database_url="postgresql://localhost/test")
        count = client.store_chunks("aemo", "test.md", [])
        assert count == 0


class TestPgVectorClientSearch:
    """Test similarity search."""

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            results = client.search([0.1, 0.2, 0.3])

        assert len(results) == 1
        assert results[0]["source"] == "aemo"
        assert results[0]["content"] == "hello world"
        assert results[0]["score"] == 0.95

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            client.search([0.1], sources=["aemo", "guardian"])

        # Verify the SQL contains source filter
        sql = mock_cursor.execute.call_args[0][0]
        assert "source = ANY" in sql

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")

        with patch("pgvector.psycopg.register_vector"):
            client.search([0.1], metadata_filter={"org": "AEMO"})

        sql = mock_cursor.execute.call_args[0][0]
        assert "metadata @>" in sql


class TestPgVectorClientStats:
    """Test stats and sources."""

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")
        sources = client.get_sources()

        assert len(sources) == 2
        assert sources[0]["source"] == "aemo"
        assert sources[0]["chunk_count"] == 100

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")
        stats = client.get_stats()

        assert stats["total_chunks"] == 150
        assert stats["total_documents"] == 10
        assert stats["total_sources"] == 2


class TestPgVectorClientClose:
    """Test connection pool cleanup."""

    def test_close_with_pool(self):
        client = PgVectorClient(database_url="postgresql://localhost/test")
        mock_pool = MagicMock()
        client._pool = mock_pool
        client._schema_ensured = True
        client._known_partitions = {"aemo"}

        client.close()

        mock_pool.close.assert_called_once()
        assert client._pool is None
        assert client._schema_ensured is False
        assert len(client._known_partitions) == 0

    def test_close_without_pool(self):
        client = PgVectorClient(database_url="postgresql://localhost/test")
        client.close()  # Should not raise


class TestPgVectorClientDelete:
    """Test document deletion."""

    @patch("app.services.pgvector_client.PgVectorClient._get_pool")
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

        client = PgVectorClient(database_url="postgresql://localhost/test")
        deleted = client.delete_document("aemo", "test.md")

        assert deleted == 5
        mock_conn.commit.assert_called_once()
