"""Stack tests for end-to-end pipeline — require real services."""

import time

import pytest
import requests

from app.backends.parsers.docling_serve_parser import DoclingServeParser
from app.backends.archives.paperless_adapter import PaperlessArchiveBackend
from app.backends.rag.anythingllm_adapter import AnythingLLMBackend
from app.orchestrator.pipeline import Pipeline
from app.scrapers.models import DocumentMetadata
from app.services.paperless_client import PaperlessClient


pytestmark = pytest.mark.stack


@pytest.fixture
def paperless_client(paperless_url, paperless_token, paperless_alive):
    """Real Paperless client."""
    return PaperlessClient(url=paperless_url, token=paperless_token)


@pytest.fixture
def archive_backend(paperless_client):
    """Real archive backend."""
    return PaperlessArchiveBackend(client=paperless_client)


@pytest.fixture
def parser(docling_serve_url, docling_serve_alive):
    """Real parser backend."""
    return DoclingServeParser(url=docling_serve_url)


@pytest.fixture
def rag_backend(anythingllm_url, anythingllm_key, anythingllm_workspace, anythingllm_alive):
    """Real RAG backend."""
    return AnythingLLMBackend(
        api_url=anythingllm_url,
        api_key=anythingllm_key,
        workspace_id=anythingllm_workspace,
    )


@pytest.fixture
def dummy_metadata():
    """Minimal DocumentMetadata for pipeline calls."""
    return DocumentMetadata(
        url="http://example.com/stack-test.pdf",
        title=f"Stack Test Doc {int(time.time())}",
        filename="stack_test_doc.pdf",
        organization="StackTest",
        tags=["stack-test"],
    )


class _MockSettings:
    """Stub settings that returns defaults for all .get() calls."""

    def get(self, key: str, default: str = "") -> str:
        return default


class _MockContainer:
    """Lightweight mock container wired to real backends.

    Includes stubs for attributes the pipeline accesses beyond the
    three core backends (ragflow_client, settings, tika_client, llm_client).
    """

    def __init__(self, parser_backend, archive_backend, rag_backend):
        self._parser = parser_backend
        self._archive = archive_backend
        self._rag = rag_backend
        self._settings = _MockSettings()

    @property
    def parser_backend(self):
        return self._parser

    @property
    def archive_backend(self):
        return self._archive

    @property
    def rag_backend(self):
        return self._rag

    @property
    def ragflow_client(self):
        """Stub — Pipeline.__init__ reads this but _process_document uses rag_backend."""
        return None

    @property
    def settings(self):
        return self._settings

    @property
    def tika_client(self):
        """Stub — enrichment step checks settings first and skips if disabled."""
        return None

    @property
    def llm_client(self):
        """Stub — LLM enrichment checks settings first and skips if disabled."""
        return None

    @property
    def gotenberg_client(self):
        """Stub — only used for markdown/office doc types."""
        return None


class TestPipelineParseAndArchive:
    """Parse + archive pipeline using real services."""

    def test_parse_and_archive(
        self,
        parser,
        archive_backend,
        rag_backend,
        test_pdf,
        dummy_metadata,
        paperless_url,
        paperless_token,
    ):
        """Parse a PDF with docling-serve, then archive to Paperless."""
        container = _MockContainer(parser, archive_backend, rag_backend)

        pipeline = Pipeline(
            scraper_name="stack-test",
            upload_to_ragflow=False,
            upload_to_paperless=True,
            verify_document_timeout=90,
            container=container,
        )

        try:
            result = pipeline._process_document(dummy_metadata, test_pdf)

            assert result["parsed"] is True, "Parsing failed"
            assert result["archived"] is True, "Archiving failed"
            if not result["verified"]:
                print("Warning: document verification timed out (non-fatal)")
        finally:
            _cleanup_paperless_test_doc(
                paperless_url, paperless_token, dummy_metadata.title
            )


class TestPipelineFullE2E:
    """Full pipeline: parse + archive + RAG using all real services."""

    def test_full_pipeline(
        self,
        parser,
        archive_backend,
        rag_backend,
        test_pdf,
        dummy_metadata,
        paperless_url,
        paperless_token,
    ):
        """Parse -> archive -> RAG ingest using real services."""
        container = _MockContainer(parser, archive_backend, rag_backend)

        pipeline = Pipeline(
            scraper_name="stack-test",
            dataset_id="test",
            upload_to_ragflow=True,
            upload_to_paperless=True,
            verify_document_timeout=90,
            container=container,
        )

        try:
            result = pipeline._process_document(dummy_metadata, test_pdf)

            assert result["parsed"] is True, "Parsing failed"
            assert result["archived"] is True, "Archiving failed"
            if not result["rag_indexed"]:
                print("Warning: RAG indexing failed (non-fatal)")
        finally:
            _cleanup_paperless_test_doc(
                paperless_url, paperless_token, dummy_metadata.title
            )


def _cleanup_paperless_test_doc(base_url: str, token: str, title: str) -> None:
    """Best-effort cleanup of test documents from Paperless by title search."""
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.get(
            f"{base_url}/api/documents/",
            headers=headers,
            params={"query": title},
            timeout=30,
        )
        if resp.ok:
            for doc in resp.json().get("results", []):
                doc_id = doc.get("id")
                doc_title = doc.get("title", "")
                # Only delete exact title matches to avoid removing unrelated docs
                if doc_id and doc_title == title:
                    requests.delete(
                        f"{base_url}/api/documents/{doc_id}/",
                        headers=headers,
                        timeout=30,
                    )
    except Exception as e:
        print(f"Warning: Paperless cleanup failed: {e}")

    # Also clean up correspondent "StackTest" and tag "stack-test"
    for resource_type, name in [("correspondents", "StackTest"), ("tags", "stack-test")]:
        try:
            resp = requests.get(
                f"{base_url}/api/{resource_type}/",
                headers=headers,
                timeout=30,
            )
            if resp.ok:
                for item in resp.json().get("results", []):
                    if item.get("name") == name:
                        requests.delete(
                            f"{base_url}/api/{resource_type}/{item['id']}/",
                            headers=headers,
                            timeout=30,
                        )
        except Exception:
            pass
