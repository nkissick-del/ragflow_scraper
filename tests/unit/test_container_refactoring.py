"""
New tests for ServiceContainer refactoring.
"""

import pytest
from unittest.mock import patch

from app.services.container import reset_container, get_container


class TestServiceContainerRefactoring:
    """Test new functionality in ServiceContainer."""

    def teardown_method(self):
        """Reset container after each test."""
        reset_container()

    def test_anythingllm_requires_config(self):
        """rag_backend should raise if AnythingLLM config is missing."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "anythingllm"
            mock_config.ANYTHINGLLM_API_URL = ""
            mock_config.ANYTHINGLLM_API_KEY = ""

            with pytest.raises(ValueError, match="AnythingLLM configuration missing"):
                _ = container.rag_backend

    def test_anythingllm_success_with_config(self):
        """rag_backend should succeed if AnythingLLM config is present."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "anythingllm"
            mock_config.ANYTHINGLLM_API_URL = "http://localhost:3001"
            mock_config.ANYTHINGLLM_API_KEY = "test-key"
            mock_config.ANYTHINGLLM_WORKSPACE_ID = "test-workspace"

            with patch(
                "app.backends.rag.anythingllm_adapter.AnythingLLMBackend"
            ) as mock_backend:
                backend = container.rag_backend
                assert backend is not None
                mock_backend.assert_called_once_with(
                    api_url="http://localhost:3001",
                    api_key="test-key",
                    workspace_id="test-workspace",
                )

    def test_archive_backend_availability_check(self):
        """archive_backend should raise RuntimeError if is_available() returns False."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.ARCHIVE_BACKEND = "paperless"

            with patch(
                "app.backends.archives.paperless_adapter.PaperlessArchiveBackend"
            ) as mock_backend_cls:
                mock_instance = mock_backend_cls.return_value
                mock_instance.is_available.return_value = False

                with pytest.raises(RuntimeError, match="not available"):
                    _ = container.archive_backend

    def test_archive_backend_success_if_available(self):
        """archive_backend should succeed if is_available() returns True."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.ARCHIVE_BACKEND = "paperless"

            with patch(
                "app.backends.archives.paperless_adapter.PaperlessArchiveBackend"
            ) as mock_backend_cls:
                mock_instance = mock_backend_cls.return_value
                mock_instance.is_available.return_value = True

                backend = container.archive_backend
                assert backend is mock_instance
                assert mock_instance.is_available.called
