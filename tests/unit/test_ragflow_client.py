"""Unit tests for RAGFlowClient core client.

Tests the HTTP adapter, client init, and API methods.
The workflow layer is covered by test_ragflow_ingestion_workflow.py.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.services.ragflow_client import (
    HttpAdapter,
    RAGFlowClient,
    DatasetInfo,
    PDF_PARSERS,
    CHUNK_METHODS,
)


# ── TestHttpAdapter ─────────────────────────────────────────────────────


class TestHttpAdapter:
    """Tests for HttpAdapter retry and auth."""

    def test_auth_header_added(self):
        """Authorization Bearer header is set when api_key is provided."""
        adapter = HttpAdapter("http://ragflow:9380", api_key="test-key")

        with patch.object(adapter.session, "request") as mock_req:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_req.return_value = mock_resp

            adapter.request("GET", "/api/v1/datasets")

            call_kwargs = mock_req.call_args
            headers = call_kwargs[1]["headers"]
            assert headers["Authorization"] == "Bearer test-key"

    def test_no_auth_header_without_key(self):
        """No Authorization header when api_key is None."""
        adapter = HttpAdapter("http://ragflow:9380", api_key=None)

        with patch.object(adapter.session, "request") as mock_req:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_req.return_value = mock_resp

            adapter.request("GET", "/api/v1/datasets")

            call_kwargs = mock_req.call_args
            headers = call_kwargs[1]["headers"]
            assert "Authorization" not in headers

    @patch("time.sleep")
    def test_retries_on_5xx(self, mock_sleep):
        """Retries on 5xx status codes with backoff."""
        adapter = HttpAdapter("http://ragflow:9380", api_key="k", max_retries=3)

        with patch.object(adapter.session, "request") as mock_req:
            mock_500 = Mock(status_code=500)
            mock_200 = Mock(status_code=200)
            mock_req.side_effect = [mock_500, mock_200]

            resp = adapter.request("GET", "/api/v1/datasets")

            assert resp.status_code == 200
            assert mock_req.call_count == 2

    @patch("time.sleep")
    def test_returns_last_response_after_max_retries(self, mock_sleep):
        """Returns last failed response after exhausting retries."""
        adapter = HttpAdapter("http://ragflow:9380", api_key="k", max_retries=2)

        with patch.object(adapter.session, "request") as mock_req:
            mock_req.return_value = Mock(status_code=500)

            # Last 500 is returned (not retried further)
            resp = adapter.request("GET", "/test")
            assert resp.status_code == 500


# ── TestRAGFlowClientInit ──────────────────────────────────────────────


class TestRAGFlowClientInit:
    """Tests for RAGFlowClient initialization."""

    @patch("app.services.ragflow_client.Config")
    def test_session_auth_created_with_credentials(self, mock_config):
        """RAGFlowSession created when username is provided."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = "user@example.com"
        mock_config.RAGFLOW_PASSWORD = "pass"
        mock_config.RAGFLOW_DATASET_ID = ""
        mock_config.RAGFLOW_PUBLIC_KEY = ""

        client = RAGFlowClient(
            api_url="http://ragflow:9380",
            api_key="key",
            username="user@example.com",
            password="pass",
        )

        assert client._session_auth is not None
        assert client.session_configured is True

    @patch("app.services.ragflow_client.Config")
    def test_no_session_auth_without_credentials(self, mock_config):
        """No RAGFlowSession when username is not provided."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(
            api_url="http://ragflow:9380",
            api_key="key",
        )

        assert client._session_auth is None
        assert client.session_configured is False


# ── TestListDatasets ────────────────────────────────────────────────────


class TestListDatasets:
    """Tests for RAGFlowClient.list_datasets()."""

    @patch("app.services.ragflow_client.Config")
    def test_success_returns_dataset_list(self, mock_config):
        """Successful response returns list of DatasetInfo."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [
                {"id": "ds-1", "name": "Dataset 1", "document_count": 5, "chunk_count": 100},
                {"id": "ds-2", "name": "Dataset 2", "document_count": 0},
            ]
        }

        with patch.object(client.http, "request", return_value=mock_resp):
            datasets = client.list_datasets()

        assert len(datasets) == 2
        assert isinstance(datasets[0], DatasetInfo)
        assert datasets[0].id == "ds-1"
        assert datasets[0].document_count == 5

    @patch("app.services.ragflow_client.Config")
    def test_empty_data_returns_empty(self, mock_config):
        """Empty data array returns empty list."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": []}

        with patch.object(client.http, "request", return_value=mock_resp):
            datasets = client.list_datasets()

        assert datasets == []

    @patch("app.services.ragflow_client.Config")
    def test_exception_returns_empty(self, mock_config):
        """Exception returns empty list."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        with patch.object(client.http, "request", side_effect=ConnectionError("down")):
            datasets = client.list_datasets()

        assert datasets == []


