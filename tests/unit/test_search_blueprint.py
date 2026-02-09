"""Tests for search blueprint."""

import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    """Create a Flask app with mocked container for testing."""
    mock_container = MagicMock()
    mock_job_queue = MagicMock()

    # Mock pgvector_client
    mock_pgvector = MagicMock()
    mock_pgvector.is_configured.return_value = True
    mock_pgvector.test_connection.return_value = True
    mock_pgvector.get_sources.return_value = [
        {"source": "aemo", "chunk_count": 100},
        {"source": "guardian", "chunk_count": 50},
    ]
    mock_pgvector.get_stats.return_value = {
        "total_chunks": 150,
        "total_documents": 10,
        "total_sources": 2,
    }
    mock_pgvector.search.return_value = [
        {
            "source": "aemo",
            "filename": "doc.md",
            "chunk_index": 0,
            "content": "Energy policy content",
            "metadata": {"title": "Test"},
            "score": 0.95,
        }
    ]
    mock_container.pgvector_client = mock_pgvector

    # Mock embedding_client
    mock_embedder = MagicMock()
    mock_embedder.is_configured.return_value = True
    mock_embedder.embed_single.return_value = [0.1, 0.2, 0.3]
    mock_container.embedding_client = mock_embedder

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.get.return_value = ""
    mock_settings.flaresolverr_enabled = False
    mock_container.settings = mock_settings

    patches = [
        patch("app.web.runtime.container", mock_container),
        patch("app.web.runtime.job_queue", mock_job_queue),
        # Also patch the local binding in the search blueprint module —
        # `from app.web.runtime import container` creates a separate reference.
        patch("app.web.blueprints.search.container", mock_container),
    ]
    for p in patches:
        p.start()

    try:
        from app.config import Config
        with patch.object(Config, "BASIC_AUTH_ENABLED", False), \
             patch.object(Config, "LOG_TO_FILE", False), \
             patch.object(Config, "SECRET_KEY", "test-secret-key"):
            from app.web import create_app
            flask_app = create_app()
            flask_app.config["TESTING"] = True
            flask_app.config["WTF_CSRF_ENABLED"] = False
            flask_app.config["RATELIMIT_ENABLED"] = False
            yield flask_app
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestSearchPage:
    """Test GET /search."""

    def test_search_page_renders(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200
        assert b"Semantic Search" in resp.data


class TestSearchAPI:
    """Test POST /api/search."""

    def test_search_success(self, client):
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "energy policy", "limit": 5}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["results"][0]["source"] == "aemo"
        assert data["results"][0]["score"] == 0.95

    def test_search_empty_query(self, client):
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_search_with_sources_filter(self, client):
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "sources": ["aemo"]}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_search_limit_capped(self, client):
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "limit": 100}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestSourcesAPI:
    """Test GET /api/sources."""

    def test_list_sources(self, client):
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["sources"]) == 2
        assert data["stats"]["total_chunks"] == 150
