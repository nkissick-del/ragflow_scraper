"""Integration tests for input validation tightening on settings forms."""

import pytest
from unittest.mock import patch, MagicMock

from app.config import Config
from app.web import create_app


@pytest.fixture
def app():
    mock_container = MagicMock()
    mock_container.settings.get_all.return_value = {}
    mock_container.settings.get.return_value = ""
    patches = [
        patch("app.web.blueprints.settings.container", mock_container),
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
        application = create_app()
        application.config["TESTING"] = True
        application.config["WTF_CSRF_ENABLED"] = False
        application.config["RATELIMIT_ENABLED"] = False
        yield application
    finally:
        for p in reversed(started):
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()


class TestURLLengthValidation:

    def test_oversized_url_rejected(self, client):
        """URL exceeding 2048 chars should be rejected."""
        long_url = "http://example.com/" + "a" * 2040
        resp = client.post("/settings/services", data={
            "gotenberg_url": long_url,
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data

    def test_normal_url_accepted(self, client):
        """URL within limits should be accepted."""
        resp = client.post("/settings/services", data={
            "gotenberg_url": "http://localhost:3000",
        })
        assert resp.status_code == 200
        assert b"saved" in resp.data.lower() or b"success" in resp.data.lower()

    def test_oversized_pgvector_url_rejected(self, client):
        """pgvector URL exceeding 2048 chars should be rejected."""
        long_url = "postgresql://user:pass@host/" + "a" * 2030
        resp = client.post("/settings/services", data={
            "pgvector_url": long_url,
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data


class TestTimeoutRangeValidation:

    def test_flaresolverr_timeout_out_of_range(self, client):
        """FlareSolverr timeout > 600 should be rejected."""
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "999",
            "max_timeout": "1000",
        })
        assert resp.status_code == 200
        assert b"between 1 and 600" in resp.data

    def test_flaresolverr_max_below_timeout(self, client):
        """FlareSolverr max_timeout < timeout should be rejected."""
        resp = client.post("/settings/flaresolverr", data={
            "timeout": "120",
            "max_timeout": "60",
        })
        assert resp.status_code == 200
        assert b"greater than or equal" in resp.data

    def test_scraping_timeout_out_of_range(self, client):
        """Scraping timeout > 600 should be rejected."""
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "2",
            "default_timeout": "999",
            "default_retry_attempts": "3",
        })
        assert resp.status_code == 200
        assert b"between 1 and 600" in resp.data

    def test_scraping_retry_out_of_range(self, client):
        """Retry attempts > 10 should be rejected."""
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "2",
            "default_timeout": "60",
            "default_retry_attempts": "50",
        })
        assert resp.status_code == 200
        assert b"between 0 and 10" in resp.data

    def test_scraping_delay_out_of_range(self, client):
        """Request delay > 60 should be rejected."""
        resp = client.post("/settings/scraping", data={
            "default_request_delay": "120",
            "default_timeout": "60",
            "default_retry_attempts": "3",
        })
        assert resp.status_code == 200
        assert b"between 0 and 60" in resp.data


class TestFieldLengthValidation:

    def test_oversized_embedding_model_rejected(self, client):
        """Embedding model name > 255 chars in ragflow settings should be rejected."""
        resp = client.post("/settings/ragflow", data={
            "default_embedding_model": "m" * 300,
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data

    def test_oversized_filename_template_rejected(self, client):
        """Filename template > 1024 chars should be rejected."""
        resp = client.post("/settings/pipeline", data={
            "filename_template": "x" * 1100,
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data

    def test_oversized_pipeline_embedding_model_rejected(self, client):
        """Pipeline embedding model > 255 chars should be rejected."""
        resp = client.post("/settings/pipeline", data={
            "embedding_model": "m" * 300,
        })
        assert resp.status_code == 200
        assert b"exceeds maximum length" in resp.data


class TestChunkTokenValidation:

    def test_chunk_max_tokens_out_of_range(self, client):
        """chunk_max_tokens > 8192 should be rejected."""
        resp = client.post("/settings/pipeline", data={
            "chunk_max_tokens": "10000",
        })
        assert resp.status_code == 200
        assert b"between 1 and 8192" in resp.data

    def test_chunk_overlap_out_of_range(self, client):
        """chunk_overlap_tokens > 4096 should be rejected."""
        resp = client.post("/settings/pipeline", data={
            "chunk_overlap_tokens": "5000",
        })
        assert resp.status_code == 200
        assert b"between 0 and 4096" in resp.data

    def test_chunk_zero_accepted(self, client):
        """chunk_max_tokens=0 (use default) should be accepted."""
        resp = client.post("/settings/pipeline", data={
            "chunk_max_tokens": "0",
            "chunk_overlap_tokens": "0",
        })
        assert resp.status_code == 200
        assert b"success" in resp.data.lower() or b"saved" in resp.data.lower()


class TestScraperFieldLengthValidation:

    def test_oversized_embedding_model_in_scraper_ragflow(self, client):
        """Embedding model > 255 chars in scraper ragflow settings should be rejected."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_cls:
            mock_cls.return_value = MagicMock()
            resp = client.post("/scrapers/test_scraper/ragflow", data={
                "embedding_model": "m" * 300,
            })
            assert resp.status_code == 400
            assert b"exceeds maximum length" in resp.data

    def test_oversized_pipeline_id_in_scraper_ragflow(self, client):
        """Pipeline ID > 255 chars in scraper ragflow settings should be rejected."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_cls:
            mock_cls.return_value = MagicMock()
            resp = client.post("/scrapers/test_scraper/ragflow", data={
                "pipeline_id": "p" * 300,
            })
            assert resp.status_code == 400
            assert b"exceeds maximum length" in resp.data

    def test_oversized_dataset_id_in_scraper_ragflow(self, client):
        """Dataset ID > 255 chars in scraper ragflow settings should be rejected."""
        with patch("app.web.blueprints.scrapers.ScraperRegistry.get_scraper_class") as mock_cls:
            mock_cls.return_value = MagicMock()
            resp = client.post("/scrapers/test_scraper/ragflow", data={
                "dataset_id": "d" * 300,
            })
            assert resp.status_code == 400
            assert b"exceeds maximum length" in resp.data
