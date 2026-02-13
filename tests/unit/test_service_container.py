"""
Tests for the ServiceContainer dependency injection container.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.container import ServiceContainer, get_container, reset_container
from app.services.settings_manager import SettingsManager
from app.services.state_tracker import StateTracker


class TestServiceContainer:
    """Test ServiceContainer functionality."""

    def teardown_method(self):
        """Reset container after each test."""
        reset_container()

    def test_singleton_pattern(self):
        """Container should return same instance."""
        container1 = get_container()
        container2 = get_container()
        assert container1 is container2

    def test_singleton_via_class_constructor(self):
        """ServiceContainer class should enforce singleton."""
        container1 = ServiceContainer()
        container2 = ServiceContainer()
        assert container1 is container2

    def test_settings_lazy_loaded(self):
        """Settings should be lazy-loaded on first access."""
        reset_container()
        container = get_container()
        assert container._settings is None

        settings = container.settings
        assert settings is not None
        assert container._settings is not None
        assert isinstance(settings, SettingsManager)

        # Second access should return cached instance
        settings2 = container.settings
        assert settings is settings2

    def test_ragflow_client_lazy_loaded(self):
        """RAGFlow client should be lazy-loaded on first access."""
        reset_container()
        container = get_container()
        assert container._ragflow_client is None

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_API_URL = "http://localhost:9380"
            mock_config.RAGFLOW_API_KEY = "test-key"
            mock_config.RAGFLOW_USERNAME = ""
            mock_config.RAGFLOW_PASSWORD = ""

            with patch("app.services.container.RAGFlowClient") as mock_client:
                _ = container.ragflow_client
                assert mock_client.called
                mock_client.assert_called_once()

                # Second access should return cached instance
                _ = container.ragflow_client
                # Still only called once (cached)
                assert mock_client.call_count == 1

    def test_ragflow_client_requires_config(self):
        """RAGFlow client should raise if config missing."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_API_URL = ""
            mock_config.RAGFLOW_API_KEY = ""

            with pytest.raises(ValueError, match="RAGFlow configuration missing"):
                _ = container.ragflow_client

    def test_ragflow_client_requires_api_key(self):
        """RAGFlow client should raise if API key missing."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_API_URL = "http://localhost:9380"
            mock_config.RAGFLOW_API_KEY = ""

            with pytest.raises(ValueError, match="RAGFlow configuration missing"):
                _ = container.ragflow_client

    def test_flaresolverr_client_lazy_loaded(self):
        """FlareSolverr client should be lazy-loaded on first access."""
        reset_container()
        container = get_container()
        assert container._flaresolverr_client is None

        with patch("app.services.container.Config") as mock_config:
            mock_config.FLARESOLVERR_URL = "http://localhost:8191"

            with patch("app.services.container.FlareSolverrClient") as mock_client:
                _ = container.flaresolverr_client
                assert mock_client.called

                # Second access should return cached instance
                _ = container.flaresolverr_client
                # Still only called once (cached)
                assert mock_client.call_count == 1

    def test_state_tracker_factory(self):
        """State tracker should be created per scraper (factory pattern)."""
        reset_container()
        container = get_container()

        with patch("app.services.container.StateTracker") as mock_tracker_class:
            # Setup mock instances
            mock_tracker1 = MagicMock(scraper_name="aemo")
            mock_tracker2 = MagicMock(scraper_name="aer")

            mock_tracker_class.side_effect = [mock_tracker1, mock_tracker2]

            # Get trackers (same scraper twice)
            tracker1 = container.state_tracker("aemo")
            tracker2 = container.state_tracker("aemo")

            # Same scraper returns cached instance
            assert tracker1 is tracker2
            assert mock_tracker_class.call_count == 1

            # Different scraper returns new instance
            tracker3 = container.state_tracker("aer")
            assert tracker1 is not tracker3
            assert mock_tracker_class.call_count == 2

    def test_state_tracker_cached_per_scraper(self):
        """State tracker should be cached per scraper name."""
        reset_container()
        container = get_container()

        tracker_aemo1 = container.state_tracker("aemo")
        tracker_aemo2 = container.state_tracker("aemo")
        tracker_aer = container.state_tracker("aer")

        # Same scraper name returns cached instance
        assert tracker_aemo1 is tracker_aemo2

        # Different scraper name returns different instance
        assert tracker_aemo1 is not tracker_aer
        assert tracker_aemo1.scraper_name == "aemo"
        assert tracker_aer.scraper_name == "aer"

        # Check internal cache
        assert len(container._state_trackers) == 2
        assert "aemo" in container._state_trackers
        assert "aer" in container._state_trackers

    def test_gotenberg_client_lazy_loaded(self):
        """Gotenberg client should be lazy-loaded on first access."""
        reset_container()
        container = get_container()
        assert container._gotenberg_client is None

        with patch("app.services.gotenberg_client.GotenbergClient.__init__", return_value=None):
            client = container.gotenberg_client
            assert container._gotenberg_client is not None

            # Second access should return cached instance
            client2 = container.gotenberg_client
            assert client is client2

    def test_tika_client_lazy_loaded(self):
        """Tika client should be lazy-loaded on first access."""
        reset_container()
        container = get_container()
        assert container._tika_client is None

        with patch("app.services.tika_client.TikaClient.__init__", return_value=None):
            client = container.tika_client
            assert container._tika_client is not None

            # Second access should return cached instance
            client2 = container.tika_client
            assert client is client2

    def test_parser_backend_tika(self):
        """Container should create TikaParser when PARSER_BACKEND=tika."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.PARSER_BACKEND = "tika"

            with patch(
                "app.backends.parsers.tika_parser.TikaParser"
            ) as mock_parser_cls:
                mock_instance = MagicMock()
                mock_parser_cls.return_value = mock_instance
                mock_instance.is_available.return_value = True

                backend = container.parser_backend
                assert backend is mock_instance

    def test_reset_clears_all_services(self):
        """Reset should clear all cached services."""
        reset_container()
        container = get_container()

        # Access services to populate cache
        _ = container.settings
        _ = container.state_tracker("aemo")
        _ = container.state_tracker("aer")

        # Verify cache populated
        assert container._settings is not None
        assert len(container._state_trackers) == 2

        # Reset
        container.reset()

        # Verify cache cleared
        assert container._settings is None
        assert container._ragflow_client is None
        assert container._flaresolverr_client is None
        assert container._gotenberg_client is None
        assert container._tika_client is None
        assert len(container._state_trackers) == 0

    def test_reset_container_global_function(self):
        """reset_container() should reset global instance."""
        # Get container to populate it
        container = get_container()
        _ = container.settings
        _ = container.state_tracker("test")

        # Verify cache populated
        assert container._settings is not None

        # Reset global container
        reset_container()

        # Next get_container should return new instance (or cleaned instance)
        container2 = get_container()
        assert container2._settings is None
        assert len(container2._state_trackers) == 0


