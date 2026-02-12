"""Generic vector store RAG backend adapter.

Chunks markdown, generates embeddings, and stores via any VectorStoreBackend.
Replaces the pgvector-specific adapter with a store-agnostic version.
"""

from pathlib import Path
from typing import Any, Optional

from app.backends.rag.base import RAGBackend, RAGResult
from app.backends.vectorstores.base import VectorStoreBackend
from app.utils import get_logger


class VectorRAGBackend(RAGBackend):
    """RAG backend using any VectorStoreBackend for chunking/embedding/retrieval."""

    def __init__(
        self,
        vector_store: VectorStoreBackend,
        embedding_client: Any,
        chunking_strategy: str = "hybrid",
        chunk_max_tokens: int = 512,
        chunk_overlap_tokens: int = 64,
        docling_serve_url: str = "",
        docling_serve_timeout: int = 120,
    ):
        self._store = vector_store
        self._embedder = embedding_client

        from app.services.chunking import create_chunker
        self._chunker = create_chunker(
            strategy=chunking_strategy,
            max_tokens=chunk_max_tokens,
            overlap_tokens=chunk_overlap_tokens,
            docling_serve_url=docling_serve_url,
            docling_serve_timeout=docling_serve_timeout,
        )
        self.logger = get_logger("backends.rag.vector")

    @property
    def name(self) -> str:
        return f"vector:{self._store.name}"

    def is_configured(self) -> bool:
        return self._store.is_configured() and self._embedder.is_configured()

    def is_available(self) -> bool:
        """Override: test both connections, not just is_configured()."""
        if not self.is_configured():
            return False
        try:
            return self._store.test_connection() and self._embedder.test_connection()
        except Exception:
            return False

    def test_connection(self) -> bool:
        if not self.is_configured():
            return False
        try:
            store_ok = self._store.test_connection()
            emb_ok = self._embedder.test_connection()
            return store_ok and emb_ok
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    def ingest_document(
        self,
        markdown_path: Path,
        metadata: dict[str, Any],
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        if not self.is_configured():
            return RAGResult(
                success=False,
                error=f"{self.name} backend not configured (missing vector store or embedding URL)",
                rag_name=self.name,
            )

        if not markdown_path.exists():
            return RAGResult(
                success=False,
                error=f"Markdown file not found: {markdown_path}",
                rag_name=self.name,
            )

        try:
            # Determine source (partition key)
            source = collection_id or metadata.get("source", "default")
            filename = markdown_path.name

            # Read markdown
            text = markdown_path.read_text(encoding="utf-8")
            if not text.strip():
                return RAGResult(
                    success=False,
                    error=f"Markdown file is empty: {markdown_path}",
                    rag_name=self.name,
                )

            # Chunk
            chunks = self._chunker.chunk(text, metadata)
            if not chunks:
                return RAGResult(
                    success=False,
                    error=f"No chunks produced from: {markdown_path}",
                    rag_name=self.name,
                )

            # Contextual enrichment (optional — enriched text for embedding only)
            texts = self._apply_contextual_enrichment(chunks, text)

            # Embed
            embedding_result = self._embedder.embed(texts)

            if not embedding_result.embeddings:
                return RAGResult(
                    success=False,
                    error=f"Embedding failed for: {markdown_path}",
                    rag_name=self.name,
                )
            if len(embedding_result.embeddings) != len(chunks):
                return RAGResult(
                    success=False,
                    error=(
                        f"Embedding count mismatch: got {len(embedding_result.embeddings)}, "
                        f"expected {len(chunks)}"
                    ),
                    rag_name=self.name,
                )

            # Prepare chunks for storage
            storage_chunks = []
            for chunk, embedding in zip(chunks, embedding_result.embeddings):
                storage_chunks.append({
                    "content": chunk.content,
                    "embedding": embedding,
                    "chunk_index": chunk.index,
                    "metadata": chunk.metadata,
                })

            # Store
            self._store.ensure_ready()
            document_id = metadata.get("document_id")
            count = self._store.store_chunks(
                source=source,
                filename=filename,
                chunks=storage_chunks,
                document_id=str(document_id) if document_id else None,
            )

            self.logger.info(
                f"Ingested {count} chunks for {source}/{filename} "
                f"(model={embedding_result.model}, dims={embedding_result.dimensions})"
            )

            return RAGResult(
                success=True,
                document_id=str(document_id) if document_id else filename,
                collection_id=source,
                rag_name=self.name,
            )

        except Exception as e:
            error_msg = f"{self.name} ingestion failed: {e}"
            self.logger.error(error_msg)
            return RAGResult(success=False, error=error_msg, rag_name=self.name)

    def _apply_contextual_enrichment(
        self,
        chunks: list,
        full_text: str,
    ) -> list[str]:
        """Apply contextual enrichment to chunks if enabled.

        Returns enriched text for embedding. Raw chunk.content is still
        stored in the database (line 129 in store loop).

        Args:
            chunks: List of Chunk objects
            full_text: Full document text

        Returns:
            List of text strings for embedding
        """
        from app.config import Config

        enabled = getattr(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", False)

        # Check settings override
        try:
            from app.container import get_container
            override = get_container().settings.get(
                "pipeline.contextual_enrichment_enabled", ""
            )
            if override != "":
                enabled = override.lower() == "true"
        except Exception:
            pass

        if not enabled:
            return [c.content for c in chunks]

        try:
            from app.container import get_container
            from app.services.document_enrichment import DocumentEnrichmentService

            container = get_container()
            llm_client = container.llm_client
            if not llm_client.is_configured():
                self.logger.debug("LLM client not configured, skipping contextual enrichment")
                return [c.content for c in chunks]

            window = getattr(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3)
            max_tokens = getattr(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000)
            service = DocumentEnrichmentService(llm_client, max_tokens=max_tokens)
            return service.enrich_chunks(chunks, full_text, window=window)
        except Exception as e:
            self.logger.warning(
                f"Contextual enrichment failed, using raw content: {e}"
            )
            return [c.content for c in chunks]
