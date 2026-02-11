"""PostgreSQL + pgvector vector store backend.

Manages schema creation, chunk storage, and cosine similarity search
using partitioned tables (one partition per source).
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Optional

from app.backends.vectorstores.base import VectorStoreBackend
from app.utils import get_logger

_SOURCE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

ANYTHINGLLM_VIEW_NAME = "anythingllm_document_view"


class PgVectorVectorStore(VectorStoreBackend):
    """Vector store using PostgreSQL+pgvector for document chunk embeddings.

    Uses psycopg (v3) with connection pooling and lazy partition creation.
    Each source (e.g., scraper name) gets its own table partition with a
    dedicated HNSW index for fast approximate nearest-neighbor search.
    """

    def __init__(
        self,
        database_url: str = "",
        dimensions: int = 768,
        view_name: str = ANYTHINGLLM_VIEW_NAME,
        drop_on_dimension_mismatch: bool = False,
    ):
        if not isinstance(dimensions, int) or dimensions < 1:
            raise ValueError(f"dimensions must be a positive integer, got {dimensions!r}")
        self._database_url = database_url
        self._dimensions = dimensions
        self._view_name = view_name
        self._drop_on_mismatch = drop_on_dimension_mismatch
        self._pool = None  # Lazy-initialized ConnectionPool
        self._pool_lock = threading.Lock()
        self._schema_lock = threading.Lock()
        self._partition_lock = threading.Lock()
        self._known_partitions: set[str] = set()
        self._schema_ensured = False
        self.logger = get_logger("pgvector")

    @property
    def name(self) -> str:
        return "pgvector"

    def _get_pool(self):
        """Get or create the connection pool (lazy init, thread-safe)."""
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    if not self._database_url:
                        raise ValueError("DATABASE_URL is not configured")
                    from psycopg_pool import ConnectionPool

                    self._pool = ConnectionPool(
                        self._database_url,
                        min_size=2,
                        max_size=10,
                        open=True,
                    )
        return self._pool

    def is_configured(self) -> bool:
        """Check if the client has a database URL configured."""
        return bool(self._database_url)

    def test_connection(self) -> bool:
        """Test connectivity to PostgreSQL and verify pgvector extension."""
        if not self.is_configured():
            return False
        try:
            pool = self._get_pool()
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                    if not cur.fetchone():
                        self.logger.debug("pgvector extension not installed")
                        return False
                    return True
        except Exception as e:
            self.logger.debug(f"Connection test failed: {e}")
            return False

    def _get_existing_dimensions(self, cur: Any) -> Optional[int]:
        """Get the vector dimensions of the existing embedding column.

        Returns the dimension count, or None if the table doesn't exist.
        Uses pg_attribute.atttypmod which stores dimensions directly for
        the pgvector ``vector`` type.
        """
        cur.execute("""
            SELECT a.atttypmod
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'document_chunks'
              AND n.nspname = current_schema()
              AND a.attname = 'embedding'
              AND a.attnum > 0
        """)
        row = cur.fetchone()
        if row is None:
            return None
        return int(row[0])

    def _handle_dimension_mismatch(
        self, cur: Any, conn: Any, existing_dims: int
    ) -> None:
        """Handle a mismatch between existing and configured vector dimensions.

        If the table is empty, drops it automatically (CASCADE removes the
        AnythingLLM VIEW too).  If the table has data, behaviour depends on
        ``_drop_on_mismatch``:
        - True  -> drop anyway (user explicitly opted in)
        - False -> raise ValueError with clear instructions
        """
        cur.execute("SELECT COUNT(*) FROM document_chunks")
        count: int = cur.fetchone()[0]  # type: ignore[index]

        if count == 0:
            self.logger.warning(
                "Embedding dimension mismatch: table has vector(%d), "
                "configured for %d. Table is empty — dropping and recreating.",
                existing_dims,
                self._dimensions,
            )
            cur.execute("DROP TABLE document_chunks CASCADE")
            conn.commit()
            self._known_partitions.clear()
            return

        # Table has data
        if self._drop_on_mismatch:
            self.logger.warning(
                "Embedding dimension mismatch: table has vector(%d), "
                "configured for %d. PGVECTOR_DROP_ON_MISMATCH=true — "
                "dropping %d rows and recreating.",
                existing_dims,
                self._dimensions,
                count,
            )
            cur.execute("DROP TABLE document_chunks CASCADE")
            conn.commit()
            self._known_partitions.clear()
            return

        raise ValueError(
            f"Embedding dimension mismatch: existing table has vector({existing_dims}), "
            f"but EMBEDDING_DIMENSIONS is configured as {self._dimensions}. "
            f"The table contains {count} row(s) which are incompatible with the "
            f"new model. To drop all data and recreate, set the environment variable "
            f"PGVECTOR_DROP_ON_MISMATCH=true and restart."
        )

    def ensure_ready(self) -> None:
        """Create the pgvector extension and parent table if they don't exist.

        Idempotent and thread-safe — safe to call on every ingest.
        Detects embedding dimension mismatches and auto-recovers when safe.
        Also creates the AnythingLLM-compatible VIEW if view_name is set.
        """
        if self._schema_ensured:
            return

        with self._schema_lock:
            if self._schema_ensured:
                return

            pool = self._get_pool()
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

                    # Check for dimension mismatch on existing table
                    existing_dims = self._get_existing_dimensions(cur)
                    if existing_dims is not None and existing_dims != self._dimensions:
                        self._handle_dimension_mismatch(cur, conn, existing_dims)

                    # Dimensions is a validated int — safe for SQL composition
                    dims = self._dimensions
                    create_sql = (
                        f"CREATE TABLE IF NOT EXISTS document_chunks ("
                        f"id BIGSERIAL, "
                        f"source TEXT NOT NULL, "
                        f"filename TEXT NOT NULL, "
                        f"chunk_index INTEGER NOT NULL, "
                        f"content TEXT NOT NULL, "
                        f"embedding vector({dims}), "
                        f"metadata JSONB DEFAULT '{{}}'::jsonb, "
                        f"created_at TIMESTAMPTZ DEFAULT NOW(), "
                        f"PRIMARY KEY (source, id)"
                        f") PARTITION BY LIST (source)"
                    )
                    cur.execute(create_sql)  # type: ignore[arg-type]
                    # GIN index on metadata for filtered searches
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata
                        ON document_chunks USING GIN (metadata)
                    """)
                    # AnythingLLM-compatible VIEW
                    if self._view_name:
                        from app.backends.vectorstores.pgvector_anythingllm_view import (
                            create_anythingllm_view,
                        )

                        create_anythingllm_view(cur, self._view_name)
                conn.commit()

            self._schema_ensured = True
            self.logger.debug("Schema ensured (pgvector extension + parent table)")

    # Keep ensure_schema as an alias for backward compatibility during migration
    ensure_schema = ensure_ready

    def _ensure_partition(self, source: str, conn: Any) -> None:
        """Create a partition and HNSW index for a source if not yet known.

        Thread-safe — uses _partition_lock to prevent duplicate creation.
        """
        if source in self._known_partitions:
            return

        with self._partition_lock:
            if source in self._known_partitions:
                return

            # Validate source name — only alphanumeric, underscore, hyphen allowed
            if not _SOURCE_NAME_RE.match(source):
                raise ValueError(
                    f"Invalid source name: {source!r}. "
                    "Only alphanumeric, underscore, and hyphen allowed."
                )

            from psycopg import sql

            safe_source = source.replace("-", "_")
            partition_name = f"document_chunks_{safe_source}"
            index_name = f"idx_{safe_source}_embedding_hnsw"

            with conn.cursor() as cur:
                # Check if partition already exists
                cur.execute(
                    "SELECT 1 FROM pg_tables WHERE tablename = %s AND schemaname = current_schema()",
                    (partition_name,),
                )
                if not cur.fetchone():
                    cur.execute(
                        sql.SQL(
                            "CREATE TABLE {} PARTITION OF document_chunks "
                            "FOR VALUES IN ({})"
                        ).format(
                            sql.Identifier(partition_name),
                            sql.Literal(source),
                        ),
                    )
                    self.logger.info(f"Created partition for source '{source}'")

                # Always ensure index exists (handles partial creation scenario)
                cur.execute(
                    sql.SQL(
                        "CREATE INDEX IF NOT EXISTS {} ON {} "
                        "USING hnsw (embedding vector_cosine_ops) "
                        "WITH (m = 16, ef_construction = 64)"
                    ).format(
                        sql.Identifier(index_name),
                        sql.Identifier(partition_name),
                    )
                )
                conn.commit()

            self._known_partitions.add(source)

    def store_chunks(
        self,
        source: str,
        filename: str,
        chunks: list[dict[str, Any]],
        document_id: Optional[str] = None,
    ) -> int:
        """Store document chunks with embeddings (delete-then-insert upsert).

        Args:
            source: Source/partition name (e.g., scraper name)
            filename: Document filename
            chunks: List of dicts with keys: content, embedding, metadata, chunk_index
            document_id: Optional document ID to store in metadata

        Returns:
            Number of chunks stored
        """
        if not chunks:
            return 0

        from pgvector.psycopg import register_vector

        self.ensure_ready()
        pool = self._get_pool()

        with pool.connection() as conn:
            register_vector(conn)
            self._ensure_partition(source, conn)

            with conn.cursor() as cur:
                # Use savepoint for atomicity — if INSERT fails, DELETE is rolled back
                cur.execute("SAVEPOINT store_chunks_sp")
                try:
                    # Delete existing chunks for this document
                    cur.execute(
                        "DELETE FROM document_chunks WHERE source = %s AND filename = %s",
                        (source, filename),
                    )

                    # Validate and prepare batch insert values
                    values = []
                    for i, chunk in enumerate(chunks):
                        missing = [f for f in ("content", "embedding") if f not in chunk]
                        if missing:
                            raise ValueError(
                                f"Chunk {i} missing required field(s): {', '.join(missing)}"
                            )
                        meta = dict(chunk.get("metadata", {}))
                        if document_id:
                            meta["document_id"] = document_id
                        values.append((
                            source,
                            filename,
                            chunk.get("chunk_index", i),
                            chunk["content"],
                            chunk["embedding"],
                            json.dumps(meta),
                        ))

                    cur.executemany(
                        """
                        INSERT INTO document_chunks
                            (source, filename, chunk_index, content, embedding, metadata)
                        VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
                        """,
                        values,
                    )
                    cur.execute("RELEASE SAVEPOINT store_chunks_sp")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT store_chunks_sp")
                    raise

            conn.commit()

        self.logger.debug(f"Stored {len(chunks)} chunks for {source}/{filename}")
        return len(chunks)

    def delete_document(self, source: str, filename: str) -> int:
        """Delete all chunks for a document.

        Args:
            source: Source/partition name
            filename: Document filename

        Returns:
            Number of chunks deleted
        """
        pool = self._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM document_chunks WHERE source = %s AND filename = %s",
                    (source, filename),
                )
                deleted = cur.rowcount
            conn.commit()
        self.logger.debug(f"Deleted {deleted} chunks for {source}/{filename}")
        return deleted

    def search(
        self,
        query_embedding: list[float],
        sources: Optional[list[str]] = None,
        metadata_filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks using cosine similarity.

        Args:
            query_embedding: Query vector
            sources: Optional list of source names to filter by
            metadata_filter: Optional JSONB containment filter
            limit: Maximum results to return

        Returns:
            List of result dicts with: source, filename, chunk_index,
            content, metadata, score
        """
        if limit < 1 or limit > 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")

        pool = self._get_pool()
        conditions = []
        params: list[Any] = [query_embedding]

        if sources:
            conditions.append("source = ANY(%s)")
            params.append(sources)

        if metadata_filter:
            conditions.append("metadata @> %s::jsonb")
            params.append(json.dumps(metadata_filter))

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Append second query_embedding (for ORDER BY) then limit
        params.append(query_embedding)
        params.append(limit)

        from pgvector.psycopg import register_vector

        with pool.connection() as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT source, filename, chunk_index, content, metadata,
                           1 - (embedding <=> %s::vector) AS score
                    FROM document_chunks
                    {where_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                "source": row[0],
                "filename": row[1],
                "chunk_index": row[2],
                "content": row[3],
                "metadata": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
                "score": float(row[5]),
            })

        return results

    def get_sources(self) -> list[dict[str, Any]]:
        """List all sources with their chunk counts.

        Returns:
            List of dicts with: source, chunk_count
        """
        pool = self._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT source, COUNT(*) as chunk_count
                    FROM document_chunks
                    GROUP BY source
                    ORDER BY source
                """)
                rows = cur.fetchall()

        return [{"source": row[0], "chunk_count": row[1]} for row in rows]

    def get_stats(self) -> dict[str, Any]:
        """Get overall statistics.

        Returns:
            Dict with: total_chunks, total_documents, sources
        """
        pool = self._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM document_chunks")
                total_chunks = cur.fetchone()[0]  # type: ignore[index]

                cur.execute("SELECT COUNT(DISTINCT (source, filename)) FROM document_chunks")
                total_documents = cur.fetchone()[0]  # type: ignore[index]

                cur.execute("SELECT COUNT(DISTINCT source) FROM document_chunks")
                total_sources = cur.fetchone()[0]  # type: ignore[index]

        return {
            "total_chunks": total_chunks,
            "total_documents": total_documents,
            "total_sources": total_sources,
        }

    def get_document_chunks(self, source: str, filename: str) -> list[dict[str, Any]]:
        """Get all chunks for a specific document.

        Args:
            source: Source/partition name
            filename: Document filename

        Returns:
            List of dicts with: chunk_index, content, metadata
        """
        pool = self._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_index, content, metadata
                    FROM document_chunks
                    WHERE source = %s AND filename = %s
                    ORDER BY chunk_index
                    """,
                    (source, filename),
                )
                rows = cur.fetchall()

        return [
            {
                "chunk_index": row[0],
                "content": row[1],
                "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}"),
            }
            for row in rows
        ]

    def close(self) -> None:
        """Close the connection pool (thread-safe)."""
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
                self._schema_ensured = False
                self._known_partitions.clear()
                self.logger.debug("Connection pool closed")