class TestContainerIntegration:
    """Integration tests with actual services."""

    def teardown_method(self):
        """Reset container after each test."""
        reset_container()

    def test_container_provides_settings(self):
        """Container should provide SettingsManager."""
        reset_container()
        container = get_container()

        settings = container.settings
        assert isinstance(settings, SettingsManager)

    def test_container_provides_state_tracker(self):
        """Container should provide StateTracker."""
        reset_container()
        container = get_container()

        tracker = container.state_tracker("test_scraper")
        assert isinstance(tracker, StateTracker)
        assert tracker.scraper_name == "test_scraper"

    def test_container_error_message_clarity(self):
        """Error message for missing RAGFlow config should be clear."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_API_URL = ""
            mock_config.RAGFLOW_API_KEY = ""

            error_msg = None
            try:
                _ = container.ragflow_client
            except ValueError as e:
                error_msg = str(e)

            assert error_msg is not None
            assert "RAGFlow" in error_msg
            assert "RAGFLOW_API_URL" in error_msg
            assert "RAGFLOW_API_KEY" in error_msg

    def test_multiple_containers_use_same_instance(self):
        """Multiple ServiceContainer() calls should return same instance."""
        reset_container()

        c1 = ServiceContainer()
        c2 = ServiceContainer()
        c3 = get_container()

        assert c1 is c2
        assert c2 is c3
        assert id(c1) == id(c2) == id(c3)

    def test_container_logging(self):
        """Container should log initialization events."""
        reset_container()
        container = get_container()

        with patch.object(container.logger, "debug") as mock_debug:
            # Access settings to trigger logging
            _ = container.settings
            mock_debug.assert_called_with("Initialized SettingsManager")

            # Access state tracker to trigger logging
            _ = container.state_tracker("test")
            assert mock_debug.call_count >= 2  # Settings + state tracker


# ── Additional coverage tests ─────────────────────────────────────────


class TestResetServices:
    """Test reset_services() partial reset."""

    def teardown_method(self):
        reset_container()

    def test_reset_services_clears_backend_caches(self):
        """reset_services should clear backend instances but keep settings."""
        reset_container()
        container = get_container()

        # Populate settings
        _ = container.settings
        assert container._settings is not None

        # Manually set backend cache entries
        container._parser_backend = MagicMock()
        container._archive_backend = MagicMock()
        container._rag_backend = MagicMock()
        container._vector_store = MagicMock()

        container.reset_services()

        # Backend caches cleared
        assert container._parser_backend is None
        assert container._archive_backend is None
        assert container._rag_backend is None
        assert container._vector_store is None
        assert container._ragflow_client is None
        assert container._flaresolverr_client is None
        assert container._embedding_client is None
        assert container._llm_client is None

        # Settings preserved
        assert container._settings is not None

    def test_reset_services_preserves_state_trackers(self):
        """reset_services should preserve state trackers."""
        reset_container()
        container = get_container()

        _ = container.state_tracker("test")
        assert len(container._state_trackers) == 1

        container.reset_services()

        assert len(container._state_trackers) == 1


class TestGetEffectiveMethods:
    """Test _get_effective_url, _get_effective_timeout, _get_config_attr."""

    def teardown_method(self):
        reset_container()

    def test_get_effective_url_settings_override(self):
        """Settings override should take priority over Config."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = "http://override:9380"
        container._settings = mock_settings

        result = container._get_effective_url("ragflow", "RAGFLOW_API_URL")
        assert result == "http://override:9380"

    def test_get_effective_url_config_fallback(self):
        """Should fall back to Config when no settings override."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = ""
        container._settings = mock_settings

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_API_URL = "http://config:9380"

            result = container._get_effective_url("ragflow", "RAGFLOW_API_URL")
            assert result == "http://config:9380"

    def test_get_effective_timeout_settings_override(self):
        """Settings override should take priority for timeout."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = 120
        container._settings = mock_settings

        result = container._get_effective_timeout("ragflow", "RAGFLOW_TIMEOUT")
        assert result == 120

    def test_get_effective_timeout_config_fallback(self):
        """Should fall back to Config when settings timeout is 0."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = 0
        container._settings = mock_settings

        with patch("app.services.container.Config") as mock_config:
            mock_config.RAGFLOW_TIMEOUT = 90

            result = container._get_effective_timeout("ragflow", "RAGFLOW_TIMEOUT")
            assert result == 90

    def test_get_config_attr_returns_value(self):
        """Should return Config attribute value."""
        reset_container()
        container = get_container()

        with patch("app.services.container.Config") as mock_config:
            mock_config.TEST_ATTR = "test_value"

            result = container._get_config_attr("TEST_ATTR")
            assert result == "test_value"

    def test_get_config_attr_missing_returns_default(self):
        """Should return default when Config attr missing."""
        reset_container()
        container = get_container()

        result = container._get_config_attr("TOTALLY_MISSING_ATTR", "default_val")
        assert result == "default_val"

    def test_safe_int_valid(self):
        """Should convert valid string to int."""
        reset_container()
        container = get_container()
        assert container._safe_int("42", 0) == 42

    def test_safe_int_invalid(self):
        """Should return default for invalid string."""
        reset_container()
        container = get_container()
        assert container._safe_int("not-a-number", 768) == 768

    def test_safe_int_none(self):
        """Should return default for None."""
        reset_container()
        container = get_container()
        assert container._safe_int(None, 100) == 100


class TestVectorStoreProperty:
    """Test vector_store property."""

    def teardown_method(self):
        reset_container()

    def test_vector_store_lazy_loaded(self):
        """vector_store should be lazy-loaded."""
        reset_container()
        container = get_container()
        assert container._vector_store is None

    def test_pgvector_client_alias(self):
        """pgvector_client should be an alias for vector_store."""
        reset_container()
        container = get_container()

        mock_store = MagicMock()
        container._vector_store = mock_store

        assert container.pgvector_client is mock_store


class TestGetEffectiveBackend:
    """Test _get_effective_backend method."""

    def teardown_method(self):
        reset_container()

    def test_settings_override(self):
        """Should use settings override when available."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = "docling_serve"
        container._settings = mock_settings

        result = container._get_effective_backend("parser")
        assert result == "docling_serve"

    def test_config_fallback(self):
        """Should fall back to Config when no settings override."""
        reset_container()
        container = get_container()

        mock_settings = MagicMock()
        mock_settings.get.return_value = ""
        container._settings = mock_settings

        with patch("app.services.container.Config") as mock_config:
            mock_config.PARSER_BACKEND = "tika"

            result = container._get_effective_backend("parser")
            assert result == "tika"
