"""Tests for VectorStoreBackend ABC and VectorStoreResult dataclass."""

import pytest

from app.backends.vectorstores.base import VectorStoreBackend, VectorStoreResult


class TestVectorStoreResult:
    """Test VectorStoreResult dataclass validation."""

    def test_successful_result(self):
        r = VectorStoreResult(success=True, chunks_stored=5, store_name="pgvector")
        assert r.success is True
        assert r.chunks_stored == 5
        assert r.store_name == "pgvector"
        assert r.error is None

    def test_failed_result(self):
        r = VectorStoreResult(
            success=False, error="Connection refused", store_name="pgvector"
        )
        assert r.success is False
        assert r.error == "Connection refused"

    def test_missing_store_name_raises(self):
        with pytest.raises(ValueError, match="store_name must be provided"):
            VectorStoreResult(success=True, chunks_stored=1, store_name="")

    def test_success_with_error_raises(self):
        with pytest.raises(ValueError, match="must not include error"):
            VectorStoreResult(
                success=True, chunks_stored=1, error="oops", store_name="pgvector"
            )

    def test_failure_without_error_raises(self):
        with pytest.raises(ValueError, match="must include error"):
            VectorStoreResult(success=False, store_name="pgvector")

    def test_success_negative_chunks_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            VectorStoreResult(success=True, chunks_stored=-1, store_name="pgvector")

    def test_success_zero_chunks_ok(self):
        r = VectorStoreResult(success=True, chunks_stored=0, store_name="pgvector")
        assert r.chunks_stored == 0


class TestVectorStoreBackendABC:
    """Test that ABC cannot be instantiated and defaults work."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            VectorStoreBackend()  # type: ignore[abstract]

    def test_concrete_subclass_defaults(self):
        """Test concrete default methods on a minimal implementation."""

        class MinimalStore(VectorStoreBackend):
            @property
            def name(self) -> str:
                return "minimal"

            def store_chunks(self, source, filename, chunks, document_id=None):
                return len(chunks)

            def delete_document(self, source, filename):
                return 0

            def search(self, query_embedding, sources=None, metadata_filter=None, limit=10):
                return []

            def get_sources(self):
                return []

            def get_stats(self):
                return {}

            def is_configured(self):
                return True

            def test_connection(self):
                return True

        store = MinimalStore()

        # Test defaults
        assert store.is_available() is True
        store.ensure_ready()  # no-op
        store.close()  # no-op
        assert store.get_document_chunks("src", "file") == []

    def test_is_available_delegates_to_is_configured(self):
        """is_available() should return is_configured() by default."""

        class UnconfiguredStore(VectorStoreBackend):
            @property
            def name(self) -> str:
                return "test"

            def store_chunks(self, source, filename, chunks, document_id=None):
                return 0

            def delete_document(self, source, filename):
                return 0

            def search(self, query_embedding, sources=None, metadata_filter=None, limit=10):
                return []

            def get_sources(self):
                return []

            def get_stats(self):
                return {}

            def is_configured(self):
                return False

            def test_connection(self):
                return False

        store = UnconfiguredStore()
        assert store.is_available() is False
