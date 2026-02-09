"""Tests for PaperlessClient query methods (get_documents, download_document, get_scraper_document_urls)."""

import pytest
from unittest.mock import Mock, patch

from app.services.paperless_client import PaperlessClient


@pytest.fixture
def client():
    """Create test client with mocked session."""
    return PaperlessClient(url="http://localhost:8000", token="test-token")


class TestGetDocuments:
    """Test get_documents method."""

    def test_returns_empty_when_not_configured(self):
        """Should return empty list when client is not configured."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = None
            c = PaperlessClient()
            assert c.get_documents() == []

    def test_fetches_single_page(self, client):
        """Should fetch documents from a single page."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "title": "Doc 1"},
                {"id": 2, "title": "Doc 2"},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_documents()

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_fetches_multiple_pages(self, client):
        """Should follow pagination."""
        page1 = Mock()
        page1.raise_for_status = Mock()
        page1.json.return_value = {
            "results": [{"id": 1, "title": "Doc 1"}],
            "next": "http://localhost:8000/api/documents/?page=2",
        }

        page2 = Mock()
        page2.raise_for_status = Mock()
        page2.json.return_value = {
            "results": [{"id": 2, "title": "Doc 2"}],
            "next": None,
        }

        with patch.object(client.session, "get", side_effect=[page1, page2]):
            result = client.get_documents()

        assert len(result) == 2

    def test_passes_filters(self, client):
        """Should pass filter params to the request."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            client.get_documents(filters={"correspondent__id": 5})

        # Check that correspondent__id was included in params
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("correspondent__id") == 5

    def test_returns_partial_on_error(self, client):
        """Should return partial results on error."""
        page1 = Mock()
        page1.raise_for_status = Mock()
        page1.json.return_value = {
            "results": [{"id": 1, "title": "Doc 1"}],
            "next": "http://localhost:8000/api/documents/?page=2",
        }

        page2 = Mock()
        page2.raise_for_status.side_effect = Exception("Network error")

        with patch.object(client.session, "get", side_effect=[page1, page2]):
            result = client.get_documents()

        assert len(result) == 1


class TestDownloadDocument:
    """Test download_document method."""

    def test_returns_none_when_not_configured(self):
        """Should return None when not configured."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = None
            c = PaperlessClient()
            assert c.download_document(1) is None

    def test_downloads_successfully(self, client):
        """Should return file bytes."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.content = b"%PDF-1.4 test content"

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.download_document(42)

        assert result == b"%PDF-1.4 test content"

    def test_returns_none_on_error(self, client):
        """Should return None on HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.download_document(999)

        assert result is None


class TestGetScraperDocumentUrls:
    """Test get_scraper_document_urls method."""

    def test_returns_empty_when_not_configured(self):
        """Should return empty dict when not configured."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = None
            c = PaperlessClient()
            assert c.get_scraper_document_urls("aemo") == {}

    def test_matches_by_scraper_name_field(self, client):
        """Should match documents by Scraper Name custom field."""
        # Pre-populate caches
        client._correspondent_cache = {"aemo": 1}
        client._correspondent_cache_populated = True
        client._custom_field_cache = {"Original URL": 10, "Scraper Name": 11}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 100,
                    "custom_fields": [
                        {"field": 10, "value": "https://example.com/doc1.pdf"},
                        {"field": 11, "value": "aemo"},
                    ],
                },
                {
                    "id": 101,
                    "custom_fields": [
                        {"field": 10, "value": "https://example.com/doc2.pdf"},
                        {"field": 11, "value": "guardian"},  # different scraper
                    ],
                },
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_scraper_document_urls("aemo")

        assert result == {"https://example.com/doc1.pdf": 100}

    def test_fallback_to_correspondent_when_no_scraper_field(self, client):
        """Should fall back to correspondent match when Scraper Name is absent."""
        client._correspondent_cache = {"aemo": 1}
        client._correspondent_cache_populated = True
        client._custom_field_cache = {"Original URL": 10, "Scraper Name": 11}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 200,
                    "custom_fields": [
                        {"field": 10, "value": "https://example.com/old-doc.pdf"},
                        # No Scraper Name field — pre-existing doc
                    ],
                },
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_scraper_document_urls("aemo")

        # Should match because doc came from aemo correspondent and has no scraper_name field
        assert result == {"https://example.com/old-doc.pdf": 200}

    def test_skips_docs_without_url(self, client):
        """Should skip documents that don't have an Original URL custom field."""
        client._correspondent_cache = {"aemo": 1}
        client._correspondent_cache_populated = True
        client._custom_field_cache = {"Original URL": 10, "Scraper Name": 11}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 300,
                    "custom_fields": [
                        {"field": 11, "value": "aemo"},
                        # No Original URL field
                    ],
                },
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_scraper_document_urls("aemo")

        assert result == {}


class TestResolveCustomFieldName:
    """Test _resolve_custom_field_name helper."""

    def test_resolves_known_field(self, client):
        """Should resolve a cached field ID to name."""
        client._custom_field_cache = {"Original URL": 10, "Scraper Name": 11}
        client._custom_field_cache_populated = True

        assert client._resolve_custom_field_name(10) == "Original URL"
        assert client._resolve_custom_field_name(11) == "Scraper Name"

    def test_returns_none_for_unknown_field(self, client):
        """Should return None for unknown field IDs."""
        client._custom_field_cache = {"Original URL": 10}
        client._custom_field_cache_populated = True

        assert client._resolve_custom_field_name(999) is None

    def test_returns_none_for_none_input(self, client):
        """Should return None when field_id is None."""
        assert client._resolve_custom_field_name(None) is None
