"""Integration tests for Paperless-ngx backend with mocked API.

Tests document archiving, correspondent/tag management, and verification polling.
"""

import re
import threading

import pytest
import requests
import responses
from pathlib import Path
from unittest.mock import patch

from app.backends.archives.paperless_adapter import PaperlessArchiveBackend
from app.services.paperless_client import PaperlessClient


@pytest.fixture
def paperless_client():
    """Create test Paperless client."""
    return PaperlessClient(
        url="http://localhost:8000",
        token="test-token-123",
    )


@pytest.fixture
def paperless_backend(paperless_client):
    """Create test Paperless backend."""
    return PaperlessArchiveBackend(client=paperless_client)


@pytest.fixture
def test_pdf(tmp_path):
    """Create a test PDF file."""
    pdf_file = tmp_path / "test_document.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\nTest PDF content")
    return pdf_file


class TestPaperlessDocumentArchiving:
    """Test document archiving workflow."""

    @responses.activate
    def test_archive_document_success(self, paperless_backend, test_pdf):
        """Should successfully archive document to Paperless."""
        task_id = "00000000-0000-0000-0000-000000000001"
        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": task_id},
            status=200,
        )

        # Archive document
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            created="2024-01-15T10:30:00Z",
            correspondent="TestOrg",
            tags=["test", "integration"],
        )

        # Verify
        assert result.success is True
        assert result.document_id == task_id
        assert result.archive_name == "paperless"
        assert task_id in result.url

    @responses.activate
    def test_archive_with_correspondent_lookup(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should resolve correspondent name to ID."""
        # Mock correspondent fetch (cache population)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={
                "count": 1,
                "results": [{"id": 42, "name": "TestOrg"}],
            },
            status=200,
        )

        # Mock upload endpoint
        task_id = "00000000-0000-0000-0000-000000000002"
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": task_id},
            status=200,
        )

        # Archive document with correspondent name
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            correspondent="TestOrg",
        )

        # Verify
        assert result.success is True
        assert result.document_id == task_id

        # Verify correspondent was resolved to ID in request
        upload_request = responses.calls[-1].request
        # Parse multipart form data to verify correspondent ID
        content_type = upload_request.headers.get("Content-Type", "")
        # Extract boundary from Content-Type header
        if "boundary=" in content_type:
            body_str = upload_request.body.decode("utf-8", errors="ignore")
            # Check that correspondent field has value "42"
            assert 'name="correspondent"' in body_str
            # Find the correspondent value in the multipart data
            correspondent_match = re.search(
                r'name="correspondent"[^\r\n]*\r?\n\r?\n([^\r\n]+)', body_str
            )
            assert correspondent_match is not None, (
                "Correspondent field not found in request"
            )
            assert correspondent_match.group(1) == "42", (
                f"Expected correspondent ID 42, got {correspondent_match.group(1)}"
            )

    @responses.activate
    def test_archive_with_tag_lookup(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should resolve tag names to IDs."""
        # Mock tag fetch (cache population)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/tags/",
            json={
                "count": 2,
                "results": [
                    {"id": 10, "name": "test"},
                    {"id": 11, "name": "integration"},
                ],
            },
            status=200,
        )

        # Mock upload endpoint
        task_id = "00000000-0000-0000-0000-000000000003"
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": task_id},
            status=200,
        )

        # Archive document with tag names
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            tags=["test", "integration"],
        )

        # Verify
        assert result.success is True
        assert result.document_id == task_id

    @responses.activate
    def test_archive_creates_missing_correspondent(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should create correspondent if it doesn't exist."""
        # Mock correspondent fetch (empty)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={"count": 0, "results": []},
            status=200,
        )

        # Mock correspondent creation
        responses.add(
            responses.POST,
            "http://localhost:8000/api/correspondents/",
            json={"id": 99, "name": "NewOrg"},
            status=201,
        )

        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000004"},
            status=200,
        )

        # Archive document with new correspondent
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            correspondent="NewOrg",
        )

        # Verify
        assert result.success is True
        # Verify correspondent was created
        assert (
            len(
                [
                    c
                    for c in responses.calls
                    if "correspondents" in c.request.url and c.request.method == "POST"
                ]
            )
            == 1
        )

    @responses.activate
    def test_archive_creates_missing_tags(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should create tags if they don't exist."""
        # Mock tag fetch (empty)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/tags/",
            json={"count": 0, "results": []},
            status=200,
        )

        # Mock tag creation (called twice for two tags)
        responses.add(
            responses.POST,
            "http://localhost:8000/api/tags/",
            json={"id": 20, "name": "newtag1"},
            status=201,
        )
        responses.add(
            responses.POST,
            "http://localhost:8000/api/tags/",
            json={"id": 21, "name": "newtag2"},
            status=201,
        )

        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000005"},
            status=200,
        )

        # Archive document with new tags
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            tags=["newtag1", "newtag2"],
        )

        # Verify
        assert result.success is True
        # Verify tags were created
        tag_posts = [
            c
            for c in responses.calls
            if "tags" in c.request.url and c.request.method == "POST"
        ]
        assert len(tag_posts) == 2

    @responses.activate
    def test_archive_pagination(self, paperless_client, paperless_backend, test_pdf):
        """Should handle paginated API responses for correspondents and tags."""
        # Mock paginated correspondent fetch (2 pages)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={
                "count": 3,
                "next": "http://localhost:8000/api/correspondents/?page=2",
                "results": [
                    {"id": 1, "name": "Org1"},
                    {"id": 2, "name": "Org2"},
                ],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/?page=2",
            json={
                "count": 3,
                "next": None,
                "results": [
                    {"id": 3, "name": "TargetOrg"},
                ],
            },
            status=200,
        )

        # Mock upload endpoint
        task_id = "00000000-0000-0000-0000-000000000006"
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": task_id},
            status=200,
        )

        # Archive document with correspondent from page 2
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            correspondent="TargetOrg",
        )

        # Verify success
        assert result.success is True
        # Verify both pages were fetched
        correspondent_gets = [
            c
            for c in responses.calls
            if "correspondents" in c.request.url and c.request.method == "GET"
        ]
        assert len(correspondent_gets) == 2

    @responses.activate
    def test_archive_case_insensitive_matching(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should handle case-insensitive name matching for correspondents and tags."""
        # Mock correspondent fetch with different casing
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={
                "count": 1,
                "results": [{"id": 50, "name": "TestOrg"}],  # Mixed case
            },
            status=200,
        )

        # Mock tag fetch with different casing
        responses.add(
            responses.GET,
            "http://localhost:8000/api/tags/",
            json={
                "count": 1,
                "results": [{"id": 100, "name": "ImportantTag"}],  # Mixed case
            },
            status=200,
        )

        # Mock upload endpoint
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000007"},
            status=200,
        )

        # Archive document with lowercase names
        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test Document",
            correspondent="testorg",  # lowercase
            tags=["importanttag"],  # lowercase
        )

        # Verify success (case-insensitive matching should work)
        assert result.success is True

    @responses.activate
    def test_archive_concurrent_requests(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should handle concurrent archiving requests correctly."""
        # Mock correspondent fetch
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={
                "count": 1,
                "results": [{"id": 42, "name": "TestOrg"}],
            },
            status=200,
        )

        # Mock tag fetch
        responses.add(
            responses.GET,
            "http://localhost:8000/api/tags/",
            json={
                "count": 1,
                "results": [{"id": 10, "name": "test"}],
            },
            status=200,
        )

        # Mock upload endpoint (multiple times for concurrent requests)
        for i in range(3):
            responses.add(
                responses.POST,
                "http://localhost:8000/api/documents/post_document/",
                json={"task_id": f"00000000-0000-0000-0000-0000000000{i + 8:02d}"},
                status=200,
            )

        # Archive documents concurrently
        results = []
        errors = []

        def archive_doc(index):
            try:
                result = paperless_backend.archive_document(
                    file_path=test_pdf,
                    title=f"Test Document {index}",
                    correspondent="TestOrg",
                    tags=["test"],
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=archive_doc, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all succeeded without errors
        assert len(errors) == 0, f"Concurrent archiving had errors: {errors}"
        assert len(results) == 3
        assert all(r.success for r in results)


class TestPaperlessVerification:
    """Test document verification polling."""

    @responses.activate
    def test_verify_document_success(self, paperless_backend):
        """Should successfully verify document exists."""
        task_id = "00000000-0000-0000-0000-000000000001"
        # Mock task status endpoint (SUCCESS)
        responses.add(
            responses.GET,
            f"http://localhost:8000/api/tasks/{task_id}/",
            json={
                "status": "SUCCESS",
                "related_document": 456,
            },
            status=200,
        )

        # Verify document
        verified = paperless_backend.verify_document(
            document_id=task_id,
            timeout=5,
        )

        # Verify
        assert verified is True

    @responses.activate
    def test_verify_document_timeout(self, paperless_backend):
        """Should timeout when document not verified."""
        task_id = "00000000-0000-0000-0000-000000000002"
        # Mock task status endpoint (PENDING forever)
        responses.add(
            responses.GET,
            f"http://localhost:8000/api/tasks/{task_id}/",
            json={
                "status": "PENDING",
            },
            status=200,
        )

        # Mock time.sleep to avoid real delays
        with patch("time.sleep"):
            # Verify document (should timeout)
            verified = paperless_backend.verify_document(
                document_id=task_id,
                timeout=2,  # Short timeout for test
            )

        # Verify
        assert verified is False

    @responses.activate
    def test_verify_document_failure(self, paperless_backend):
        """Should handle task failure."""
        task_id = "00000000-0000-0000-0000-000000000003"
        # Mock task status endpoint (FAILURE)
        responses.add(
            responses.GET,
            f"http://localhost:8000/api/tasks/{task_id}/",
            json={
                "status": "FAILURE",
                "result": "Processing failed",
            },
            status=200,
        )

        # Verify document
        verified = paperless_backend.verify_document(
            document_id=task_id,
            timeout=5,
        )

        # Verify
        assert verified is False


class TestPaperlessCaching:
    """Test caching behavior for correspondents and tags."""

    @responses.activate
    def test_correspondent_cache_reduces_api_calls(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should cache correspondent lookups."""
        # Mock correspondent fetch (called once)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/correspondents/",
            json={
                "count": 1,
                "results": [{"id": 42, "name": "TestOrg"}],
            },
            status=200,
        )

        # Mock upload endpoint (called twice)
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000010"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000011"},
            status=200,
        )

        # Archive two documents with same correspondent
        paperless_backend.archive_document(
            file_path=test_pdf,
            title="Doc 1",
            correspondent="TestOrg",
        )
        paperless_backend.archive_document(
            file_path=test_pdf,
            title="Doc 2",
            correspondent="TestOrg",
        )

        # Verify: correspondent API called only once (cached on second call)
        correspondent_calls = [
            c
            for c in responses.calls
            if "correspondents" in c.request.url and c.request.method == "GET"
        ]
        assert len(correspondent_calls) == 1

    @responses.activate
    def test_tag_cache_reduces_api_calls(
        self, paperless_client, paperless_backend, test_pdf
    ):
        """Should cache tag lookups."""
        # Mock tag fetch (called once)
        responses.add(
            responses.GET,
            "http://localhost:8000/api/tags/",
            json={
                "count": 1,
                "results": [{"id": 10, "name": "test"}],
            },
            status=200,
        )

        # Mock upload endpoint (called twice)
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000012"},
            status=200,
        )
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"task_id": "00000000-0000-0000-0000-000000000013"},
            status=200,
        )

        # Archive two documents with same tag
        paperless_backend.archive_document(
            file_path=test_pdf,
            title="Doc 1",
            tags=["test"],
        )
        paperless_backend.archive_document(
            file_path=test_pdf,
            title="Doc 2",
            tags=["test"],
        )

        # Verify: tag API called only once (cached on second call)
        tag_calls = [
            c
            for c in responses.calls
            if "tags" in c.request.url and c.request.method == "GET"
        ]
        assert len(tag_calls) == 1


class TestPaperlessErrorHandling:
    """Test error handling scenarios."""

    def test_archive_file_not_found(self, paperless_backend):
        """Should handle missing file gracefully."""
        result = paperless_backend.archive_document(
            file_path=Path("/nonexistent/file.pdf"),
            title="Test",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @responses.activate
    def test_archive_api_error(self, paperless_backend, test_pdf):
        """Should handle API errors."""
        # Mock upload endpoint (server error)
        responses.add(
            responses.POST,
            "http://localhost:8000/api/documents/post_document/",
            json={"error": "Internal server error"},
            status=500,
        )

        result = paperless_backend.archive_document(
            file_path=test_pdf,
            title="Test",
        )

        assert result.success is False
        assert result.error is not None

    @responses.activate
    def test_archive_network_timeout(self, paperless_backend, test_pdf):
        """Should handle network timeouts."""
        # Mock timeout
        with patch.object(
            paperless_backend.client.session,
            "post",
            side_effect=requests.Timeout("Timeout"),
        ):
            result = paperless_backend.archive_document(
                file_path=test_pdf,
                title="Test",
            )

            assert result.success is False
            assert result.error is not None

    def test_verify_not_configured(self):
        """Should handle verification when not configured."""
        backend = PaperlessArchiveBackend(client=PaperlessClient(url=None, token=None))

        verified = backend.verify_document("00000000-0000-0000-0000-000000000001")

        assert verified is False
