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
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = None
            mock_config.PAPERLESS_API_TOKEN = None
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
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = ""
            mock_config.PAPERLESS_API_TOKEN = ""
            client = PaperlessClient(url=None, token=None)
        assert not client.is_configured
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
        client._custom_field_cache = {"Original URL": 1, "Scraper Name": 2}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"url": "https://example.com/doc.pdf", "scraper_name": "test"}

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

        metadata = {"url": "https://example.com", "scraped_at": None, "scraper_name": ""}

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

    def test_string_field_values_passed_as_is(self, client):
        """Should pass string values without coercion."""
        client._custom_field_cache = {"Author": 1, "Language": 2}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"author": "Jane Doe", "language": "en"}

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        values = {item["field"]: item["value"] for item in payload}
        assert values[1] == "Jane Doe"
        assert values[2] == "en"


class TestSetCustomFieldsTruncation:
    """Test that string custom fields are truncated to 128 chars."""

    def test_long_string_truncated(self, client):
        """String values over 128 chars should be truncated with ellipsis."""
        client._custom_field_cache = {"Description": 8}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        long_desc = "A" * 200
        metadata = {"description": long_desc}

        with patch.object(
            client.session, "patch", return_value=mock_response
        ) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        desc_value = payload[0]["value"]
        assert len(desc_value) == 128
        assert desc_value.endswith("...")

    def test_short_string_not_truncated(self, client):
        """String values under 128 chars should not be modified."""
        client._custom_field_cache = {"Description": 8}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {"description": "Short description"}

        with patch.object(
            client.session, "patch", return_value=mock_response
        ) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        assert payload[0]["value"] == "Short description"


class TestRetryAdapter:
    """Test that PaperlessClient session has retry adapter configured."""

    def test_session_has_retry_adapter(self, client):
        """Session should have retry adapters with correct configuration."""
        # Check both http and https adapters
        for prefix in ("http://", "https://"):
            adapter = client.session.get_adapter(prefix + "example.com")
            retry = adapter.max_retries

            assert retry.total == 3
            assert 429 in retry.status_forcelist
            assert 500 in retry.status_forcelist
            assert 502 in retry.status_forcelist
            assert 503 in retry.status_forcelist
            assert 504 in retry.status_forcelist
            # 409 should NOT be in forcelist (existing conflict handling)
            assert 409 not in retry.status_forcelist
            # Only GET is retried to avoid duplicate uploads on POST
            assert set(retry.allowed_methods) == {"GET"}


# ── Additional coverage tests ─────────────────────────────────────────


class TestVerifyDocumentEdgeCases:
    """Test verify_document_exists() edge cases."""

    def test_not_configured_returns_none(self):
        """Should return None when client is not configured."""
        client = PaperlessClient(url=None, token=None)
        result = client.verify_document_exists("some-task-id")
        assert result is None

    def test_invalid_task_id_format(self, client):
        """Should return None for invalid task_id format."""
        result = client.get_task_status("not-a-valid-uuid")
        assert result is None

    def test_success_with_no_related_document(self, client):
        """Should return None when SUCCESS but no related_document."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = [
            {"task_id": "12345678-1234-1234-1234-123456789abc", "status": "SUCCESS", "related_document": None}
        ]

        with patch.object(client.session, "get", return_value=mock_resp):
            with patch("time.sleep"):
                result = client.verify_document_exists(
                    "12345678-1234-1234-1234-123456789abc", timeout=1, poll_interval=0.1
                )

        assert result is None

    def test_failure_status_returns_none(self, client):
        """Should return None immediately on FAILURE status."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = [
            {"task_id": "12345678-1234-1234-1234-123456789abc", "status": "FAILURE"}
        ]

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.verify_document_exists(
                "12345678-1234-1234-1234-123456789abc", timeout=5, poll_interval=0.1
            )

        assert result is None

    def test_success_with_document_id(self, client):
        """Should return document ID on SUCCESS with related_document."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = [
            {"task_id": "12345678-1234-1234-1234-123456789abc", "status": "SUCCESS", "related_document": 42}
        ]

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.verify_document_exists(
                "12345678-1234-1234-1234-123456789abc", timeout=5, poll_interval=0.1
            )

        assert result == "42"


class TestSetCustomFieldsEdgeCases:
    """Test set_custom_fields() edge cases."""

    def test_not_configured_with_metadata_returns_false(self):
        """Should return False when not configured but metadata provided."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_URL = ""
            mock_config.PAPERLESS_API_TOKEN = ""
            client = PaperlessClient(url=None, token=None)
            assert not client.is_configured
            result = client.set_custom_fields(123, {"url": "https://example.com"})
            assert result is False

    def test_string_field_skips_none(self, client):
        """Should skip fields with None values."""
        client._custom_field_cache = {"Author": 1}
        client._custom_field_cache_populated = True

        metadata = {"author": None}

        result = client.set_custom_fields(123, metadata)
        assert result is True  # No fields to set

    def test_no_matching_fields_returns_true(self, client):
        """Should return True when no fields match CUSTOM_FIELD_MAPPING."""
        client._custom_field_cache_populated = True

        metadata = {"unrelated_key": "value"}

        result = client.set_custom_fields(123, metadata)
        assert result is True