# ── TestUploadDocument ──────────────────────────────────────────────────


class TestUploadDocument:
    """Tests for RAGFlowClient.upload_document()."""

    @patch("app.services.ragflow_client.Config")
    def test_upload_success(self, mock_config, tmp_path):
        """Successful upload returns UploadResult.success=True."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"id": "doc-123"}}

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.upload_document("ds-1", pdf)

        assert result.success is True
        assert result.document_id == "doc-123"

    @patch("app.services.ragflow_client.Config")
    def test_upload_failure(self, mock_config, tmp_path):
        """Failed upload returns UploadResult.success=False."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_resp = Mock()
        mock_resp.ok = False
        mock_resp.text = "Duplicate document"

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.upload_document("ds-1", pdf)

        assert result.success is False
        assert "Duplicate" in result.error


# ── TestCheckDocumentExists ─────────────────────────────────────────────


class TestCheckDocumentExists:
    """Tests for RAGFlowClient.check_document_exists()."""

    @patch("app.services.ragflow_client.Config")
    def test_found_returns_id(self, mock_config):
        """Returns document ID when hash matches."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"id": "doc-abc"}}

        with patch.object(client.http, "request", return_value=mock_resp):
            doc_id = client.check_document_exists("ds-1", "abc123hash")

        assert doc_id == "doc-abc"

    @patch("app.services.ragflow_client.Config")
    def test_not_found_returns_none(self, mock_config):
        """Returns None when hash not found."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = False

        with patch.object(client.http, "request", return_value=mock_resp):
            doc_id = client.check_document_exists("ds-1", "nothash")

        assert doc_id is None


# ── TestWaitForDocumentReady ────────────────────────────────────────────


class TestWaitForDocumentReady:
    """Tests for RAGFlowClient.wait_for_document_ready()."""

    @patch("app.services.ragflow_client.Config")
    def test_immediate_ready_returns_true(self, mock_config):
        """Returns True when document is immediately ready."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"status": "ready"}}

        with patch.object(client.http, "request", return_value=mock_resp):
            assert client.wait_for_document_ready("ds-1", "doc-1", timeout=1) is True

    @patch("app.services.ragflow_client.Config")
    @patch("app.services.ragflow_client.time")
    def test_timeout_returns_false(self, mock_time, mock_config):
        """Returns False when document never becomes ready."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        # Simulate time progression: start=0, check at 0.5, 1.0, then >timeout
        mock_time.time.side_effect = [0, 0.5, 1.0, 11.0]
        mock_time.sleep = Mock()

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": {"status": "processing"}}

        with patch.object(client.http, "request", return_value=mock_resp):
            assert client.wait_for_document_ready("ds-1", "doc-1", timeout=10) is False


# ── TestConnectionAndCatalogs ───────────────────────────────────────────


class TestConnectionAndCatalogs:
    """Tests for test_connection and catalog methods."""

    @patch("app.services.ragflow_client.Config")
    def test_connection_success(self, mock_config):
        """test_connection returns True on successful response."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True

        with patch.object(client.http, "request", return_value=mock_resp):
            assert client.test_connection() is True

    def test_list_pdf_parsers(self):
        """list_pdf_parsers returns static list."""
        assert "DeepDOC" in PDF_PARSERS
        assert "Docling" in PDF_PARSERS

    def test_list_chunk_methods(self):
        """list_chunk_methods returns static list."""
        assert "naive" in CHUNK_METHODS
        assert "paper" in CHUNK_METHODS


# ── TestListDatasetsErrorPaths ────────────────────────────────────────


class TestListDatasetsErrorPaths:
    """Additional error-path tests for list_datasets()."""

    @patch("app.services.ragflow_client.Config")
    def test_non_ok_response_returns_empty(self, mock_config):
        """Returns empty list when HTTP response is not OK."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = False
        mock_resp.status_code = 403

        with patch.object(client.http, "request", return_value=mock_resp):
            datasets = client.list_datasets()

        assert datasets == []

    @patch("app.services.ragflow_client.Config")
    def test_missing_fields_use_defaults(self, mock_config):
        """DatasetInfo fields default when missing from response."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": [{"id": "ds-x", "name": "X"}]}

        with patch.object(client.http, "request", return_value=mock_resp):
            datasets = client.list_datasets()

        assert len(datasets) == 1
        assert datasets[0].document_count == 0
        assert datasets[0].chunk_count == 0
        assert datasets[0].status == "unknown"


# ── TestListDocuments ─────────────────────────────────────────────────


class TestListDocuments:
    """Tests for RAGFlowClient.list_documents()."""

    @patch("app.services.ragflow_client.Config")
    def test_success_returns_document_list(self, mock_config):
        """Successful response returns list of document dicts."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [{"id": "d1", "name": "doc1"}, {"id": "d2", "name": "doc2"}]
        }

        with patch.object(client.http, "request", return_value=mock_resp):
            docs = client.list_documents("ds-1")

        assert len(docs) == 2
        assert docs[0]["id"] == "d1"

    @patch("app.services.ragflow_client.Config")
    def test_non_ok_response_returns_empty(self, mock_config):
        """Returns empty list when HTTP response is not OK."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = False

        with patch.object(client.http, "request", return_value=mock_resp):
            docs = client.list_documents("ds-1")

        assert docs == []

    @patch("app.services.ragflow_client.Config")
    def test_exception_returns_empty(self, mock_config):
        """Exception returns empty list."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        with patch.object(client.http, "request", side_effect=RuntimeError("network")):
            docs = client.list_documents("ds-1")

        assert docs == []


