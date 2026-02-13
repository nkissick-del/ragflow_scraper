"""
New tests for ServiceContainer refactoring.
"""

import threading

import pytest
from unittest.mock import patch

from app.services.container import ServiceContainer, reset_container, get_container


class TestServiceContainerRefactoring:
    """Test new functionality in ServiceContainer."""

    def setup_method(self):
        """Reset container before each test."""
        reset_container()

    def teardown_method(self):
        """Reset container after each test."""
        reset_container()

    def test_anythingllm_requires_config(self):
        """rag_backend should raise if AnythingLLM config is missing."""
        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "anythingllm"
            mock_config.ANYTHINGLLM_API_URL = ""
            mock_config.ANYTHINGLLM_API_KEY = ""

            container = get_container()
            with pytest.raises(ValueError, match="AnythingLLM configuration missing"):
                _ = container.rag_backend

    def test_anythingllm_success_with_config(self):
        """rag_backend should succeed if AnythingLLM config is present."""
        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "anythingllm"
            mock_config.ANYTHINGLLM_API_URL = "http://localhost:3001"
            mock_config.ANYTHINGLLM_API_KEY = "test-key"
            mock_config.ANYTHINGLLM_WORKSPACE_ID = "test-workspace"

            with patch(
                "app.backends.rag.anythingllm_adapter.AnythingLLMBackend"
            ) as mock_backend:
                container = get_container()
                backend = container.rag_backend
                assert backend is not None
                mock_backend.assert_called_once_with(
                    api_url="http://localhost:3001",
                    api_key="test-key",
                    workspace_id="test-workspace",
                )

    def test_archive_backend_availability_check(self):
        """archive_backend should raise ValueError if is_available() returns False."""
        with patch("app.services.container.Config") as mock_config:
            mock_config.ARCHIVE_BACKEND = "paperless"

            with patch(
                "app.backends.archives.paperless_adapter.PaperlessArchiveBackend"
            ) as mock_backend_cls:
                mock_instance = mock_backend_cls.return_value
                mock_instance.is_available.return_value = False

                container = get_container()
                with pytest.raises(ValueError, match="not available"):
                    _ = container.archive_backend

    def test_archive_backend_success_if_available(self):
        """archive_backend should succeed if is_available() returns True."""
        with patch("app.services.container.Config") as mock_config:
            mock_config.ARCHIVE_BACKEND = "paperless"

            with patch(
                "app.backends.archives.paperless_adapter.PaperlessArchiveBackend"
            ) as mock_backend_cls:
                mock_instance = mock_backend_cls.return_value
                mock_instance.is_available.return_value = True

                container = get_container()
                backend = container.archive_backend
                assert backend is mock_instance
                mock_instance.is_available.assert_called_once()

    def test_singleton_thread_safety(self):
        """20 threads calling ServiceContainer() should all get the same instance."""
        results: list[int] = []

        def create():
            c = ServiceContainer()
            results.append(id(c))

        threads = [threading.Thread(target=create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        assert len(set(results)) == 1  # All same id

    def test_state_tracker_concurrent_access(self):
        """10 threads getting different trackers should all succeed."""
        container = get_container()
        results: dict[str, object] = {}
        errors: list[Exception] = []

        def get_tracker(name: str):
            try:
                tracker = container.state_tracker(name)
                results[name] = tracker
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=get_tracker, args=(f"scraper_{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(results) == 10
