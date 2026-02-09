import pytest
from unittest.mock import patch, MagicMock
from app.config import Config
from app.services.container import get_container, reset_container


class TestConfigValidation:
    @pytest.fixture(autouse=True)
    def clean_config(self):
        """Mock out all validation-sensitive Config attributes to valid states."""
        with (
            patch.object(Config, "SECRET_KEY", "test-secret-key-for-validation-tests"),
            patch.object(Config, "BASIC_AUTH_ENABLED", False),
            patch.object(Config, "ARCHIVE_BACKEND", "local"),
            patch.object(Config, "RAG_BACKEND", "ragflow"),
            patch.object(Config, "RAGFLOW_API_KEY", "key"),
            patch.object(Config, "RAGFLOW_DATASET_ID", "id"),
            patch.object(Config, "PARSER_BACKEND", "docling"),
            patch.object(Config, "METADATA_MERGE_STRATEGY", "smart"),
            patch.object(Config, "FILENAME_TEMPLATE", ""),
            patch.object(Config, "EMBEDDING_BACKEND", "ollama"),
            patch.object(Config, "CHUNKING_STRATEGY", "fixed"),
            patch.object(Config, "CHUNK_MAX_TOKENS", 512),
            patch.object(Config, "CHUNK_OVERLAP_TOKENS", 64),
            patch.object(Config, "EMBEDDING_DIMENSIONS", 768),
        ):
            yield

    def test_paperless_validation(self):
        """Test that paperless requires API_TOKEN."""
        with patch.object(Config, "ARCHIVE_BACKEND", "paperless"):
            with patch.object(Config, "PAPERLESS_API_TOKEN", ""):
                with pytest.raises(
                    ValueError,
                    match="ARCHIVE_BACKEND='paperless' requires PAPERLESS_API_TOKEN",
                ):
                    Config.validate()

            with patch.object(Config, "PAPERLESS_API_TOKEN", "some-token"):
                # Should not raise
                Config.validate()

    def test_ragflow_validation(self):
        """Test that ragflow requires API_KEY and DATASET_ID."""
        with patch.object(Config, "RAG_BACKEND", "ragflow"):
            with patch.object(Config, "RAGFLOW_API_KEY", ""):
                with pytest.raises(
                    ValueError,
                    match="RAG_BACKEND='ragflow' requires both RAGFLOW_API_KEY and RAGFLOW_DATASET_ID",
                ):
                    Config.validate()

            with patch.object(Config, "RAGFLOW_API_KEY", "key"):
                with patch.object(Config, "RAGFLOW_DATASET_ID", ""):
                    with pytest.raises(
                        ValueError,
                        match="RAG_BACKEND='ragflow' requires both RAGFLOW_API_KEY and RAGFLOW_DATASET_ID",
                    ):
                        Config.validate()

                with patch.object(Config, "RAGFLOW_DATASET_ID", "123"):
                    # Should not raise
                    Config.validate()

    def test_anythingllm_validation(self):
        """Test that anythingllm requires URL, KEY, and WORKSPACE_ID."""
        with patch.object(Config, "RAG_BACKEND", "anythingllm"):
            # Missing API_URL
            with (
                patch.object(Config, "ANYTHINGLLM_API_URL", ""),
                patch.object(Config, "ANYTHINGLLM_API_KEY", "key"),
                patch.object(Config, "ANYTHINGLLM_WORKSPACE_ID", "workspace"),
                pytest.raises(
                    ValueError,
                    match="requires ANYTHINGLLM_API_URL, ANYTHINGLLM_API_KEY, and ANYTHINGLLM_WORKSPACE_ID",
                ),
            ):
                Config.validate()

            # Missing API_KEY
            with (
                patch.object(Config, "ANYTHINGLLM_API_URL", "http://localhost"),
                patch.object(Config, "ANYTHINGLLM_API_KEY", ""),
                patch.object(Config, "ANYTHINGLLM_WORKSPACE_ID", "workspace"),
                pytest.raises(
                    ValueError,
                    match="requires ANYTHINGLLM_API_URL, ANYTHINGLLM_API_KEY, and ANYTHINGLLM_WORKSPACE_ID",
                ),
            ):
                Config.validate()

            # Missing WORKSPACE_ID
            with (
                patch.object(Config, "ANYTHINGLLM_API_URL", "http://localhost"),
                patch.object(Config, "ANYTHINGLLM_API_KEY", "key"),
                patch.object(Config, "ANYTHINGLLM_WORKSPACE_ID", ""),
                pytest.raises(
                    ValueError,
                    match="requires ANYTHINGLLM_API_URL, ANYTHINGLLM_API_KEY, and ANYTHINGLLM_WORKSPACE_ID",
                ),
            ):
                Config.validate()

            # All fields present
            with (
                patch.object(Config, "ANYTHINGLLM_API_URL", "http://localhost"),
                patch.object(Config, "ANYTHINGLLM_API_KEY", "key"),
                patch.object(Config, "ANYTHINGLLM_WORKSPACE_ID", "workspace"),
            ):
                # Should not raise
                Config.validate()

    def test_tika_validation(self):
        """Test that PARSER_BACKEND=tika requires TIKA_SERVER_URL."""
        with patch.object(Config, "PARSER_BACKEND", "tika"):
            with patch.object(Config, "TIKA_SERVER_URL", ""):
                with pytest.raises(
                    ValueError,
                    match="PARSER_BACKEND='tika' requires TIKA_SERVER_URL",
                ):
                    Config.validate()

            with patch.object(Config, "TIKA_SERVER_URL", "http://localhost:9998"):
                # Should not raise
                Config.validate()

    def test_backend_constants_extraction(self):
        """Test that backend lists are extracted into constants."""
        assert hasattr(Config, "VALID_PARSER_BACKENDS")
        assert "docling" in Config.VALID_PARSER_BACKENDS
        assert hasattr(Config, "VALID_ARCHIVE_BACKENDS")
        assert "paperless" in Config.VALID_ARCHIVE_BACKENDS
        assert hasattr(Config, "VALID_RAG_BACKENDS")
        assert "ragflow" in Config.VALID_RAG_BACKENDS
        assert hasattr(Config, "VALID_METADATA_MERGE_STRATEGIES")
        assert "smart" in Config.VALID_METADATA_MERGE_STRATEGIES


class TestServiceContainerRAGValidation:
    def teardown_method(self):
        reset_container()

    def test_rag_backend_requires_config(self):
        """ServiceContainer should validate RAG config before instantiation."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "ragflow"
            mock_config.RAGFLOW_API_URL = ""

            with pytest.raises(ValueError, match="RAGFlow configuration missing"):
                _ = container.rag_backend

    def test_rag_backend_calls_is_available(self):
        """ServiceContainer should call is_available() on RAG backend."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAG_BACKEND = "ragflow"
            mock_config.RAGFLOW_API_URL = "http://localhost:9380"
            mock_config.RAGFLOW_API_KEY = "test-key"

            with patch(
                "app.backends.rag.ragflow_adapter.RAGFlowBackend"
            ) as mock_backend_cls:
                mock_instance = MagicMock()
                mock_backend_cls.return_value = mock_instance

                # Case 1: Unavailable
                mock_instance.is_available.return_value = False
                with pytest.raises(
                    ValueError, match="RAG backend 'ragflow' not available"
                ):
                    _ = container.rag_backend

                # Case 2: Available
                reset_container()
                container = get_container()
                mock_instance.reset_mock()  # Reset mock to clear previous calls
                mock_instance.is_available.return_value = True
                backend = container.rag_backend
                assert backend is mock_instance
                assert mock_instance.is_available.called
