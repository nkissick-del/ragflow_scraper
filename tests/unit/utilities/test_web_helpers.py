"""Tests for web helpers (app/web/helpers.py).

Tests get_scraper_status, load_scraper_configs, build_ragflow_options,
and build_scraper_metadata.
"""

import json
from unittest.mock import patch, MagicMock

from app.config import Config


# ---------------------------------------------------------------------------
# get_scraper_status
# ---------------------------------------------------------------------------


class TestGetScraperStatus:
    """Tests for get_scraper_status."""

    def test_in_flight_job_not_idle(self):
        from app.web.helpers import get_scraper_status

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "running"
        mock_container = MagicMock()

        with patch("app.web.helpers.job_queue", mock_job_queue), \
             patch("app.web.helpers.container", mock_container):
            result = get_scraper_status("test")

        assert result == "running"
        # Should not have checked state_tracker since job_queue returned non-idle
        mock_container.state_tracker.assert_not_called()

    def test_idle_with_no_state(self):
        from app.web.helpers import get_scraper_status

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state

        with patch("app.web.helpers.job_queue", mock_job_queue), \
             patch("app.web.helpers.container", mock_container):
            result = get_scraper_status("test")

        assert result == "idle"

    def test_idle_no_last_updated(self):
        from app.web.helpers import get_scraper_status

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {"status": "done"}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state

        with patch("app.web.helpers.job_queue", mock_job_queue), \
             patch("app.web.helpers.container", mock_container):
            result = get_scraper_status("test")

        assert result == "idle"

    def test_error_state(self):
        from app.web.helpers import get_scraper_status

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {
            "last_updated": "2024-01-01T00:00:00",
            "statistics": {"total_failed": 3},
        }
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state

        with patch("app.web.helpers.job_queue", mock_job_queue), \
             patch("app.web.helpers.container", mock_container):
            result = get_scraper_status("test")

        assert result == "error"

    def test_ready_state(self):
        from app.web.helpers import get_scraper_status

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {
            "last_updated": "2024-01-01T00:00:00",
            "statistics": {"total_failed": 0},
        }
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state

        with patch("app.web.helpers.job_queue", mock_job_queue), \
             patch("app.web.helpers.container", mock_container):
            result = get_scraper_status("test")

        assert result == "ready"


# ---------------------------------------------------------------------------
# load_scraper_configs
# ---------------------------------------------------------------------------


class TestLoadScraperConfigs:
    """Tests for load_scraper_configs."""

    def test_loads_config_file(self, tmp_path):
        from app.web.helpers import load_scraper_configs

        config_dir = tmp_path / "scrapers"
        config_dir.mkdir()
        config_file = config_dir / "my_scraper.json"
        config_file.write_text(json.dumps({"key": "value"}))

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state
        mock_container.settings.get_scraper_cloudflare_enabled.return_value = False
        mock_container.settings.get_scraper_ragflow_settings.return_value = {}

        scrapers = [{"name": "my_scraper"}]

        with patch("app.web.helpers.container", mock_container), \
             patch("app.web.helpers.job_queue", mock_job_queue), \
             patch.object(Config, "SCRAPERS_CONFIG_DIR", config_dir):
            load_scraper_configs(scrapers)

        assert scrapers[0]["config"] == {"key": "value"}
        assert scrapers[0]["status"] == "idle"

    def test_no_config_file(self, tmp_path):
        from app.web.helpers import load_scraper_configs

        config_dir = tmp_path / "scrapers"
        config_dir.mkdir()

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state
        mock_container.settings.get_scraper_cloudflare_enabled.return_value = False
        mock_container.settings.get_scraper_ragflow_settings.return_value = {}

        scrapers = [{"name": "nonexistent"}]

        with patch("app.web.helpers.container", mock_container), \
             patch("app.web.helpers.job_queue", mock_job_queue), \
             patch.object(Config, "SCRAPERS_CONFIG_DIR", config_dir):
            load_scraper_configs(scrapers)

        assert scrapers[0]["config"] == {}

    def test_attaches_state_and_ragflow_settings(self, tmp_path):
        from app.web.helpers import load_scraper_configs

        config_dir = tmp_path / "scrapers"
        config_dir.mkdir()

        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {"last_updated": "2024-01-01"}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state
        mock_container.settings.get_scraper_cloudflare_enabled.return_value = True
        mock_container.settings.get_scraper_ragflow_settings.return_value = {"chunk_method": "paper"}

        scrapers = [{"name": "test_scraper", "default_chunk_method": "naive", "default_parser": "DeepDOC"}]

        with patch("app.web.helpers.container", mock_container), \
             patch("app.web.helpers.job_queue", mock_job_queue), \
             patch.object(Config, "SCRAPERS_CONFIG_DIR", config_dir):
            load_scraper_configs(scrapers)

        assert scrapers[0]["state"] == {"last_updated": "2024-01-01"}
        assert scrapers[0]["cloudflare_enabled"] is True
        assert scrapers[0]["ragflow_settings"] == {"chunk_method": "paper"}


