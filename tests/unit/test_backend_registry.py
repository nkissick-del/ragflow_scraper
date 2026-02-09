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
        assert names == ["anythingllm", "pgvector", "ragflow"]

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
