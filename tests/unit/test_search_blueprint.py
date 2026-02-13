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


class TestSearchAPIValidation:
    """Test input validation edge cases for POST /api/search."""

    def test_sources_not_a_list(self, client):
        """sources must be a list, not a string."""
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "sources": "aemo"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "sources must be a list"

    def test_invalid_source_name(self, client):
        """Source names containing special characters should be rejected."""
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "sources": ["../evil"]}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Invalid source name"

    def test_metadata_filter_not_a_dict(self, client):
        """metadata_filter must be a dict, not a list."""
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "metadata_filter": ["bad"]}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "metadata_filter must be an object"

    def test_search_non_integer_limit_uses_default(self, client):
        """Non-integer limit should fall back to default 10."""
        resp = client.post(
            "/api/search",
            data=json.dumps({"query": "test", "limit": "abc"}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestDocumentChunksAPI:
    """Test GET /api/search/document/<source>/<filename>."""

    def test_get_document_chunks_success(self, client, app):
        """Valid source and filename should return chunks."""
        # Access the mock pgvector_client through the app's patched container
        with app.app_context():
            from app.web.blueprints.search import container as search_container
            search_container.pgvector_client.get_document_chunks.return_value = [
                {"chunk_index": 0, "content": "chunk one"},
                {"chunk_index": 1, "content": "chunk two"},
            ]

        resp = client.get("/api/search/document/aemo/report.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "aemo"
        assert data["filename"] == "report.md"
        assert data["chunk_count"] == 2

    def test_invalid_source_with_traversal(self, client):
        """Source containing '..' should be rejected."""
        resp = client.get("/api/search/document/../etc/report.md")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Invalid source"

    def test_invalid_filename_with_traversal(self, client):
        """Filename containing '..' should be rejected."""
        resp = client.get("/api/search/document/aemo/../../etc/passwd")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Invalid filename"

    def test_pgvector_not_configured(self, client, app):
        """When pgvector is not configured, should return 503."""
        with app.app_context():
            from app.web.blueprints.search import container as search_container
            search_container.pgvector_client.is_configured.return_value = False

        resp = client.get("/api/search/document/aemo/report.md")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "pgvector not configured"

        # Reset for other tests
        with app.app_context():
            from app.web.blueprints.search import container as search_container
            search_container.pgvector_client.is_configured.return_value = True
