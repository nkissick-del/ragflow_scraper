"""Tests for BackendRegistry."""

import pytest
from unittest.mock import MagicMock

from app.services.backend_registry import BackendRegistry, get_backend_registry


class TestBackendRegistry:
    """Test BackendRegistry class mechanics."""

    def test_register_and_create(self):
        """register() + create() should invoke factory with container."""
        registry = BackendRegistry()
        mock_container = MagicMock()
        mock_backend = MagicMock()

        factory = MagicMock(return_value=mock_backend)
        registry.register("parser", "test", factory)

        result = registry.create("parser", "test", mock_container)
        assert result is mock_backend
        factory.assert_called_once_with(mock_container)

    def test_unknown_backend_raises(self):
        """create() should raise ValueError for unregistered backend."""
        registry = BackendRegistry()
        with pytest.raises(ValueError, match="Unknown parser backend: missing"):
            registry.create("parser", "missing", MagicMock())

    def test_has(self):
        """has() should return True/False for registered/unregistered."""
        registry = BackendRegistry()
        registry.register("rag", "test", lambda c: None)
        assert registry.has("rag", "test") is True
        assert registry.has("rag", "other") is False

    def test_names(self):
        """names() should list registered names for a type."""
        registry = BackendRegistry()
        registry.register("parser", "alpha", lambda c: None)
        registry.register("parser", "beta", lambda c: None)
        registry.register("rag", "gamma", lambda c: None)
        assert sorted(registry.names("parser")) == ["alpha", "beta"]
        assert registry.names("rag") == ["gamma"]
        assert registry.names("archive") == []


class TestDefaultRegistry:
    """Test that the default registry has all expected backends."""

    def test_parser_names(self):
        registry = get_backend_registry()
        names = sorted(registry.names("parser"))
        assert names == ["docling", "docling_serve", "mineru", "tika"]

    def test_archive_names(self):
        registry = get_backend_registry()
        names = sorted(registry.names("archive"))
        assert names == ["local", "paperless", "s3"]

    def test_rag_names(self):
        registry = get_backend_registry()
        names = sorted(registry.names("rag"))
        assert names == ["anythingllm", "pgvector", "ragflow", "vector"]

    def test_vectorstore_names(self):
        registry = get_backend_registry()
        names = sorted(registry.names("vectorstore"))
        assert names == ["pgvector"]

    def test_unimplemented_mineru_raises(self):
        registry = get_backend_registry()
        with pytest.raises(ValueError, match="not yet implemented"):
            registry.create("parser", "mineru", MagicMock())

    def test_unimplemented_s3_raises(self):
        registry = get_backend_registry()
        with pytest.raises(ValueError, match="not yet implemented"):
            registry.create("archive", "s3", MagicMock())

    def test_unimplemented_local_raises(self):
        registry = get_backend_registry()
        with pytest.raises(ValueError, match="not yet implemented"):
            registry.create("archive", "local", MagicMock())


# ── Additional coverage tests ─────────────────────────────────────────


class TestRegistryEdgeCases:
    """Test edge cases for BackendRegistry."""

    def test_create_unknown_type_raises(self):
        """Should raise ValueError for completely unknown backend type."""
        registry = BackendRegistry()
        with pytest.raises(ValueError, match="Unknown nonexistent backend: foo"):
            registry.create("nonexistent", "foo", MagicMock())

    def test_factory_exception_propagates(self):
        """Factory exceptions should propagate to caller."""
        registry = BackendRegistry()

        def failing_factory(container):
            raise RuntimeError("Factory crashed")

        registry.register("parser", "broken", failing_factory)

        with pytest.raises(RuntimeError, match="Factory crashed"):
            registry.create("parser", "broken", MagicMock())

    def test_register_duplicate_key_overwrites(self):
        """Registering same key twice should overwrite."""
        registry = BackendRegistry()
        factory1 = MagicMock(return_value="backend1")
        factory2 = MagicMock(return_value="backend2")

        registry.register("parser", "test", factory1)
        registry.register("parser", "test", factory2)

        result = registry.create("parser", "test", MagicMock())
        assert result == "backend2"
        factory1.assert_not_called()

    def test_names_returns_empty_for_unknown_type(self):
        """names() should return empty list for unknown type."""
        registry = BackendRegistry()
        assert registry.names("nonexistent") == []

    def test_has_returns_false_for_unregistered(self):
        """has() returns False for unregistered backends."""
        registry = BackendRegistry()
        assert registry.has("parser", "anything") is False

    def test_multiple_types_isolated(self):
        """Backends of different types should be isolated."""
        registry = BackendRegistry()
        registry.register("parser", "test", lambda c: "parser_instance")
        registry.register("rag", "test", lambda c: "rag_instance")

        assert registry.create("parser", "test", MagicMock()) == "parser_instance"
        assert registry.create("rag", "test", MagicMock()) == "rag_instance"

    def test_names_only_returns_matching_type(self):
        """names() should only return names for the specified type."""
        registry = BackendRegistry()
        registry.register("parser", "p1", lambda c: None)
        registry.register("parser", "p2", lambda c: None)
        registry.register("rag", "r1", lambda c: None)

        parser_names = registry.names("parser")
        assert "p1" in parser_names
        assert "p2" in parser_names
        assert "r1" not in parser_names


class TestDefaultRegistryFactories:
    """Test that default registry factories behave correctly."""

    def test_docling_parser_factory(self):
        """docling parser factory should be registered."""
        registry = get_backend_registry()
        assert registry.has("parser", "docling")

    def test_ragflow_rag_missing_config_raises(self):
        """RAGFlow RAG factory should raise when config missing."""
        registry = get_backend_registry()
        mock_container = MagicMock()
        mock_container._get_effective_url.return_value = ""
        mock_container._get_config_attr.return_value = ""

        with pytest.raises(ValueError, match="RAGFlow configuration missing"):
            registry.create("rag", "ragflow", mock_container)

    def test_anythingllm_rag_missing_config_raises(self):
        """AnythingLLM RAG factory should raise when config missing."""
        registry = get_backend_registry()
        mock_container = MagicMock()
        mock_container._get_effective_url.return_value = ""
        mock_container._get_config_attr.return_value = ""

        with pytest.raises(ValueError, match="AnythingLLM configuration missing"):
            registry.create("rag", "anythingllm", mock_container)