# ── TestUploadDocumentsWithMetadata ───────────────────────────────────


class TestUploadDocumentsWithMetadata:
    """Tests for RAGFlowClient.upload_documents_with_metadata()."""

    @patch("app.services.ragflow_client.Config")
    def test_delegates_to_ingestion(self, mock_config):
        """Should delegate to ingestion workflow."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_workflow = Mock()
        mock_workflow.ingest_with_metadata.return_value = []
        client._ingestion_workflow = mock_workflow

        result = client.upload_documents_with_metadata("ds-1", [])

        mock_workflow.ingest_with_metadata.assert_called_once_with(
            "ds-1", [], check_duplicates=True, wait_timeout=10.0, poll_interval=0.5
        )
        assert result == []


# ── TestMakeRequestRetryPaths ─────────────────────────────────────────


class TestMakeRequestRetryPaths:
    """Tests for HttpAdapter retry/error edge cases."""

    @patch("time.sleep")
    def test_request_exception_retries_then_raises(self, mock_sleep):
        """RequestException on all attempts raises after exhausting retries."""
        import requests

        adapter = HttpAdapter("http://ragflow:9380", api_key="k", max_retries=2)

        with patch.object(
            adapter.session, "request",
            side_effect=requests.ConnectionError("refused"),
        ):
            with pytest.raises(requests.ConnectionError):
                adapter.request("GET", "/test")

    @patch("time.sleep")
    def test_5xx_on_last_attempt_returns_response(self, mock_sleep):
        """5xx on last attempt returns the response instead of retrying."""
        adapter = HttpAdapter("http://ragflow:9380", api_key="k", max_retries=3)

        with patch.object(adapter.session, "request") as mock_req:
            mock_req.return_value = Mock(status_code=503)

            resp = adapter.request("GET", "/test")
            assert resp.status_code == 503
            assert mock_req.call_count == 3

    def test_custom_timeout_passed(self):
        """Custom timeout kwarg is forwarded to session.request."""
        adapter = HttpAdapter("http://ragflow:9380", api_key="k")

        with patch.object(adapter.session, "request") as mock_req:
            mock_req.return_value = Mock(status_code=200)

            adapter.request("GET", "/test", timeout=5)

            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["timeout"] == 5


# ── TestSessionConfigMethods ─────────────────────────────────────────


class TestSessionConfigMethods:
    """Tests for catalog and session configuration methods."""

    @patch("app.services.ragflow_client.Config")
    def test_list_pdf_parsers_returns_static(self, mock_config):
        """list_pdf_parsers returns static PDF_PARSERS list."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")
        parsers = client.list_pdf_parsers()
        assert parsers == PDF_PARSERS

    @patch("app.services.ragflow_client.Config")
    def test_list_chunk_methods_returns_static(self, mock_config):
        """list_chunk_methods returns static CHUNK_METHODS list."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")
        methods = client.list_chunk_methods()
        assert methods == CHUNK_METHODS

    @patch("app.services.ragflow_client.Config")
    def test_list_ingestion_pipelines_success(self, mock_config):
        """list_ingestion_pipelines returns data from API."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": [{"id": "p1", "name": "Pipeline1"}]}

        with patch.object(client.http, "request", return_value=mock_resp):
            pipelines = client.list_ingestion_pipelines()

        assert len(pipelines) == 1
        assert pipelines[0]["name"] == "Pipeline1"

    @patch("app.services.ragflow_client.Config")
    def test_list_ingestion_pipelines_exception(self, mock_config):
        """list_ingestion_pipelines returns empty on exception."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        with patch.object(client.http, "request", side_effect=ConnectionError("down")):
            pipelines = client.list_ingestion_pipelines()

        assert pipelines == []

    @patch("app.services.ragflow_client.Config")
    def test_list_ingestion_pipelines_non_ok(self, mock_config):
        """list_ingestion_pipelines returns empty on non-ok response."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = False

        with patch.object(client.http, "request", return_value=mock_resp):
            pipelines = client.list_ingestion_pipelines()

        assert pipelines == []


