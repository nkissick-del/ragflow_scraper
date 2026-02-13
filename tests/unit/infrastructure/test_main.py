"""Tests for app.main — application entry point."""

from unittest.mock import patch, MagicMock

import pytest


class TestMain:
    """Test the main() entry point with heavy mocking."""

    @pytest.fixture(autouse=True)
    def _setup_patches(self):
        """Set up all patches needed for main() to run without side effects."""
        self.mock_config = MagicMock()
        self.mock_config.HOST = "0.0.0.0"
        self.mock_config.PORT = 5000
        self.mock_config.DEBUG = False
        self.mock_config.LOG_LEVEL = "INFO"
        self.mock_config.DATABASE_URL = ""
        self.mock_config.ANYTHINGLLM_VIEW_NAME = "test_view"

        self.mock_setup_logging = MagicMock()
        self.mock_get_logger = MagicMock()
        self.mock_logger = MagicMock()
        self.mock_get_logger.return_value = self.mock_logger

        self.mock_container = MagicMock()
        self.mock_get_container = MagicMock(return_value=self.mock_container)

        self.mock_app = MagicMock()
        self.mock_create_app = MagicMock(return_value=self.mock_app)

        self.mock_registry = MagicMock()

        # Default: scheduler disabled
        self.mock_container.settings.get_section.return_value = {"enabled": False, "run_on_startup": False}

        self.patches = [
            patch("app.main.Config", self.mock_config),
            patch("app.main.setup_logging", self.mock_setup_logging),
            patch("app.main.get_logger", self.mock_get_logger),
            patch("app.main.get_container", self.mock_get_container),
            patch("app.main.create_app", self.mock_create_app),
            patch("app.main.ScraperRegistry", self.mock_registry),
        ]
        for p in self.patches:
            p.start()
        yield
        for p in reversed(self.patches):
            p.stop()

    def test_successful_startup(self):
        """main() should call ensure_directories, validate, create_app, and app.run."""
        from app.main import main

        main()

        self.mock_config.ensure_directories.assert_called_once()
        self.mock_config.validate.assert_called_once()
        self.mock_setup_logging.assert_called_once_with(name="scraper", level="INFO")
        self.mock_create_app.assert_called_once()
        self.mock_app.run.assert_called_once_with(
            host="0.0.0.0",
            port=5000,
            debug=False,
        )

    def test_config_validation_failure(self):
        """main() should raise if Config.validate() fails."""
        self.mock_config.validate.side_effect = ValueError("bad config")

        from app.main import main

        with pytest.raises(ValueError, match="bad config"):
            main()

        # app.run should NOT have been called
        self.mock_app.run.assert_not_called()

    def test_scheduler_enabled_and_starts(self):
        """When scheduler is enabled, main() should load schedules and start."""
        self.mock_container.settings.get_section.return_value = {
            "enabled": True,
            "run_on_startup": False,
        }
        mock_scheduler = MagicMock()
        self.mock_container.scheduler = mock_scheduler

        from app.main import main

        main()

        mock_scheduler.load_schedules.assert_called_once()
        mock_scheduler.start.assert_called_once()
        # run_on_startup is False, so run_now should NOT be called
        mock_scheduler.run_now.assert_not_called()

    def test_scheduler_with_run_on_startup(self):
        """When run_on_startup is True, main() should trigger all scrapers."""
        self.mock_container.settings.get_section.return_value = {
            "enabled": True,
            "run_on_startup": True,
        }
        mock_scheduler = MagicMock()
        self.mock_container.scheduler = mock_scheduler
        self.mock_registry.get_scraper_names.return_value = ["aemo", "guardian"]

        from app.main import main

        main()

        mock_scheduler.load_schedules.assert_called_once()
        mock_scheduler.start.assert_called_once()
        assert mock_scheduler.run_now.call_count == 2
        mock_scheduler.run_now.assert_any_call("aemo")
        mock_scheduler.run_now.assert_any_call("guardian")

    def test_vector_store_database_url_configured(self):
        """When DATABASE_URL is set, main() should ensure vector store schema."""
        self.mock_config.DATABASE_URL = "postgresql://localhost/test"
        mock_store = MagicMock()
        self.mock_container.vector_store = mock_store

        from app.main import main

        main()

        mock_store.ensure_ready.assert_called_once()

    def test_vector_store_init_failure_non_fatal(self):
        """Vector store init failure should not prevent the app from starting."""
        self.mock_config.DATABASE_URL = "postgresql://localhost/test"
        mock_store = MagicMock()
        mock_store.ensure_ready.side_effect = RuntimeError("connection failed")
        self.mock_container.vector_store = mock_store

        from app.main import main

        # Should NOT raise
        main()

        # App should still run
        self.mock_app.run.assert_called_once()
        # Exception should be logged
        self.mock_logger.exception.assert_called()
