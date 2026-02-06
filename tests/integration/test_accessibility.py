"""Integration tests for accessibility features."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch
from app.web import create_app


@pytest.fixture
def app():
    """Create test Flask app."""
    # Patch runtime dependencies before importing blueprints
    with patch("app.web.runtime.container"), patch("app.web.runtime.job_queue"):
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        yield app


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
