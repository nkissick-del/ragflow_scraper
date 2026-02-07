"""Stack tests for AnythingLLM — require real AnythingLLM service."""

import pytest
import requests

from app.services.anythingllm_client import AnythingLLMClient


pytestmark = pytest.mark.stack


@pytest.fixture
def client(anythingllm_url, anythingllm_key, anythingllm_workspace, anythingllm_alive):
    """Create an AnythingLLMClient connected to the real service."""
    c = AnythingLLMClient(
        api_url=anythingllm_url,
        api_key=anythingllm_key,
        workspace_id=anythingllm_workspace,
    )
    yield c
    c.close()


class TestAnythingLLMConnection:
    """Basic connectivity tests."""

    def test_connection(self, client):
        """AnythingLLM API should be reachable."""
        assert client.test_connection() is True

    def test_list_workspaces(self, client):
        """Should return a list of workspaces."""
        workspaces = client.list_workspaces()
        assert isinstance(workspaces, list)


class TestAnythingLLMDocuments:
    """Document upload tests with cleanup."""

    def test_upload_document(self, client, test_markdown, anythingllm_url, anythingllm_key):
        """Upload a markdown file and verify success."""
        result = client.upload_document(
            filepath=test_markdown,
            folder_name="stack_test",
        )
        assert result.success is True, f"Upload failed: {result.error}"
        assert result.filename == test_markdown.name

        # Best-effort cleanup via system remove-documents
        if result.filename:
            try:
                requests.delete(
                    f"{anythingllm_url}/api/v1/system/remove-documents",
                    headers={"Authorization": f"Bearer {anythingllm_key}"},
                    json={"names": [f"custom-documents/stack_test/{result.filename}"]},
                    timeout=30,
                )
            except Exception:
                pass  # Cleanup is best-effort
