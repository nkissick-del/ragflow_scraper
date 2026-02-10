"""Integration tests for accessibility features."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch
from app.config import Config
from app.web import create_app


def _make_mock_container():
    """Create a mock container that won't trigger real HTTP calls."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.ragflow_client.test_connection.return_value = False
    mock.ragflow_client.list_embedding_models.return_value = []
    mock.ragflow_client.list_chunk_methods.return_value = []
    mock.flaresolverr_client.test_connection.return_value = False
    mock.settings.get_all.return_value = {
        "ragflow": {"default_dataset_id": "", "auto_upload": False, "auto_create_dataset": True,
                     "default_embedding_model": "", "default_chunk_method": "paper",
                     "wait_for_parsing": True, "parser_config": {"chunk_token_num": 128, "layout_recognize": "DeepDOC"}},
        "flaresolverr": {"enabled": False, "timeout": 60, "max_timeout": 120},
        "scraping": {"use_flaresolverr_by_default": False, "default_request_delay": 2.0,
                      "default_timeout": 60, "default_retry_attempts": 3, "max_concurrent_downloads": 3},
        "pipeline": {"metadata_merge_strategy": "", "filename_template": "",
                      "parser_backend": "", "archive_backend": "", "rag_backend": ""},
        "services": {"gotenberg_url": "", "gotenberg_timeout": 0, "tika_url": "", "tika_timeout": 0,
                      "docling_serve_url": "", "docling_serve_timeout": 0,
                      "paperless_url": "", "ragflow_url": "", "anythingllm_url": ""},
        "application": {"name": "PDF Scraper", "version": "0.1.0"},
        "scrapers": {},
        "scheduler": {"enabled": False, "run_on_startup": False},
    }
    mock.flaresolverr_enabled = False
    # settings.get needs to return values from _all_settings to support _get_effective_* helpers
    _all = mock.settings.get_all.return_value
    def _mock_get(key, default=None):
        keys = key.split(".")
        value = _all
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    mock.settings.get.side_effect = _mock_get
    return mock


@pytest.fixture
def app():
    """Create test Flask app."""
    mock_container = _make_mock_container()
    patches = [
        patch("app.web.blueprints.settings.ui.container", mock_container),
        patch("app.web.blueprints.settings.api.container", mock_container),
        patch("app.web.blueprints.settings.helpers.container", mock_container),
        patch("app.web.blueprints.settings.reconciliation.container", mock_container),
        patch("app.web.blueprints.settings.ui.http_requests"),
        patch("app.web.blueprints.settings.api.http_requests"),
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.metrics_logs.container", mock_container),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
        patch.object(Config, "SECRET_KEY", "test-secret-key-for-integration-tests"),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["RATELIMIT_ENABLED"] = False
        yield app
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestNavigationAccessibility:
    """Test accessibility features in navigation."""

    def test_settings_active_link_has_aria_current(self, client):
        """Test that the active navigation link has aria-current='page' on Settings page."""
        response = client.get("/settings")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # Find the navigation container and links within it
        nav = soup.find("nav")
        assert nav is not None, "Navigation container <nav> not found"
        nav_links = nav.find_all("a")

        settings_link = None
        scrapers_link = None

        for link in nav_links:
            # Normalize whitespace and use exact match to avoid "Advanced Settings"
            text = " ".join(link.text.strip().split())

            if text == "Settings":
                settings_link = link
            elif text == "Scrapers":
                scrapers_link = link

        # Verify Settings link is active
        assert settings_link is not None, "Settings link not found"
        assert "active" in settings_link.get("class", []), (
            "Settings link should have active class"
        )

        # Verify aria-current="page"
        assert settings_link.get("aria-current") == "page", (
            "Settings link should have aria-current='page'"
        )

        # Verify Scrapers link is NOT active
        assert scrapers_link is not None, "Scrapers link not found"
        assert "active" not in scrapers_link.get("class", []), (
            "Scrapers link should not have active class"
        )
        assert not scrapers_link.get("aria-current"), (
            "Scrapers link should not have aria-current"
        )