class TestCorrespondentCacheBehavior:
    """Test _ensure_correspondent() cache behavior."""

    def test_409_conflict_refetches(self, client):
        """Should re-fetch on 409 conflict during creation."""
        # Ensure cache is populated (empty)
        fetch_empty = Mock()
        fetch_empty.raise_for_status = Mock()
        fetch_empty.json.return_value = {"results": [], "next": None}

        conflict_resp = Mock()
        conflict_resp.status_code = 409

        fetch_after = Mock()
        fetch_after.raise_for_status = Mock()
        fetch_after.json.return_value = {
            "results": [{"id": 77, "name": "ConflictOrg"}], "next": None
        }

        with patch.object(
            client.session, "get", side_effect=[fetch_empty, fetch_after]
        ):
            with patch.object(client.session, "post", return_value=conflict_resp):
                result = client.get_or_create_correspondent("ConflictOrg")

        assert result == 77


class TestGetOrCreateTagsMixed:
    """Test get_or_create_tags with mixed existing/new tags."""

    def test_mixed_existing_and_new_tags(self, client):
        """Should handle mix of cached and new tags."""
        # First fetch populates cache with one tag
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {
            "results": [{"id": 10, "name": "Existing"}], "next": None
        }

        # Creation of new tag
        create_response = Mock()
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 20, "name": "Brand New"}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(client.session, "post", return_value=create_response):
                result = client.get_or_create_tags(["Existing", "Brand New"])

        assert result == [10, 20]

    def test_tag_creation_failure_continues(self, client):
        """Should continue processing remaining tags after a failure."""
        client._tag_cache = {"Good": 1}
        client._tag_cache_populated = True

        create_ok = Mock()
        create_ok.raise_for_status = Mock()
        create_ok.json.return_value = {"id": 99, "name": "AlsoGood"}

        with patch.object(
            client.session, "post", side_effect=[Exception("fail"), create_ok]
        ):
            result = client.get_or_create_tags(["Good", "FailTag", "AlsoGood"])

        assert 1 in result
        assert 99 in result


class TestPostDocumentEdgeCases:
    """Test post_document with edge cases."""

    def test_post_document_not_configured(self):
        """Should return None when not configured."""
        client = PaperlessClient(url=None, token=None)
        result = client.post_document("/tmp/test.pdf", title="Test")
        assert result is None

    def test_post_document_file_not_found(self, client):
        """Should return None when file does not exist."""
        result = client.post_document("/nonexistent/path.pdf", title="Test")
        assert result is None

    def test_post_with_numeric_string_correspondent(self, client, tmp_path):
        """Should convert numeric string correspondent to int."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "12345678-1234-1234-1234-123456789abc"

        with patch.object(client.session, "post", return_value=mock_response) as mock_post:
            result = client.post_document(
                file_path=test_file, title="Test", correspondent="42"
            )

        assert result == "12345678-1234-1234-1234-123456789abc"
        call_args = mock_post.call_args
        assert call_args[1]["data"]["correspondent"] == 42

    def test_post_with_integer_correspondent(self, client, tmp_path):
        """Should pass integer correspondent directly."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "12345678-1234-1234-1234-123456789ab2"

        with patch.object(client.session, "post", return_value=mock_response) as mock_post:
            result = client.post_document(
                file_path=test_file, title="Test", correspondent=99
            )

        assert result == "12345678-1234-1234-1234-123456789ab2"
        call_args = mock_post.call_args
        assert call_args[1]["data"]["correspondent"] == 99


