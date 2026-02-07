"""Stack tests for Paperless-ngx — require real Paperless service."""

import time

import pytest
import requests

from app.services.paperless_client import PaperlessClient


pytestmark = pytest.mark.stack


@pytest.fixture
def client(paperless_url, paperless_token, paperless_alive):
    """Create a PaperlessClient connected to the real service."""
    return PaperlessClient(url=paperless_url, token=paperless_token)


class TestPaperlessHealth:
    """Basic connectivity tests."""

    def test_health_check(self, client):
        """Paperless API should be alive."""
        assert client.check_alive() is True


class TestPaperlessReadOperations:
    """Tests that read from Paperless without creating resources."""

    def test_list_correspondents(self, client):
        """Should return a dict of correspondents."""
        correspondents = client._fetch_correspondents()
        assert isinstance(correspondents, dict)

    def test_list_tags(self, client):
        """Should return a dict of tags."""
        tags = client._fetch_tags()
        assert isinstance(tags, dict)


class TestPaperlessWriteOperations:
    """Tests that create and clean up resources in Paperless."""

    def test_create_and_cleanup_correspondent(self, client, paperless_url, paperless_token):
        """Create a correspondent, verify it exists, then delete it."""
        test_name = f"stack-test-corr-{int(time.time())}"
        corr_id = None

        try:
            corr_id = client.get_or_create_correspondent(test_name)
            assert corr_id is not None
            assert isinstance(corr_id, int)
        finally:
            if corr_id is not None:
                _delete_resource(paperless_url, paperless_token, "correspondents", corr_id)

    def test_create_and_cleanup_tag(self, client, paperless_url, paperless_token):
        """Create a tag, verify it exists, then delete it."""
        test_name = f"stack-test-tag-{int(time.time())}"
        tag_id = None

        try:
            tag_ids = client.get_or_create_tags([test_name])
            assert len(tag_ids) == 1
            tag_id = tag_ids[0]
            assert isinstance(tag_id, int)
        finally:
            if tag_id is not None:
                _delete_resource(paperless_url, paperless_token, "tags", tag_id)

    def test_upload_verify_delete_document(
        self, client, paperless_url, paperless_token, test_pdf
    ):
        """Full document lifecycle: upload -> verify -> delete."""
        test_title = f"stack-test-doc-{int(time.time())}"
        test_corr = f"stack-test-corr-{int(time.time())}"
        test_tag = f"stack-test-tag-{int(time.time())}"

        created_resources = {"document_id": None, "correspondent_id": None, "tag_id": None}

        try:
            # Upload
            task_id = client.post_document(
                file_path=test_pdf,
                title=test_title,
                correspondent=test_corr,
                tags=[test_tag],
            )
            assert task_id is not None, "Upload returned no task_id"

            # Verify (poll until document appears)
            document_id = client.verify_document_exists(
                task_id=task_id, timeout=90, poll_interval=3
            )
            assert document_id is not None, f"Document never verified for task {task_id}"
            created_resources["document_id"] = document_id

        finally:
            # Cleanup: delete document
            if created_resources["document_id"]:
                _delete_resource(
                    paperless_url, paperless_token,
                    "documents", created_resources["document_id"],
                )

            # Cleanup: find and delete the correspondent we created
            try:
                correspondents = client._fetch_correspondents()
                corr_id = correspondents.get(test_corr)
                if corr_id:
                    _delete_resource(paperless_url, paperless_token, "correspondents", corr_id)
            except Exception:
                pass

            # Cleanup: find and delete the tag we created
            try:
                tags = client._fetch_tags()
                tag_id = tags.get(test_tag)
                if tag_id:
                    _delete_resource(paperless_url, paperless_token, "tags", tag_id)
            except Exception:
                pass


def _delete_resource(base_url: str, token: str, resource_type: str, resource_id) -> None:
    """Helper to delete a Paperless resource by type and ID."""
    try:
        resp = requests.delete(
            f"{base_url}/api/{resource_type}/{resource_id}/",
            headers={"Authorization": f"Token {token}"},
            timeout=30,
        )
        # 204 = deleted, 404 = already gone — both fine
        if resp.status_code not in (200, 204, 404):
            print(f"Warning: cleanup of {resource_type}/{resource_id} returned {resp.status_code}")
    except Exception as e:
        print(f"Warning: cleanup of {resource_type}/{resource_id} failed: {e}")
