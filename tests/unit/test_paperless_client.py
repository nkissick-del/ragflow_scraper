"""Tests for PaperlessClient."""

import pytest
from unittest.mock import Mock, patch

from app.services.paperless_client import PaperlessClient


@pytest.fixture
def client():
    """Create test client with mocked session."""
    return PaperlessClient(url="http://localhost:8000", token="test-token")


class TestClientInitialization:
    """Test client initialization."""

    def test_init_with_explicit_params(self):
        """Should initialize with provided parameters."""
        client = PaperlessClient(url="http://test:8000/", token="my-token")
        assert client.url == "http://test:8000"  # Trailing slash stripped
        assert client.token == "my-token"
        assert client.is_configured is True
        assert client._correspondent_cache == {}
        assert client._tag_cache == {}

    def test_init_strips_trailing_slash(self):
        """Should strip trailing slash from URL."""
        client = PaperlessClient(url="http://test:8000///", token="token")
        assert client.url == "http://test:8000"

    def test_is_configured_false_without_url(self):
        """Should return False when URL is missing."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = "token"
            client = PaperlessClient()
            assert client.is_configured is False

    def test_is_configured_false_without_token(self):
        """Should return False when token is missing."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = "http://test:8000"
            mock_config.PAPERLESS_API_TOKEN = None
            client = PaperlessClient()
            assert client.is_configured is False


class TestFetchCorrespondents:
    """Test correspondent fetching."""

    def test_fetch_correspondents_success(self, client):
        """Should parse paginated response correctly."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "AEMO"},
                {"id": 2, "name": "Guardian"},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_correspondents()

        assert result == {"AEMO": 1, "Guardian": 2}

    def test_fetch_correspondents_with_pagination(self, client):
        """Should handle multiple pages."""
        page1 = Mock()
        page1.raise_for_status = Mock()
        page1.json.return_value = {
            "results": [{"id": 1, "name": "Org1"}],
            "next": "http://localhost:8000/api/correspondents/?page=2",
        }

        page2 = Mock()
        page2.raise_for_status = Mock()
        page2.json.return_value = {
            "results": [{"id": 2, "name": "Org2"}],
            "next": None,
        }

        with patch.object(client.session, "get", side_effect=[page1, page2]):
            result = client._fetch_correspondents()

        assert result == {"Org1": 1, "Org2": 2}

    def test_fetch_correspondents_empty(self, client):
        """Should return empty dict when no correspondents exist."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_correspondents()

        assert result == {}

    def test_fetch_correspondents_not_configured(self):
        """Should return empty dict when not configured."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = None
            client = PaperlessClient(url=None, token=None)
            result = client._fetch_correspondents()
            assert result == {}


class TestGetOrCreateCorrespondent:
    """Test correspondent lookup/creation."""

    def test_returns_cached_id(self, client):
        """Should return cached ID without API call."""
        client._correspondent_cache = {"AEMO": 42}
        client._correspondent_cache_populated = True

        with patch.object(client.session, "get") as mock_get:
            result = client.get_or_create_correspondent("AEMO")

        assert result == 42
        mock_get.assert_not_called()

    def test_fetches_and_returns_existing(self, client):
        """Should fetch correspondents and return existing ID."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 5, "name": "AEMO"}],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_or_create_correspondent("AEMO")

        assert result == 5
        assert client._correspondent_cache["AEMO"] == 5

    def test_creates_new_correspondent(self, client):
        """Should create new correspondent when not found."""
        # Mock fetch returning empty
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        # Mock create returning new ID
        create_response = Mock()
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 99, "name": "NewOrg"}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(client.session, "post", return_value=create_response):
                result = client.get_or_create_correspondent("NewOrg")

        assert result == 99
        assert client._correspondent_cache["NewOrg"] == 99

    def test_returns_none_on_creation_failure(self, client):
        """Should return None when creation fails."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session, "post", side_effect=Exception("API Error")
            ):
                result = client.get_or_create_correspondent("FailOrg")

        assert result is None

    def test_returns_none_for_empty_name(self, client):
        """Should return None for empty name."""
        result = client.get_or_create_correspondent("")
        assert result is None


class TestFetchTags:
    """Test tag fetching."""

    def test_fetch_tags_success(self, client):
        """Should parse paginated response correctly."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 10, "name": "Report"},
                {"id": 20, "name": "Energy"},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_tags()

        assert result == {"Report": 10, "Energy": 20}

    def test_fetch_tags_with_pagination(self, client):
        """Should handle multiple pages of tags."""
        page1 = Mock()
        page1.raise_for_status = Mock()
        page1.json.return_value = {
            "results": [{"id": 10, "name": "Report"}],
            "next": "http://localhost:8000/api/tags/?page=2",
        }

        page2 = Mock()
        page2.raise_for_status = Mock()
        page2.json.return_value = {
            "results": [{"id": 20, "name": "Energy"}],
            "next": None,
        }

        with patch.object(client.session, "get", side_effect=[page1, page2]):
            result = client._fetch_tags()

        assert result == {"Report": 10, "Energy": 20}

    def test_fetch_tags_not_configured(self):
        """Should return empty dict when not configured."""
        client = PaperlessClient(url=None, token=None)
        result = client._fetch_tags()
        assert result == {}


