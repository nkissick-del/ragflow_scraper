"""Stack tests for pgvector client against real PostgreSQL on Unraid."""

import time
import pytest

from app.services.pgvector_client import ANYTHINGLLM_VIEW_NAME, PgVectorClient


@pytest.fixture
def pgvector_client(pgvector_url, pgvector_alive):
    """Create a PgVectorClient connected to the test database."""
    client = PgVectorClient(database_url=pgvector_url, dimensions=768)
    yield client
    client.close()


@pytest.fixture
def clean_test_source(pgvector_client):
    """Provide unique test source name and clean up after test."""
    source = f"_test_{int(time.time() * 1000)}"
    yield source
    # Cleanup: delete test data
    try:
        pgvector_client.delete_document(source, "test_doc.md")
    except Exception:
        pass


class TestPgVectorStack:
    """Test pgvector operations against real PostgreSQL."""

    def test_connection(self, pgvector_client):
        assert pgvector_client.test_connection() is True

    def test_ensure_schema(self, pgvector_client):
        pgvector_client.ensure_schema()
        # Should be idempotent
        pgvector_client.ensure_schema()

    def test_store_and_search(self, pgvector_client, clean_test_source, ollama_url, ollama_alive):
        """Store chunks with real embeddings and search."""
        from app.services.embedding_client import OllamaEmbeddingClient

        embedder = OllamaEmbeddingClient(url=ollama_url, model="nomic-embed-text")

        texts = [
            "Renewable energy targets for Australia in 2030",
            "Coal plant decommissioning in New South Wales",
            "Solar farm permits in Queensland",
        ]
        result = embedder.embed(texts)

        chunks = [
            {
                "content": text,
                "embedding": emb,
                "chunk_index": i,
                "metadata": {"title": "Test Document"},
            }
            for i, (text, emb) in enumerate(zip(texts, result.embeddings))
        ]

        pgvector_client.ensure_schema()
        count = pgvector_client.store_chunks(clean_test_source, "test_doc.md", chunks)
        assert count == 3

        # Search for similar content
        query_vec = embedder.embed_single("renewable energy policy")
        results = pgvector_client.search(
            query_embedding=query_vec,
            sources=[clean_test_source],
            limit=3,
        )

        assert len(results) > 0
        assert results[0]["source"] == clean_test_source
        assert results[0]["score"] > 0

    def test_delete_document(self, pgvector_client, clean_test_source):
        """Store then delete chunks."""
        pgvector_client.ensure_schema()

        # Create a minimal fake embedding (all zeros)
        fake_embedding = [0.0] * 768
        chunks = [
            {
                "content": "test content",
                "embedding": fake_embedding,
                "chunk_index": 0,
                "metadata": {},
            }
        ]
        pgvector_client.store_chunks(clean_test_source, "test_doc.md", chunks)
        deleted = pgvector_client.delete_document(clean_test_source, "test_doc.md")
        assert deleted == 1

    def test_get_stats(self, pgvector_client):
        pgvector_client.ensure_schema()
        stats = pgvector_client.get_stats()
        assert "total_chunks" in stats
        assert "total_documents" in stats
        assert "total_sources" in stats


class TestAnythingLLMViewStack:
    """Test AnythingLLM VIEW against real PostgreSQL."""

    def test_anythingllm_view_exists(self, pgvector_client):
        """Verify VIEW exists with correct columns after ensure_schema."""
        pgvector_client.ensure_schema()

        pool = pgvector_client._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (ANYTHINGLLM_VIEW_NAME,),
                )
                rows = cur.fetchall()

        columns = {row[0]: row[1] for row in rows}
        assert "id" in columns
        assert columns["id"] == "uuid"
        assert "namespace" in columns
        assert columns["namespace"] == "text"
        assert "embedding" in columns
        assert columns["embedding"] == "USER-DEFINED"
        assert "metadata" in columns
        assert columns["metadata"] == "jsonb"
        assert "created_at" in columns

    def test_anythingllm_view_returns_data(self, pgvector_client, clean_test_source):
        """Store chunks, query VIEW, verify metadata.text matches content."""
        pgvector_client.ensure_schema()

        fake_embedding = [0.0] * 768
        test_content = "Energy policy reform 2030"
        chunks = [
            {
                "content": test_content,
                "embedding": fake_embedding,
                "chunk_index": 0,
                "metadata": {"title": "Test"},
            }
        ]
        pgvector_client.store_chunks(clean_test_source, "test_doc.md", chunks)

        from psycopg import sql

        pool = pgvector_client._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT id, namespace, metadata FROM {} "
                            "WHERE namespace = %s").format(
                        sql.Identifier(ANYTHINGLLM_VIEW_NAME)
                    ),
                    (clean_test_source,),
                )
                rows = cur.fetchall()

        assert len(rows) >= 1
        row = rows[0]
        # id should be a UUID
        assert row[0] is not None
        # namespace should match source
        assert row[1] == clean_test_source
        # metadata should contain 'text' key with content
        meta = row[2] if isinstance(row[2], dict) else {}
        assert meta.get("text") == test_content
        assert meta.get("title") == "Test"
