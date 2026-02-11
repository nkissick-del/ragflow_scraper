"""Unit tests for Tier 2 contextual chunk enrichment in pgvector adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.config import Config
from app.services.chunking import Chunk
from app.services.llm_client import LLMResult


def _make_backend():
    """Create a VectorRAGBackend with mocked loggers to avoid /app/data/logs/ issue."""
    mock_store = MagicMock()
    mock_store.name = "pgvector"
    with patch("app.backends.rag.vector_adapter.get_logger"), \
         patch("app.services.chunking.get_logger"):
        from app.backends.rag.vector_adapter import VectorRAGBackend

        return VectorRAGBackend(
            vector_store=mock_store,
            embedding_client=MagicMock(),
        )


def _make_chunks(texts):
    return [Chunk(content=t, index=i) for i, t in enumerate(texts)]


class TestApplyContextualEnrichment:
    """Test PgVectorRAGBackend._apply_contextual_enrichment()."""

    def test_disabled_returns_raw_content(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0", "chunk 1"])

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", False), \
             patch("app.container.get_container") as mock_gc:
            mock_gc.return_value.settings.get.return_value = ""
            result = backend._apply_contextual_enrichment(chunks, "full text")

        assert result == ["chunk 0", "chunk 1"]

    def test_enabled_calls_enrichment(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0", "chunk 1"])

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_llm.chat.side_effect = [
            LLMResult(content="Context for chunk 0.", model="m", finish_reason="stop"),
            LLMResult(content="Context for chunk 1.", model="m", finish_reason="stop"),
        ]

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", True), \
             patch.object(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3), \
             patch.object(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000), \
             patch("app.container.get_container") as mock_gc:
            mock_container = MagicMock()
            mock_container.llm_client = mock_llm
            mock_container.settings.get.return_value = ""
            mock_gc.return_value = mock_container

            result = backend._apply_contextual_enrichment(chunks, "full text")

        assert len(result) == 2
        assert "Context for chunk 0." in result[0]
        assert "chunk 0" in result[0]
        assert "Context for chunk 1." in result[1]
        assert "chunk 1" in result[1]

    def test_settings_override_enables(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0"])

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_llm.chat.return_value = LLMResult(
            content="Context.", model="m", finish_reason="stop"
        )

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", False), \
             patch.object(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3), \
             patch.object(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000), \
             patch("app.container.get_container") as mock_gc:
            mock_container = MagicMock()
            mock_container.llm_client = mock_llm
            mock_container.settings.get.return_value = "true"  # Override enables
            mock_gc.return_value = mock_container

            result = backend._apply_contextual_enrichment(chunks, "full text")

        assert "Context." in result[0]

    def test_settings_override_disables(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0"])

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", True), \
             patch("app.container.get_container") as mock_gc:
            mock_gc.return_value.settings.get.return_value = "false"  # Override disables

            result = backend._apply_contextual_enrichment(chunks, "full text")

        assert result == ["chunk 0"]

    def test_llm_not_configured_returns_raw(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0"])

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = False

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", True), \
             patch.object(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3), \
             patch.object(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000), \
             patch("app.container.get_container") as mock_gc:
            mock_container = MagicMock()
            mock_container.llm_client = mock_llm
            mock_container.settings.get.return_value = ""
            mock_gc.return_value = mock_container

            result = backend._apply_contextual_enrichment(chunks, "full text")

        assert result == ["chunk 0"]

    def test_enrichment_failure_returns_raw(self):
        backend = _make_backend()
        chunks = _make_chunks(["chunk 0"])

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_llm.chat.side_effect = ConnectionError("boom")

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", True), \
             patch.object(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3), \
             patch.object(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000), \
             patch("app.container.get_container") as mock_gc:
            mock_container = MagicMock()
            mock_container.llm_client = mock_llm
            mock_container.settings.get.return_value = ""
            mock_gc.return_value = mock_container

            result = backend._apply_contextual_enrichment(chunks, "full text")

        # Should fall back gracefully
        assert len(result) == 1


class TestPgVectorIngestWithEnrichment:
    """Test that ingest_document uses enriched texts for embedding but raw for storage."""

    def test_enriched_texts_used_for_embedding(self, tmp_path):
        from app.backends.rag.vector_adapter import VectorRAGBackend

        mock_embedder = MagicMock()
        mock_embedder.is_configured.return_value = True
        mock_embedder.embed.return_value = MagicMock(
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            model="test",
            dimensions=2,
        )
        mock_store = MagicMock()
        mock_store.is_configured.return_value = True
        mock_store.test_connection.return_value = True
        mock_store.store_chunks.return_value = 2
        mock_store.name = "pgvector"

        with patch("app.backends.rag.vector_adapter.get_logger"), \
             patch("app.services.chunking.get_logger"):
            backend = VectorRAGBackend(
                vector_store=mock_store,
                embedding_client=mock_embedder,
            )

        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nchunk 0\n\nchunk 1", encoding="utf-8")

        # Mock chunker to return 2 chunks (real chunker may merge short content)
        fake_chunks = _make_chunks(["chunk 0", "chunk 1"])

        with patch.object(backend._chunker, "chunk", return_value=fake_chunks), \
             patch.object(
                 VectorRAGBackend,
                 "_apply_contextual_enrichment",
                 return_value=["enriched chunk 0", "enriched chunk 1"],
             ):
            result = backend.ingest_document(
                markdown_path=md_file,
                metadata={"source": "test"},
            )

        assert result.success

        # Embedder should receive enriched texts
        mock_embedder.embed.assert_called_once_with(["enriched chunk 0", "enriched chunk 1"])

        # Storage chunks should have RAW content (not enriched)
        store_call = mock_store.store_chunks.call_args
        stored_chunks = store_call[1]["chunks"] if "chunks" in store_call[1] else store_call[0][2]
        for sc in stored_chunks:
            assert "enriched" not in sc["content"]

    def test_enrichment_does_not_affect_storage(self, tmp_path):
        """Verify chunk.content (raw) is stored, not the enriched version."""
        from app.backends.rag.vector_adapter import VectorRAGBackend

        mock_embedder = MagicMock()
        mock_embedder.is_configured.return_value = True
        mock_embedder.embed.return_value = MagicMock(
            embeddings=[[0.1]],
            model="test",
            dimensions=1,
        )
        mock_store = MagicMock()
        mock_store.is_configured.return_value = True
        mock_store.test_connection.return_value = True
        mock_store.store_chunks.return_value = 1
        mock_store.name = "pgvector"

        with patch("app.backends.rag.vector_adapter.get_logger"), \
             patch("app.services.chunking.get_logger"):
            backend = VectorRAGBackend(
                vector_store=mock_store,
                embedding_client=mock_embedder,
            )

        md_file = tmp_path / "test.md"
        md_file.write_text("First chunk content", encoding="utf-8")

        # Mock chunker to return exactly 1 chunk with known content
        fake_chunks = _make_chunks(["First chunk content"])

        with patch.object(backend._chunker, "chunk", return_value=fake_chunks), \
             patch.object(
                 VectorRAGBackend,
                 "_apply_contextual_enrichment",
                 return_value=["ENRICHED: first chunk"],
             ):
            backend.ingest_document(
                markdown_path=md_file,
                metadata={"source": "test"},
            )

        store_call = mock_store.store_chunks.call_args
        stored_chunks = store_call[1]["chunks"] if "chunks" in store_call[1] else store_call[0][2]
        for sc in stored_chunks:
            assert "ENRICHED" not in sc["content"]