class TestGetOrCreateTags:
    """Test tag lookup/creation."""

    def test_returns_cached_ids(self, client):
        """Should return cached IDs without API call."""
        client._tag_cache = {"Report": 10, "Energy": 20}
        client._tag_cache_populated = True

        with patch.object(client.session, "get") as mock_get:
            result = client.get_or_create_tags(["Report", "Energy"])

        assert result == [10, 20]
        mock_get.assert_not_called()

    def test_creates_missing_tags(self, client):
        """Should create tags that don't exist."""
        # Pre-populate cache with one tag
        client._tag_cache = {"Existing": 1}

        create_response = Mock()
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 99, "name": "NewTag"}

        with patch.object(client.session, "post", return_value=create_response):
            result = client.get_or_create_tags(["Existing", "NewTag"])

        assert result == [1, 99]
        assert client._tag_cache["NewTag"] == 99

    def test_returns_empty_for_empty_list(self, client):
        """Should return empty list for empty input."""
        result = client.get_or_create_tags([])
        assert result == []

    def test_skips_empty_names(self, client):
        """Should skip empty tag names."""
        client._tag_cache = {"Valid": 1}
        result = client.get_or_create_tags(["Valid", "", None])
        assert result == [1]

    def test_handles_creation_failure(self, client):
        """Should skip tags that fail to create."""
        client._tag_cache = {"Good": 1}

        with patch.object(client.session, "post", side_effect=Exception("API Error")):
            result = client.get_or_create_tags(["Good", "FailTag"])

        assert result == [1]  # Only cached tag returned