# ---------------------------------------------------------------------------
# build_ragflow_options
# ---------------------------------------------------------------------------


class TestBuildRagflowOptions:
    """Tests for build_ragflow_options."""

    def test_success(self):
        from app.web.helpers import build_ragflow_options

        mock_container = MagicMock()
        mock_container.ragflow_client.list_chunk_methods.return_value = ["naive", "paper"]
        mock_container.ragflow_client.list_pdf_parsers.return_value = ["DeepDOC"]
        mock_container.ragflow_client.list_ingestion_pipelines.return_value = []
        mock_container.ragflow_client.session_configured = False

        with patch("app.web.helpers.container", mock_container):
            result = build_ragflow_options(MagicMock())

        assert result["chunk_methods"] == ["naive", "paper"]
        assert result["pdf_parsers"] == ["DeepDOC"]
        assert result["embedding_providers"] == {}

    def test_value_error_from_ragflow_client(self):
        from app.web.helpers import build_ragflow_options

        mock_container = MagicMock()
        type(mock_container).ragflow_client = property(
            lambda self: (_ for _ in ()).throw(ValueError("not configured"))
        )

        with patch("app.web.helpers.container", mock_container):
            result = build_ragflow_options(MagicMock())

        assert result == {
            "chunk_methods": [],
            "pdf_parsers": [],
            "pipelines": [],
            "embedding_providers": {},
        }

    def test_with_session_models(self):
        from app.web.helpers import build_ragflow_options

        mock_container = MagicMock()
        mock_container.ragflow_client.list_chunk_methods.return_value = []
        mock_container.ragflow_client.list_pdf_parsers.return_value = []
        mock_container.ragflow_client.list_ingestion_pipelines.return_value = []
        mock_container.ragflow_client.session_configured = True
        mock_container.ragflow_client.list_embedding_models.return_value = [
            {"name": "model-a", "provider": "OpenAI"},
            {"name": "model-b", "provider": "OpenAI"},
            {"name": "model-c", "provider": "HuggingFace"},
        ]

        with patch("app.web.helpers.container", mock_container):
            result = build_ragflow_options(MagicMock())

        assert "OpenAI" in result["embedding_providers"]
        assert len(result["embedding_providers"]["OpenAI"]) == 2
        assert "HuggingFace" in result["embedding_providers"]

    def test_session_models_exception(self):
        from app.web.helpers import build_ragflow_options

        mock_container = MagicMock()
        mock_container.ragflow_client.list_chunk_methods.return_value = ["naive"]
        mock_container.ragflow_client.list_pdf_parsers.return_value = []
        mock_container.ragflow_client.list_ingestion_pipelines.return_value = []
        mock_container.ragflow_client.session_configured = True
        mock_container.ragflow_client.list_embedding_models.side_effect = RuntimeError("fail")

        with patch("app.web.helpers.container", mock_container):
            result = build_ragflow_options(MagicMock())

        # Should still return chunk_methods even though models failed
        assert result["chunk_methods"] == ["naive"]
        assert result["embedding_providers"] == {}


# ---------------------------------------------------------------------------
# build_scraper_metadata
# ---------------------------------------------------------------------------


class TestBuildScraperMetadata:
    """Tests for build_scraper_metadata."""

    def test_found_scraper(self):
        from app.web.helpers import build_scraper_metadata

        mock_class = MagicMock()
        mock_class.get_metadata.return_value = {"name": "test", "display_name": "Test"}
        mock_state = MagicMock()
        mock_state.get_last_run_info.return_value = {"last_updated": "2024-01-01"}
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = mock_state
        mock_job_queue = MagicMock()
        mock_job_queue.status.return_value = "idle"

        with patch("app.web.helpers.ScraperRegistry") as mock_registry, \
             patch("app.web.helpers.container", mock_container), \
             patch("app.web.helpers.job_queue", mock_job_queue):
            mock_registry.get_scraper_class.return_value = mock_class
            result = build_scraper_metadata("test")

        assert result["name"] == "test"
        assert result["state"] == {"last_updated": "2024-01-01"}
        # Status is "ready" because last_updated is present and total_failed is 0
        assert result["status"] == "ready"

    def test_not_found_returns_empty_dict(self):
        from app.web.helpers import build_scraper_metadata

        with patch("app.web.helpers.ScraperRegistry") as mock_registry:
            mock_registry.get_scraper_class.return_value = None
            result = build_scraper_metadata("nonexistent")

        assert result == {}
