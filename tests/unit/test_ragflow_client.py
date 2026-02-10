"""Unit tests for RAGFlowClient core client.

Tests the HTTP adapter, client init, and API methods.
The workflow layer is covered by test_ragflow_ingestion_workflow.py.
"""

from __future__ import annotations

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
