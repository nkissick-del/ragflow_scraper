"""Tests for nuclear purge functionality."""

import pytest
from unittest.mock import Mock, patch

from app.services.state_tracker import StateTracker
from app.services.paperless_client import PaperlessClient


class TestNuclearPurge:
    """Test StateTracker.nuclear_purge()."""

    @pytest.fixture
    def state_tracker(self, tmp_path):
        """Create a StateTracker with temp state dir."""
        with patch.object(
            __import__("app.config", fromlist=["Config"]).Config,
            "STATE_DIR",
            tmp_path / "state",
        ), patch.object(
            __import__("app.config", fromlist=["Config"]).Config,
            "DOWNLOAD_DIR",
            tmp_path / "downloads",
        ), patch.object(
            __import__("app.config", fromlist=["Config"]).Config,
            "METADATA_DIR",
            tmp_path / "metadata",
        ):
            (tmp_path / "state").mkdir()
            (tmp_path / "downloads").mkdir()
            (tmp_path / "metadata").mkdir()
            tracker = StateTracker("test_scraper")
        return tracker

    def test_nuclear_purge_calls_local_purge(self, state_tracker):
        """Should call local purge and return its counts."""
        result = state_tracker.nuclear_purge()
        assert "urls_cleared" in result
        assert "files_deleted" in result
        assert "metadata_deleted" in result

    def test_nuclear_purge_deletes_from_archive(self, state_tracker):
        """Should call archive_backend.delete_by_tag() when provided."""
        mock_archive = Mock()
        mock_archive.delete_by_tag.return_value = 5

        result = state_tracker.nuclear_purge(
            archive_backend=mock_archive,
            tag_name="TestTag",
        )

        mock_archive.delete_by_tag.assert_called_once_with("TestTag")
        assert result["archive_deleted"] == 5

    def test_nuclear_purge_deletes_from_vector_store(self, state_tracker):
        """Should call vector_store.delete_by_source() when provided."""
        mock_vector = Mock()
        mock_vector.delete_by_source.return_value = 42

        result = state_tracker.nuclear_purge(vector_store=mock_vector)

        mock_vector.delete_by_source.assert_called_once_with("test_scraper")
        assert result["vector_deleted"] == 42

    def test_nuclear_purge_handles_archive_failure(self, state_tracker):
        """Should handle archive backend errors gracefully."""
        mock_archive = Mock()
        mock_archive.delete_by_tag.side_effect = Exception("Connection refused")

        result = state_tracker.nuclear_purge(
            archive_backend=mock_archive,
            tag_name="TestTag",
        )

        assert result["archive_deleted"] == 0

    def test_nuclear_purge_handles_vector_failure(self, state_tracker):
        """Should handle vector store errors gracefully."""
        mock_vector = Mock()
        mock_vector.delete_by_source.side_effect = Exception("DB error")

        result = state_tracker.nuclear_purge(vector_store=mock_vector)

        assert result["vector_deleted"] == 0

    def test_nuclear_purge_handles_no_backends(self, state_tracker):
        """Should work with no backends (local purge only)."""
        result = state_tracker.nuclear_purge()
        assert result["archive_deleted"] == 0
        assert result["vector_deleted"] == 0
        assert "urls_cleared" in result

    def test_nuclear_purge_no_tag_skips_archive(self, state_tracker):
        """Should skip archive delete when tag_name is empty."""
        mock_archive = Mock()
        state_tracker.nuclear_purge(
            archive_backend=mock_archive,
            tag_name="",
        )
        mock_archive.delete_by_tag.assert_not_called()


class TestDeleteDocumentsByTag:
    """Test PaperlessClient.delete_documents_by_tag()."""

    @pytest.fixture
    def client(self):
        return PaperlessClient(url="http://localhost:8000", token="test-token")

    def test_delete_documents_by_tag(self, client):
        """Should find and delete documents by tag."""
        client._tag_cache = {"TestTag": 42}
        client._tag_cache_populated = True

        # Mock document listing
        doc_response = Mock()
        doc_response.raise_for_status = Mock()
        doc_response.json.return_value = {
            "results": [
                {"id": 1},
                {"id": 2},
                {"id": 3},
            ],
            "next": None,
        }

        # Mock bulk delete
        delete_response = Mock()
        delete_response.raise_for_status = Mock()

        with patch.object(
            client.session, "get", return_value=doc_response
        ), patch.object(
            client.session, "post", return_value=delete_response
        ) as mock_post:
            result = client.delete_documents_by_tag("TestTag")

        assert result == 3
        # Verify bulk_edit call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:8000/api/documents/bulk_edit/"
        payload = call_args[1]["json"]
        assert set(payload["documents"]) == {1, 2, 3}
        assert payload["method"] == "delete"

    def test_delete_documents_by_tag_not_found(self, client):
        """Should return 0 when tag doesn't exist."""
        client._tag_cache = {}
        client._tag_cache_populated = True

        result = client.delete_documents_by_tag("NonexistentTag")
        assert result == 0

    def test_delete_documents_by_tag_no_documents(self, client):
        """Should return 0 when no documents have the tag."""
        client._tag_cache = {"EmptyTag": 99}
        client._tag_cache_populated = True

        doc_response = Mock()
        doc_response.raise_for_status = Mock()
        doc_response.json.return_value = {"results": [], "next": None}

        with patch.object(client.session, "get", return_value=doc_response):
            result = client.delete_documents_by_tag("EmptyTag")

        assert result == 0

    def test_delete_documents_by_tag_not_configured(self):
        """Should return 0 when not configured."""
        client = PaperlessClient(url=None, token=None)
        result = client.delete_documents_by_tag("AnyTag")
        assert result == 0

    def test_delete_documents_by_tag_empty_name(self, client):
        """Should return 0 for empty tag name."""
        result = client.delete_documents_by_tag("")
        assert result == 0


class TestPaperlessAdapterDeleteByTag:
    """Test PaperlessArchiveBackend.delete_by_tag()."""

    def test_delete_by_tag_delegates(self):
        """Should delegate to client.delete_documents_by_tag()."""
        from app.backends.archives.paperless_adapter import PaperlessArchiveBackend

        mock_client = Mock()
        mock_client.delete_documents_by_tag.return_value = 7

        backend = PaperlessArchiveBackend(client=mock_client)
        result = backend.delete_by_tag("TestTag")

        assert result == 7
        mock_client.delete_documents_by_tag.assert_called_once_with("TestTag")