class TestPostDocumentWithLookups:
    """Test post_document with correspondent/tag resolution."""

    def test_resolves_string_correspondent(self, client, tmp_path):
        """Should resolve string correspondent to ID."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        # Mock correspondent lookup
        client._correspondent_cache = {"AEMO": 42}
        client._correspondent_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "0123456789abcdef0123456789abcdef"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            result = client.post_document(
                file_path=test_file,
                title="Test Doc",
                correspondent="AEMO",
            )

        assert result == "0123456789abcdef0123456789abcdef"
        # Verify correspondent ID was sent
        call_args = mock_post.call_args
        assert call_args[1]["data"]["correspondent"] == 42

    def test_resolves_string_tags(self, client, tmp_path):
        """Should resolve string tags to IDs."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        # Mock tag lookup
        client._tag_cache = {"Report": 10, "Energy": 20}
        client._tag_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "0123456789abcdef0123456789abcde2"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            result = client.post_document(
                file_path=test_file,
                title="Test Doc",
                tags=["Report", "Energy"],
            )

        assert result == "0123456789abcdef0123456789abcde2"
        # Verify tag IDs were sent
        call_args = mock_post.call_args
        assert set(call_args[1]["data"]["tags"]) == {10, 20}

    def test_handles_mixed_tag_types(self, client, tmp_path):
        """Should handle mix of string and numeric tags."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        client._tag_cache = {"StringTag": 30}

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "0123456789abcdef0123456789abcde3"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            client.post_document(
                file_path=test_file,
                title="Test Doc",
                tags=[10, "20", "StringTag"],  # int, numeric string, name
            )

        call_args = mock_post.call_args
        assert set(call_args[1]["data"]["tags"]) == {10, 20, 30}

    def test_continues_upload_on_lookup_failure(self, client, tmp_path):
        """Should still upload document if lookup fails."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        # Mock failed correspondent lookup
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        upload_response = Mock()
        upload_response.raise_for_status = Mock()
        upload_response.headers = {"Content-Type": "text/plain"}
        upload_response.text = "0123456789abcdef0123456789abcde4"

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session,
                "post",
                side_effect=[Exception("Create failed"), upload_response],
            ):
                result = client.post_document(
                    file_path=test_file,
                    title="Test Doc",
                    correspondent="UnknownOrg",
                )

        # Upload should still succeed, just without correspondent
        assert result == "0123456789abcdef0123456789abcde4"


class TestFetchCustomFields:
    """Test custom field fetching."""

    def test_fetch_custom_fields_success(self, client):
        """Should parse paginated response correctly."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Original URL"},
                {"id": 2, "name": "Scraped Date"},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_custom_fields()

        assert result == {"Original URL": 1, "Scraped Date": 2}

    def test_fetch_custom_fields_with_pagination(self, client):
        """Should handle multiple pages."""
        page1 = Mock()
        page1.raise_for_status = Mock()
        page1.json.return_value = {
            "results": [{"id": 1, "name": "Original URL"}],
            "next": "http://localhost:8000/api/custom_fields/?page=2",
        }

        page2 = Mock()
        page2.raise_for_status = Mock()
        page2.json.return_value = {
            "results": [{"id": 2, "name": "Scraped Date"}],
            "next": None,
        }

        with patch.object(client.session, "get", side_effect=[page1, page2]):
            result = client._fetch_custom_fields()

        assert result == {"Original URL": 1, "Scraped Date": 2}

    def test_fetch_custom_fields_empty(self, client):
        """Should return empty dict when no custom fields exist."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_custom_fields()

        assert result == {}

    def test_fetch_custom_fields_not_configured(self):
        """Should return empty dict when not configured."""
        client = PaperlessClient(url=None, token=None)
        result = client._fetch_custom_fields()
        assert result == {}


