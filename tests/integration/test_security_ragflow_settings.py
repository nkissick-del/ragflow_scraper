"""Integration tests for RAGFlow settings input validation."""

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app

SCRAPER = "aemo"  # Use a real registered scraper


@pytest.fixture
def app():
    """Create test Flask app with CSRF disabled for validation testing."""
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.state_tracker.return_value.get_all_status.return_value = {}

    patches = [
        patch("app.web.blueprints.scrapers.container", mock_container),
        patch("app.web.blueprints.scrapers.job_queue"),
        patch("app.web.blueprints.api_scrapers.job_queue"),
        patch("app.web.helpers.container", mock_container),
        patch("app.web.helpers.job_queue"),
        patch.object(Config, "BASIC_AUTH_ENABLED", False),
    ]
    started = []
    try:
        for p in patches:
            p.start()
            started.append(p)
        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        yield app
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestRAGFlowSettingsValidation:
    """Test allowlist/regex validation on RAGFlow settings endpoint."""

    def test_valid_chunk_method_accepted(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"chunk_method": "naive", f"ingestion_mode_{SCRAPER}": "builtin"},
        )
        assert response.status_code == 200
        assert b"Saved" in response.data

    def test_invalid_chunk_method_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"chunk_method": "<script>alert(1)</script>"},
        )
        assert response.status_code == 400
        assert b"Invalid chunk method" in response.data

    def test_valid_pdf_parser_accepted(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"pdf_parser": "DeepDOC", f"ingestion_mode_{SCRAPER}": "builtin"},
        )
        assert response.status_code == 200
        assert b"Saved" in response.data

    def test_invalid_pdf_parser_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"pdf_parser": "NotARealParser"},
        )
        assert response.status_code == 400
        assert b"Invalid PDF parser" in response.data

    def test_valid_ingestion_mode_accepted(self, client):
        for mode in ("builtin", "custom"):
            response = client.post(
                f"/scrapers/{SCRAPER}/ragflow",
                data={f"ingestion_mode_{SCRAPER}": mode},
            )
            assert response.status_code == 200

    def test_invalid_ingestion_mode_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={f"ingestion_mode_{SCRAPER}": "malicious"},
        )
        assert response.status_code == 400
        assert b"Invalid ingestion mode" in response.data

    def test_valid_embedding_model_accepted(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"embedding_model": "org/model:v1@provider"},
        )
        assert response.status_code == 200

    def test_invalid_embedding_model_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"embedding_model": "model; DROP TABLE users;"},
        )
        assert response.status_code == 400
        assert b"Invalid embedding model format" in response.data

    def test_valid_pipeline_id_accepted(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"pipeline_id": "my-pipeline_123"},
        )
        assert response.status_code == 200

    def test_invalid_pipeline_id_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"pipeline_id": "../../../etc/passwd"},
        )
        assert response.status_code == 400
        assert b"Invalid pipeline ID format" in response.data

    def test_valid_dataset_id_accepted(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"dataset_id": "dataset-abc_123"},
        )
        assert response.status_code == 200

    def test_invalid_dataset_id_rejected(self, client):
        response = client.post(
            f"/scrapers/{SCRAPER}/ragflow",
            data={"dataset_id": "id with spaces!"},
        )
        assert response.status_code == 400
        assert b"Invalid dataset ID format" in response.data
