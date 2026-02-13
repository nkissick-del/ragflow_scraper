"""Tests for VectorRAGBackend adapter."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.backends.rag.vector_adapter import VectorRAGBackend


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.is_configured.return_value = True
    store.test_connection.return_value = True
    store.store_chunks.return_value = 3
    store.name = "pgvector"
    return store


@pytest.fixture
def mock_embedder():
    client = MagicMock()
    client.is_configured.return_value = True
    client.test_connection.return_value = True

    def _embed(texts):
        """Return one embedding per input text."""
        return MagicMock(
            embeddings=[[0.1, 0.2]] * len(texts),
            model="test-model",
            dimensions=2,
        )

    client.embed.side_effect = _embed
    return client


@pytest.fixture
def backend(mock_vector_store, mock_embedder):
    return VectorRAGBackend(
        vector_store=mock_vector_store,
        embedding_client=mock_embedder,
        chunking_strategy="fixed",
        chunk_max_tokens=100,
        chunk_overlap_tokens=0,
    )


class TestVectorRAGBackendConfig:
    """Test configuration and connectivity."""

    def test_name(self, backend):
        assert backend.name == "vector:pgvector"

    def test_is_configured_both(self, backend):
        assert backend.is_configured() is True

    def test_is_configured_no_store(self, mock_embedder):
        store = MagicMock()
        store.is_configured.return_value = False
        store.name = "pgvector"
        b = VectorRAGBackend(store, mock_embedder, chunk_max_tokens=100, chunk_overlap_tokens=0)
        assert b.is_configured() is False

    def test_is_configured_no_embedder(self, mock_vector_store):
        emb = MagicMock()
        emb.is_configured.return_value = False
        b = VectorRAGBackend(mock_vector_store, emb, chunk_max_tokens=100, chunk_overlap_tokens=0)
        assert b.is_configured() is False

    def test_is_available_checks_connections(self, backend, mock_vector_store, mock_embedder):
        assert backend.is_available() is True
        mock_vector_store.test_connection.assert_called()
        mock_embedder.test_connection.assert_called()

    def test_is_available_store_down(self, backend, mock_vector_store):
        mock_vector_store.test_connection.return_value = False
        assert backend.is_available() is False

    def test_is_available_embedder_down(self, backend, mock_embedder):
        mock_embedder.test_connection.return_value = False
        assert backend.is_available() is False

    def test_test_connection(self, backend):
        assert backend.test_connection() is True

    def test_test_connection_not_configured(self, mock_vector_store, mock_embedder):
        mock_vector_store.is_configured.return_value = False
        b = VectorRAGBackend(mock_vector_store, mock_embedder, chunk_max_tokens=100, chunk_overlap_tokens=0)
        assert b.test_connection() is False


class TestVectorRAGBackendIngest:
    """Test document ingestion flow."""

    def test_ingest_success(self, backend, mock_vector_store, mock_embedder, tmp_path):
        md_file = tmp_path / "test_doc.md"
        md_file.write_text("# Title\nHello world content here.")

        result = backend.ingest_document(
            content_path=md_file,
            metadata={"source": "aemo", "title": "Test"},
            collection_id="aemo",
        )

        assert result.success is True
        assert result.document_id == "test_doc.md"
        assert result.collection_id == "aemo"
        assert result.rag_name == "vector:pgvector"

        # Should have called embed and store
        mock_embedder.embed.assert_called_once()
        mock_vector_store.ensure_ready.assert_called_once()
        mock_vector_store.store_chunks.assert_called_once()

    def test_ingest_uses_collection_id_as_source(self, backend, mock_vector_store, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")

        backend.ingest_document(md_file, {"source": "other"}, collection_id="custom_source")

        assert mock_vector_store.store_chunks.call_args is not None
        assert mock_vector_store.store_chunks.call_args.kwargs.get("source") == "custom_source"

    def test_ingest_falls_back_to_metadata_source(self, backend, mock_vector_store, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")

        backend.ingest_document(md_file, {"source": "metadata_source"}, collection_id=None)

        assert mock_vector_store.store_chunks.call_args is not None
        assert mock_vector_store.store_chunks.call_args.kwargs.get("source") == "metadata_source"

    def test_ingest_default_source(self, backend, mock_vector_store, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")

        backend.ingest_document(md_file, {}, collection_id=None)

        assert mock_vector_store.store_chunks.call_args is not None
        assert mock_vector_store.store_chunks.call_args.kwargs.get("source") == "default"

    def test_ingest_file_not_found(self, backend):
        result = backend.ingest_document(
            Path("/nonexistent/file.md"), {"source": "test"},
        )
        assert result.success is False
        assert "not found" in result.error

    def test_ingest_empty_file(self, backend, tmp_path):
        md_file = tmp_path / "empty.md"
        md_file.write_text("")

        result = backend.ingest_document(md_file, {"source": "test"})
        assert result.success is False
        assert "empty" in result.error

    def test_ingest_not_configured(self, tmp_path):
        store = MagicMock()
        store.is_configured.return_value = False
        store.name = "pgvector"
        emb = MagicMock()
        emb.is_configured.return_value = False

        b = VectorRAGBackend(store, emb, chunk_max_tokens=100, chunk_overlap_tokens=0)
        md_file = tmp_path / "test.md"
        md_file.write_text("content")

        result = b.ingest_document(md_file, {})
        assert result.success is False
        assert "not configured" in result.error

    def test_ingest_embedding_error(self, backend, mock_embedder, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")
        mock_embedder.embed.side_effect = Exception("API error")

        result = backend.ingest_document(md_file, {"source": "test"})
        assert result.success is False
        assert "API error" in result.error

    def test_ingest_storage_error(self, backend, mock_vector_store, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")
        mock_vector_store.store_chunks.side_effect = Exception("DB error")

        result = backend.ingest_document(md_file, {"source": "test"})
        assert result.success is False
        assert "DB error" in result.error

    def test_ingest_passes_document_id(self, backend, mock_vector_store, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("content")

        backend.ingest_document(md_file, {"source": "test", "document_id": "42"})

        assert mock_vector_store.store_chunks.call_args is not None
        assert mock_vector_store.store_chunks.call_args.kwargs.get("document_id") == "42"