class TestTaskIdExtraction:
    """Test _extract_task_id_from_response and _validate_task_id."""

    def test_extract_json_dict_response(self, client):
        """Should extract task_id from JSON dict response."""
        mock_resp = Mock()
        mock_resp.text = '{"task_id": "abc-123"}'
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"task_id": "abc-123"}

        result = client._extract_task_id_from_response(mock_resp)
        assert result == "abc-123"

    def test_extract_json_list_response(self, client):
        """Should extract task_id from JSON list response."""
        mock_resp = Mock()
        mock_resp.text = '[{"task_id": "abc-123"}]'
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = [{"task_id": "abc-123"}]

        result = client._extract_task_id_from_response(mock_resp)
        assert result == "abc-123"

    def test_extract_plain_text_response(self, client):
        """Should extract task_id from plain text response."""
        mock_resp = Mock()
        mock_resp.text = '"abc-123"'
        mock_resp.headers = {"Content-Type": "text/plain"}

        result = client._extract_task_id_from_response(mock_resp)
        assert result == "abc-123"

    def test_validate_valid_uuid(self, client):
        """Should return string for valid UUID."""
        result = client._validate_task_id("12345678-1234-1234-1234-123456789abc")
        assert result == "12345678-1234-1234-1234-123456789abc"

    def test_validate_invalid_uuid(self, client):
        """Should return None for invalid UUID."""
        result = client._validate_task_id("not-a-uuid")
        assert result is None

    def test_validate_empty_returns_none(self, client):
        """Should return None for empty/None task_id."""
        assert client._validate_task_id(None) is None
        assert client._validate_task_id("") is None


class TestDocumentTypes:
    """Test document type fetching and creation."""

    def test_fetch_document_types(self, client):
        """Should parse paginated response correctly."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Article"},
                {"id": 2, "name": "Report"},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._fetch_document_types()

        assert result == {"Article": 1, "Report": 2}

    def test_get_or_create_returns_cached(self, client):
        """Should return cached ID without API call."""
        client._document_type_cache = {"Article": 5}
        client._document_type_cache_populated = True

        with patch.object(client.session, "get") as mock_get:
            result = client.get_or_create_document_type("Article")

        assert result == 5
        mock_get.assert_not_called()

    def test_get_or_create_creates_new(self, client):
        """Should create new document type when not found."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        create_response = Mock()
        create_response.status_code = 201
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 10, "name": "Article"}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(client.session, "post", return_value=create_response):
                result = client.get_or_create_document_type("Article")

        assert result == 10
        assert client._document_type_cache["Article"] == 10

    def test_get_or_create_handles_409(self, client):
        """Should re-fetch on 409 conflict."""
        fetch_empty = Mock()
        fetch_empty.raise_for_status = Mock()
        fetch_empty.json.return_value = {"results": [], "next": None}

        conflict = Mock()
        conflict.status_code = 409

        fetch_after = Mock()
        fetch_after.raise_for_status = Mock()
        fetch_after.json.return_value = {
            "results": [{"id": 3, "name": "Article"}],
            "next": None,
        }

        with patch.object(
            client.session, "get", side_effect=[fetch_empty, fetch_after]
        ):
            with patch.object(client.session, "post", return_value=conflict):
                result = client.get_or_create_document_type("Article")

        assert result == 3

    def test_get_or_create_empty_name(self, client):
        """Should return None for empty name."""
        result = client.get_or_create_document_type("")
        assert result is None