class TestGetOrCreateCustomField:
    """Test custom field lookup/creation."""

    def test_returns_cached_id(self, client):
        """Should return cached ID without API call."""
        client._custom_field_cache = {"Original URL": 42}
        client._custom_field_cache_populated = True

        with patch.object(client.session, "get") as mock_get:
            result = client.get_or_create_custom_field("Original URL", "url")

        assert result == 42
        mock_get.assert_not_called()

    def test_fetches_and_returns_existing(self, client):
        """Should fetch custom fields and return existing ID."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [{"id": 5, "name": "Original URL"}],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_or_create_custom_field("Original URL", "url")

        assert result == 5
        assert client._custom_field_cache["Original URL"] == 5

    def test_creates_new_custom_field(self, client):
        """Should create new custom field when not found."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        create_response = Mock()
        create_response.status_code = 201
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {
            "id": 99,
            "name": "Page Count",
            "data_type": "integer",
        }

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(client.session, "post", return_value=create_response):
                result = client.get_or_create_custom_field("Page Count", "integer")

        assert result == 99
        assert client._custom_field_cache["Page Count"] == 99

    def test_handles_409_conflict(self, client):
        """Should re-fetch on 409 conflict."""
        fetch_empty = Mock()
        fetch_empty.raise_for_status = Mock()
        fetch_empty.json.return_value = {"results": [], "next": None}

        conflict_response = Mock()
        conflict_response.status_code = 409

        fetch_with_field = Mock()
        fetch_with_field.raise_for_status = Mock()
        fetch_with_field.json.return_value = {
            "results": [{"id": 7, "name": "Original URL"}],
            "next": None,
        }

        with patch.object(
            client.session, "get", side_effect=[fetch_empty, fetch_with_field]
        ):
            with patch.object(client.session, "post", return_value=conflict_response):
                result = client.get_or_create_custom_field("Original URL", "url")

        assert result == 7

    def test_returns_none_on_creation_failure(self, client):
        """Should return None when creation fails."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session, "post", side_effect=Exception("API Error")
            ):
                result = client.get_or_create_custom_field("FailField", "string")

        assert result is None

    def test_returns_none_for_empty_name(self, client):
        """Should return None for empty name."""
        result = client.get_or_create_custom_field("", "string")
        assert result is None


class TestSetCustomFields:
    """Test setting custom fields on a document."""

    def test_successful_patch(self, client):
        """Should PATCH document with resolved custom field IDs."""
        client._custom_field_cache = {"Original URL": 1, "Page Count": 2}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"url": "https://example.com/doc.pdf", "page_count": 42}

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        mock_patch.assert_called_once()
        call_args = mock_patch.call_args
        assert call_args[0][0] == "http://localhost:8000/api/documents/123/"
        payload = call_args[1]["json"]["custom_fields"]
        # Should have 2 fields
        assert len(payload) == 2
        field_ids = {item["field"] for item in payload}
        assert field_ids == {1, 2}

    def test_skips_none_and_empty_values(self, client):
        """Should skip None and empty string values."""
        client._custom_field_cache = {"Original URL": 1, "Scraped Date": 2}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"url": "https://example.com", "scraped_at": None, "page_count": ""}

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        assert len(payload) == 1
        assert payload[0]["field"] == 1

    def test_empty_metadata_returns_true(self, client):
        """Should return True for empty metadata."""
        result = client.set_custom_fields(123, {})
        assert result is True

    def test_none_metadata_returns_true(self, client):
        """Should return True for None metadata."""
        result = client.set_custom_fields(123, None)
        assert result is True

    def test_patch_failure_returns_false(self, client):
        """Should return False when PATCH fails."""
        client._custom_field_cache = {"Original URL": 1}
        client._custom_field_cache_populated = True

        metadata = {"url": "https://example.com"}

        with patch.object(
            client.session, "patch", side_effect=Exception("PATCH failed")
        ):
            result = client.set_custom_fields(123, metadata)

        assert result is False

    def test_only_maps_known_fields(self, client):
        """Should ignore metadata keys not in CUSTOM_FIELD_MAPPING."""
        client._custom_field_cache = {"Original URL": 1}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {
            "url": "https://example.com",
            "unknown_key": "should be ignored",
            "another_unknown": 999,
        }

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        assert len(payload) == 1
        assert payload[0]["field"] == 1

    def test_coerces_integer_types(self, client):
        """Should coerce string values to int for integer fields."""
        client._custom_field_cache = {"Page Count": 1, "File Size": 2}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"page_count": "42", "file_size": "1024"}

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        values = {item["field"]: item["value"] for item in payload}
        assert values[1] == 42
        assert values[2] == 1024

    def test_skips_non_numeric_integer_field(self, client):
        """Should skip integer fields with non-numeric values."""
        client._custom_field_cache = {"Page Count": 1}
        client._custom_field_cache_populated = True

        metadata = {"page_count": "not-a-number"}

        with patch.object(client.session, "patch") as mock_patch:
            result = client.set_custom_fields(123, metadata)

        # No fields to set, so returns True without PATCH
        assert result is True
        mock_patch.assert_not_called()
