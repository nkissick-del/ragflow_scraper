"""Stack tests for pgvector client against real PostgreSQL on Unraid."""

import time
import pytest

from app.services.pgvector_client import PgVectorClient


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