class TestPostDocumentWithDocumentType:
    """Test post_document with document_type parameter."""

    def test_resolves_string_document_type(self, client, tmp_path):
        """Should resolve string document type to ID."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        client._document_type_cache = {"Article": 7}
        client._document_type_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "12345678-1234-1234-1234-123456789abc"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            result = client.post_document(
                file_path=test_file,
                title="Test Doc",
                document_type="Article",
            )

        assert result == "12345678-1234-1234-1234-123456789abc"
        call_args = mock_post.call_args
        assert call_args[1]["data"]["document_type"] == 7

    def test_passes_integer_document_type(self, client, tmp_path):
        """Should pass integer document type directly."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "12345678-1234-1234-1234-123456789abc"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            client.post_document(
                file_path=test_file,
                title="Test Doc",
                document_type=7,
            )

        call_args = mock_post.call_args
        assert call_args[1]["data"]["document_type"] == 7

    def test_passes_numeric_string_document_type(self, client, tmp_path):
        """Should convert numeric string document type to int."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "12345678-1234-1234-1234-123456789abc"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            client.post_document(
                file_path=test_file,
                title="Test Doc",
                document_type="7",
            )

        call_args = mock_post.call_args
        assert call_args[1]["data"]["document_type"] == 7


class TestSetCustomFieldsLLMFlattening:
    """Test that set_custom_fields flattens extra dict for LLM fields."""

    def test_llm_fields_in_extra_are_found(self, client):
        """Should find LLM fields stored in extra dict."""
        client._custom_field_cache = {
            "LLM Summary": 10,
            "LLM Keywords": 11,
            "LLM Entities": 12,
            "LLM Topics": 13,
        }
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {
            "extra": {
                "llm_summary": "A summary",
                "llm_keywords": "key1, key2",
                "llm_entities": "entity1",
                "llm_topics": "topic1",
            }
        }

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            result = client.set_custom_fields(123, metadata)

        assert result is True
        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        assert len(payload) == 4
        values = {item["field"]: item["value"] for item in payload}
        assert values[10] == "A summary"
        assert values[11] == "key1, key2"

    def test_top_level_takes_priority_over_extra(self, client):
        """Top-level keys should not be overwritten by extra dict."""
        client._custom_field_cache = {"Author": 1}
        client._custom_field_cache_populated = True

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        metadata = {
            "author": "Top Level Author",
            "extra": {
                "author": "Extra Author",
            },
        }

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            client.set_custom_fields(123, metadata)

        payload = mock_patch.call_args[1]["json"]["custom_fields"]
        assert len(payload) == 1
        assert payload[0]["value"] == "Top Level Author"


class TestOwnerNullOnCreation:
    """Test that POST payloads include owner: null for public objects."""

    def test_correspondent_created_with_owner_null(self, client):
        """Correspondent creation should include owner: null."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        create_response = Mock()
        create_response.status_code = 201
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 1, "name": "Test"}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session, "post", return_value=create_response
            ) as mock_post:
                client.get_or_create_correspondent("Test")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["owner"] is None

    def test_document_type_created_with_owner_null(self, client):
        """Document type creation should include owner: null."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        create_response = Mock()
        create_response.status_code = 201
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 1, "name": "Article"}

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session, "post", return_value=create_response
            ) as mock_post:
                client.get_or_create_document_type("Article")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["owner"] is None

    def test_tag_created_with_owner_null(self, client):
        """Tag creation should include owner: null."""
        client._tag_cache = {}
        client._tag_cache_populated = True

        create_response = Mock()
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {"id": 1, "name": "Energy"}

        with patch.object(
            client.session, "post", return_value=create_response
        ) as mock_post:
            client.get_or_create_tags(["Energy"])

        call_args = mock_post.call_args
        assert call_args[1]["json"]["owner"] is None

    def test_custom_field_created_with_owner_null(self, client):
        """Custom field creation should include owner: null."""
        fetch_response = Mock()
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {"results": [], "next": None}

        create_response = Mock()
        create_response.status_code = 201
        create_response.raise_for_status = Mock()
        create_response.json.return_value = {
            "id": 1, "name": "Test Field", "data_type": "string"
        }

        with patch.object(client.session, "get", return_value=fetch_response):
            with patch.object(
                client.session, "post", return_value=create_response
            ) as mock_post:
                client.get_or_create_custom_field("Test Field", "string")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["owner"] is None


class TestCustomFieldMappingUpdated:
    """Test that CUSTOM_FIELD_MAPPING includes new fields."""

    def test_mapping_includes_organization(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "organization" in CUSTOM_FIELD_MAPPING
        assert CUSTOM_FIELD_MAPPING["organization"] == ("Organization", "string")

    def test_mapping_includes_author(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "author" in CUSTOM_FIELD_MAPPING
        assert CUSTOM_FIELD_MAPPING["author"] == ("Author", "string")

    def test_mapping_includes_description(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "description" in CUSTOM_FIELD_MAPPING
        assert CUSTOM_FIELD_MAPPING["description"] == ("Description", "string")

    def test_mapping_includes_language(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "language" in CUSTOM_FIELD_MAPPING
        assert CUSTOM_FIELD_MAPPING["language"] == ("Language", "string")

    def test_mapping_removed_page_count(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "page_count" not in CUSTOM_FIELD_MAPPING

    def test_mapping_removed_file_size(self):
        from app.services.paperless_client import CUSTOM_FIELD_MAPPING
        assert "file_size" not in CUSTOM_FIELD_MAPPING


class TestGetTaskStatusEdgeCases:
    """Test get_task_status edge cases."""

    def test_paginated_dict_response(self, client):
        """Should handle paginated dict response format."""
        page1_resp = Mock()
        page1_resp.raise_for_status = Mock()
        page1_resp.json.return_value = {
            "results": [{"task_id": "other-uuid", "status": "SUCCESS"}],
            "next": "http://localhost:8000/api/tasks/?page=2",
        }

        page2_resp = Mock()
        page2_resp.raise_for_status = Mock()
        page2_resp.json.return_value = {
            "results": [
                {"task_id": "12345678-1234-1234-1234-123456789abc", "status": "SUCCESS"}
            ],
            "next": None,
        }

        with patch.object(
            client.session, "get", side_effect=[page1_resp, page2_resp]
        ):
            result = client.get_task_status("12345678-1234-1234-1234-123456789abc")

        assert result is not None
        assert result["status"] == "SUCCESS"

    def test_task_not_found(self, client):
        """Should return None when task not in list."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = [
            {"task_id": "other-uuid", "status": "SUCCESS"}
        ]

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.get_task_status("12345678-1234-1234-1234-123456789abc")

        assert result is None

    def test_api_error_returns_none(self, client):
        """Should return None on API error."""
        with patch.object(
            client.session, "get", side_effect=Exception("Connection refused")
        ):
            result = client.get_task_status("12345678-1234-1234-1234-123456789abc")

        assert result is None