# ── TestListEmbeddingModels ───────────────────────────────────────────


class TestListEmbeddingModels:
    """Tests for RAGFlowClient.list_embedding_models()."""

    @patch("app.services.ragflow_client.Config")
    def test_no_session_returns_empty(self, mock_config):
        """Returns empty list when session auth not configured."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")
        assert client.list_embedding_models() == []

    @patch("app.services.ragflow_client.Config")
    def test_with_session_returns_data(self, mock_config):
        """Returns model list when session auth configured."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = "user"
        mock_config.RAGFLOW_PASSWORD = "pass"
        mock_config.RAGFLOW_PUBLIC_KEY = ""

        client = RAGFlowClient(
            api_url="http://ragflow:9380", api_key="key",
            username="user", password="pass",
        )
        mock_session = Mock()
        mock_session.get.return_value = {"data": [{"name": "bge-large"}]}
        client._session_auth = mock_session

        models = client.list_embedding_models()
        assert len(models) == 1
        assert models[0]["name"] == "bge-large"


# ── TestIngestionPropertyLazy ─────────────────────────────────────────


class TestIngestionPropertyLazy:
    """Tests for lazy-loaded ingestion workflow property."""

    @patch("app.services.ragflow_client.Config")
    def test_ingestion_lazy_created(self, mock_config):
        """Ingestion workflow is created on first access."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")
        assert client._ingestion_workflow is None

        workflow = client.ingestion
        assert workflow is not None
        assert client._ingestion_workflow is workflow

        # Second access returns same instance
        workflow2 = client.ingestion
        assert workflow is workflow2


# ── TestWaitForParsing ────────────────────────────────────────────────


class TestWaitForParsing:
    """Tests for RAGFlowClient.wait_for_parsing()."""

    @patch("app.services.ragflow_client.Config")
    @patch("app.services.ragflow_client.time")
    def test_all_target_ids_completed(self, mock_time, mock_config):
        """Returns True when all target document IDs are parsed."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_time.time.side_effect = [0, 1.0]
        mock_time.sleep = Mock()

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [
                {"id": "d1", "status": "parsed"},
                {"id": "d2", "status": "completed"},
            ]
        }

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.wait_for_parsing("ds-1", document_ids=["d1", "d2"], timeout=30)

        assert result is True

    @patch("app.services.ragflow_client.Config")
    @patch("app.services.ragflow_client.time")
    def test_no_target_ids_returns_on_any_completed(self, mock_time, mock_config):
        """Returns True when any document completed if no target_ids given."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_time.time.side_effect = [0, 1.0]
        mock_time.sleep = Mock()

        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "data": [{"id": "d1", "status": "parsed"}]
        }

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.wait_for_parsing("ds-1", timeout=30)

        assert result is True


# ── TestTriggerParsing ────────────────────────────────────────────────


class TestTriggerParsing:
    """Tests for RAGFlowClient.trigger_parsing()."""

    @patch("app.services.ragflow_client.Config")
    def test_trigger_parsing_success(self, mock_config):
        """Returns True on successful parsing trigger."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = True

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.trigger_parsing("ds-1", document_ids=["d1", "d2"])

        assert result is True

    @patch("app.services.ragflow_client.Config")
    def test_trigger_parsing_failure(self, mock_config):
        """Returns False on failed parsing trigger."""
        mock_config.RAGFLOW_API_URL = "http://ragflow:9380"
        mock_config.RAGFLOW_API_KEY = "key"
        mock_config.RAGFLOW_USERNAME = ""
        mock_config.RAGFLOW_PASSWORD = ""

        client = RAGFlowClient(api_url="http://ragflow:9380", api_key="key")

        mock_resp = Mock()
        mock_resp.ok = False

        with patch.object(client.http, "request", return_value=mock_resp):
            result = client.trigger_parsing("ds-1")

        assert result is False
