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
            client = PaperlessClient(url=None, token="token")
            assert client.is_configured is False

    def test_is_configured_false_without_token(self):
        """Should return False when token is missing."""
        with patch("app.services.paperless_client.Config") as mock_config:
            mock_config.PAPERLESS_API_TOKEN = None
            client = PaperlessClient(url="http://test:8000", token=None)
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
        client = PaperlessClient(url=None, token=None)
        result = client._fetch_correspondents()
        assert result == {}


class TestGetOrCreateCorrespondent:
    """Test correspondent lookup/creation."""

    def test_returns_cached_id(self, client):
        """Should return cached ID without API call."""
        client._correspondent_cache = {"AEMO": 42}

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

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.text = "task-uuid-123"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            result = client.post_document(
                file_path=test_file,
                title="Test Doc",
                correspondent="AEMO",
            )

        assert result == "task-uuid-123"
        # Verify correspondent ID was sent
        call_args = mock_post.call_args
        assert call_args[1]["data"]["correspondent"] == 42

    def test_resolves_string_tags(self, client, tmp_path):
        """Should resolve string tags to IDs."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        # Mock tag lookup
        client._tag_cache = {"Report": 10, "Energy": 20}

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.text = "task-uuid-456"

        with patch.object(
            client.session, "post", return_value=mock_response
        ) as mock_post:
            result = client.post_document(
                file_path=test_file,
                title="Test Doc",
                tags=["Report", "Energy"],
            )

        assert result == "task-uuid-456"
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
        mock_response.text = "task-uuid-789"

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
        upload_response.text = "task-uuid-success"

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
        assert result == "task-uuid-success"