class TestEnsurePublic:
    """Test _ensure_public() helper."""

    def test_patches_with_owner_null(self, client):
        """Should PATCH the object with owner=null."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "patch", return_value=mock_response) as mock_patch:
            client._ensure_public("correspondents", 42, "AEMO")

        mock_patch.assert_called_once_with(
            "http://localhost:8000/api/correspondents/42/",
            json={"owner": None},
            timeout=30,
        )

    def test_logs_warning_on_failure(self, client):
        """Should log warning but not raise on PATCH failure."""
        with patch.object(
            client.session, "patch", side_effect=Exception("Network error")
        ):
            # Should not raise
            client._ensure_public("tags", 10, "Energy")

    def test_handles_http_error_gracefully(self, client):
        """Should handle HTTP error response without raising."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

        with patch.object(client.session, "patch", return_value=mock_response):
            # Should not raise
            client._ensure_public("document_types", 5, "Article")


class TestFetchEnsuresPublic:
    """Test that _fetch_*() methods call _ensure_public for private objects."""

    def test_fetch_correspondents_patches_private(self, client):
        """Should PATCH correspondents with non-null owner."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "PublicOrg", "owner": None},
                {"id": 2, "name": "PrivateOrg", "owner": 3},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_ensure_public") as mock_ensure:
                result = client._fetch_correspondents()

        assert result == {"PublicOrg": 1, "PrivateOrg": 2}
        mock_ensure.assert_called_once_with("correspondents", 2, "PrivateOrg")

    def test_fetch_tags_patches_private(self, client):
        """Should PATCH tags with non-null owner."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 10, "name": "Public", "owner": None},
                {"id": 20, "name": "Private", "owner": 1},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_ensure_public") as mock_ensure:
                result = client._fetch_tags()

        assert result == {"Public": 10, "Private": 20}
        mock_ensure.assert_called_once_with("tags", 20, "Private")

    def test_fetch_document_types_patches_private(self, client):
        """Should PATCH document types with non-null owner."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Article", "owner": 5},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_ensure_public") as mock_ensure:
                result = client._fetch_document_types()

        assert result == {"Article": 1}
        mock_ensure.assert_called_once_with("document_types", 1, "Article")

    def test_fetch_custom_fields_patches_private(self, client):
        """Should PATCH custom fields with non-null owner."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Original URL", "owner": 2},
                {"id": 2, "name": "Scraped Date", "owner": None},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_ensure_public") as mock_ensure:
                result = client._fetch_custom_fields()

        assert result == {"Original URL": 1, "Scraped Date": 2}
        mock_ensure.assert_called_once_with("custom_fields", 1, "Original URL")

    def test_fetch_skips_items_without_owner_key(self, client):
        """Should not PATCH items missing the owner key entirely."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "NoOwnerKey"},  # No owner key
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_ensure_public") as mock_ensure:
                result = client._fetch_correspondents()

        assert result == {"NoOwnerKey": 1}
        mock_ensure.assert_not_called()

    def test_fetch_still_caches_on_patch_failure(self, client):
        """Cache should be populated even if PATCH to make public fails."""
        get_response = Mock()
        get_response.raise_for_status = Mock()
        get_response.json.return_value = {
            "results": [
                {"id": 1, "name": "PrivateTag", "owner": 5},
            ],
            "next": None,
        }

        with patch.object(client.session, "get", return_value=get_response):
            with patch.object(
                client.session, "patch", side_effect=Exception("PATCH failed")
            ):
                result = client._fetch_tags()

        # Cache populated despite PATCH failure (_ensure_public is fire-and-forget)
        assert result == {"PrivateTag": 1}
