"""Tests for app.web.job_factory."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, mock_open
import json

from app.web.job_factory import create_runnable


class TestCreateRunnable:
    """Test create_runnable helper."""

    def test_dry_run_returns_scraper(self):
        """Dry-run should return a raw scraper from the registry."""
        mock_scraper = MagicMock()
        with patch(
            "app.scrapers.ScraperRegistry"
        ) as mock_registry:
            mock_registry.get_scraper.return_value = mock_scraper

            result = create_runnable("test_scraper", dry_run=True, max_pages=5)

            assert result is mock_scraper
            mock_registry.get_scraper.assert_called_once_with(
                "test_scraper", dry_run=True, max_pages=5,
            )

    def test_preview_returns_scraper(self):
        """Preview mode should return a raw scraper."""
        mock_scraper = MagicMock()
        with patch(
            "app.scrapers.ScraperRegistry"
        ) as mock_registry:
            mock_registry.get_scraper.return_value = mock_scraper

            result = create_runnable("test_scraper", preview=True)

            assert result is mock_scraper

    def test_real_run_returns_pipeline(self):
        """Non-dry-run should return a Pipeline instance."""
        mock_pipeline = MagicMock()
        config_data = {"upload_to_ragflow": False, "upload_to_paperless": True}

        with (
            patch("app.orchestrator.pipeline.Pipeline", return_value=mock_pipeline),
            patch.object(
                __import__("app.config", fromlist=["Config"]).Config,
                "SCRAPERS_CONFIG_DIR",
                new_callable=lambda: MagicMock(),
            ),
        ):
            # Simpler approach: patch the import path
            mock_path = MagicMock()
            mock_path.exists.return_value = True

            from app.config import Config
            with patch.object(Config, "SCRAPERS_CONFIG_DIR", MagicMock(**{"__truediv__": MagicMock(return_value=mock_path)})):
                with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
                    result = create_runnable("test_scraper", max_pages=10)

            assert result is mock_pipeline

    def test_real_run_with_no_config_file(self):
        """Pipeline uses defaults when no config file exists."""
        mock_pipeline = MagicMock()

        with patch("app.orchestrator.pipeline.Pipeline", return_value=mock_pipeline) as mock_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = False

            from app.config import Config
            with patch.object(Config, "SCRAPERS_CONFIG_DIR", MagicMock(**{"__truediv__": MagicMock(return_value=mock_path)})):
                create_runnable("test_scraper")

            mock_cls.assert_called_once_with(
                scraper_name="test_scraper",
                max_pages=None,
                upload_to_ragflow=True,
                upload_to_paperless=True,
                verify_document_timeout=60,
            )

    def test_real_run_with_invalid_json_config(self):
        """Pipeline uses defaults when config file has invalid JSON."""
        mock_pipeline = MagicMock()

        with patch("app.orchestrator.pipeline.Pipeline", return_value=mock_pipeline) as mock_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = True

            from app.config import Config
            with (
                patch.object(Config, "SCRAPERS_CONFIG_DIR", MagicMock(**{"__truediv__": MagicMock(return_value=mock_path)})),
                patch("builtins.open", mock_open(read_data="not json")),
            ):
                create_runnable("test_scraper")

            # Should still create pipeline with defaults
            mock_cls.assert_called_once()
            kwargs = mock_cls.call_args[1]
            assert kwargs["upload_to_ragflow"] is True
            assert kwargs["upload_to_paperless"] is True
