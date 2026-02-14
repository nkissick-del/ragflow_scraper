"""Unit tests for extracted Pipeline step methods.

Tests each method in isolation with mocked container/backends.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from app.orchestrator.pipeline import Pipeline
from app.backends.parsers.base import ParserResult
from app.backends.archives.base import ArchiveResult
from app.utils.errors import ParserBackendError, ArchiveError


@pytest.fixture
def mock_container():
    """Create mock service container."""
    container = Mock()
    container.settings.get.return_value = ""
    container.ragflow_client = Mock()
    return container


@pytest.fixture
def pipeline(mock_container):
    """Create a Pipeline instance with mocked dependencies."""
    return Pipeline(
        scraper_name="test",
        dataset_id="ds-1",
        upload_to_ragflow=True,
        upload_to_paperless=True,
        verify_document_timeout=5,
        container=mock_container,
    )


# ── TestParseDocument ────────────────────────────────────────────────────


class TestParseDocument:
    """Tests for Pipeline._parse_document()."""

    @patch("app.orchestrator.pipeline.Config")
    def test_pdf_uses_parser_backend(self, mock_config, pipeline, tmp_path):
        """PDF doc_type calls parser_backend.parse_document()."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Parsed")

        parser_result = ParserResult(
            success=True,
            markdown_path=md_file,
            metadata={"title": "Parsed Title", "page_count": 3},
            parser_name="docling",
        )
        pipeline.container.parser_backend.parse_document.return_value = parser_result

        md_path, meta = pipeline._parse_document(
            pdf_file, Mock(), "pdf"
        )

        assert md_path == md_file
        assert meta["title"] == "Parsed Title"
        assert meta["page_count"] == 3
        pipeline.container.parser_backend.parse_document.assert_called_once()

    @patch("app.orchestrator.pipeline.Config")
    def test_pdf_parser_failure_raises(self, mock_config, pipeline, tmp_path):
        """ParserBackendError raised when parser returns success=False."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        parser_result = ParserResult(
            success=False,
            error="OCR failed",
            parser_name="docling",
        )
        pipeline.container.parser_backend.parse_document.return_value = parser_result

        with pytest.raises(ParserBackendError, match="OCR failed"):
            pipeline._parse_document(pdf_file, Mock(), "pdf")

    @patch("app.orchestrator.pipeline.Config")
    def test_pdf_parser_no_markdown_raises(self, mock_config, pipeline, tmp_path):
        """ParserBackendError raised when markdown_path is None despite success."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        # ParserResult.__post_init__ validates this, so we mock directly
        mock_result = Mock()
        mock_result.success = True
        mock_result.markdown_path = None
        mock_result.parser_name = "docling"
        mock_result.error = None
        mock_result.metadata = {}
        pipeline.container.parser_backend.parse_document.return_value = mock_result

        with pytest.raises(ParserBackendError, match="no markdown_path"):
            pipeline._parse_document(pdf_file, Mock(), "pdf")

    @patch("app.orchestrator.pipeline.Config")
    def test_markdown_skips_parser(self, mock_config, pipeline, tmp_path):
        """Markdown doc_type returns file_path directly without calling parser."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""

        md_file = tmp_path / "doc.md"
        md_file.write_text("# Already Markdown")

        md_path, meta = pipeline._parse_document(
            md_file, Mock(), "markdown"
        )

        assert md_path == md_file
        assert meta == {}
        pipeline.container.parser_backend.parse_document.assert_not_called()

    @patch("app.orchestrator.pipeline.Config")
    def test_office_uses_tika(self, mock_config, pipeline, tmp_path):
        """Office doc_type calls tika_client for extraction."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = "http://tika:9998"

        docx_file = tmp_path / "doc.docx"
        docx_file.write_bytes(b"fake docx")

        mock_tika = Mock()
        mock_tika.extract_text.return_value = "Office text content."
        mock_tika.extract_metadata.return_value = {"title": "Office Doc"}
        pipeline.container.tika_client = mock_tika

        doc_metadata = Mock()
        doc_metadata.title = "Scraper Title"

        md_path, meta = pipeline._parse_document(
            docx_file, doc_metadata, "office"
        )

        assert md_path == docx_file.with_suffix(".md")
        assert md_path.exists()
        assert meta["title"] == "Office Doc"
        mock_tika.extract_text.assert_called_once_with(docx_file)
        mock_tika.extract_metadata.assert_called_once_with(docx_file)
        pipeline.container.parser_backend.parse_document.assert_not_called()

    @patch("app.orchestrator.pipeline.Config")
    def test_office_empty_text_raises(self, mock_config, pipeline, tmp_path):
        """ParserBackendError raised when Tika returns empty text."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = "http://tika:9998"

        docx_file = tmp_path / "doc.docx"
        docx_file.write_bytes(b"fake docx")

        mock_tika = Mock()
        mock_tika.extract_text.return_value = "   "
        pipeline.container.tika_client = mock_tika

        with pytest.raises(ParserBackendError, match="empty text"):
            pipeline._parse_document(docx_file, Mock(), "office")

    @patch("app.orchestrator.pipeline.Config")
    def test_office_no_tika_configured_raises(self, mock_config, pipeline, tmp_path):
        """ParserBackendError raised when TIKA_SERVER_URL is empty."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""

        docx_file = tmp_path / "doc.docx"
        docx_file.write_bytes(b"fake docx")

        with pytest.raises(ParserBackendError, match="Tika not configured"):
            pipeline._parse_document(docx_file, Mock(), "office")

    @patch("app.orchestrator.pipeline.Config")
    def test_html_goes_through_parser(self, mock_config, pipeline, tmp_path):
        """HTML doc_type is sent through the parser backend (e.g. docling)."""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""
        mock_config.LLM_ENRICHMENT_ENABLED = False

        html_file = tmp_path / "doc.html"
        html_file.write_text("<h1>Already HTML</h1>")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Already HTML")

        parser_result = ParserResult(
            success=True,
            markdown_path=md_file,
            parser_name="docling_serve",
            metadata={"content_type": "text/html"},
        )
        pipeline.container.parser_backend.parse_document.return_value = parser_result

        content_path, meta = pipeline._parse_document(
            html_file, Mock(), "html"
        )

        assert content_path == md_file
        assert meta == {"content_type": "text/html"}
        pipeline.container.parser_backend.parse_document.assert_called_once()

    @patch("app.orchestrator.pipeline.Config")
    def test_tika_enrichment_called(self, mock_config, pipeline, tmp_path):
        """Tika enrichment is invoked after parsing."""
        mock_config.TIKA_ENRICHMENT_ENABLED = True
        mock_config.TIKA_SERVER_URL = "http://tika:9998"

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Parsed")

        parser_result = ParserResult(
            success=True,
            markdown_path=md_file,
            metadata={"title": "Parsed"},
            parser_name="docling",
        )
        pipeline.container.parser_backend.parse_document.return_value = parser_result
        pipeline.container.tika_client.extract_metadata.return_value = {
            "author": "Enriched Author"
        }

        md_path, meta = pipeline._parse_document(
            pdf_file, Mock(), "pdf"
        )

        # Tika enrichment should have added author
        assert meta["author"] == "Enriched Author"
        pipeline.container.tika_client.extract_metadata.assert_called_once()


# ── TestPrepareArchiveFile ───────────────────────────────────────────────


class TestPrepareArchiveFile:
    """Tests for Pipeline._prepare_archive_file()."""

    @patch("app.orchestrator.pipeline.Config")
    def test_pdf_returns_original(self, mock_config, pipeline, tmp_path):
        """PDF doc_type returns (file_path, None) — no conversion needed."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        md_file = tmp_path / "doc.md"

        archive_path, cleanup_path = pipeline._prepare_archive_file(
            pdf_file, md_file, "pdf", Mock()
        )

        assert archive_path == pdf_file
        assert cleanup_path is None

    @patch("app.orchestrator.pipeline.Config")
    def test_markdown_gotenberg_conversion(self, mock_config, pipeline, tmp_path):
        """Markdown uses Gotenberg to create .archive.pdf."""
        mock_config.GOTENBERG_URL = "http://gotenberg:3156"

        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test")

        mock_gotenberg = Mock()
        mock_gotenberg.convert_markdown_to_pdf.return_value = b"%PDF-1.4 gotenberg"
        pipeline.container.gotenberg_client = mock_gotenberg

        merged = Mock()
        merged.title = "Test Doc"

        archive_path, cleanup_path = pipeline._prepare_archive_file(
            md_file, md_file, "markdown", merged
        )

        assert str(archive_path).endswith(".archive.pdf")
        assert archive_path == cleanup_path
        assert archive_path.exists()
        mock_gotenberg.convert_markdown_to_pdf.assert_called_once()

    @patch("app.orchestrator.pipeline.Config")
    def test_office_gotenberg_conversion(self, mock_config, pipeline, tmp_path):
        """Office files use Gotenberg convert_to_pdf()."""
        mock_config.GOTENBERG_URL = "http://gotenberg:3156"

        docx_file = tmp_path / "doc.docx"
        docx_file.write_bytes(b"fake docx")
        md_file = tmp_path / "doc.md"

        mock_gotenberg = Mock()
        mock_gotenberg.convert_to_pdf.return_value = b"%PDF-1.4 office"
        pipeline.container.gotenberg_client = mock_gotenberg

        archive_path, cleanup_path = pipeline._prepare_archive_file(
            docx_file, md_file, "office", Mock()
        )

        assert str(archive_path).endswith(".archive.pdf")
        assert cleanup_path is not None
        mock_gotenberg.convert_to_pdf.assert_called_once_with(docx_file)

    @patch("app.orchestrator.pipeline.Config")
    def test_html_gotenberg_conversion(self, mock_config, pipeline, tmp_path):
        """HTML uses Gotenberg convert_html_to_pdf to create .archive.pdf."""
        mock_config.GOTENBERG_URL = "http://gotenberg:3156"

        html_file = tmp_path / "doc.html"
        html_file.write_text("<h1>Test</h1><p>Content</p>")

        mock_gotenberg = Mock()
        mock_gotenberg.convert_html_to_pdf.return_value = b"%PDF-1.4 html"
        pipeline.container.gotenberg_client = mock_gotenberg

        merged = Mock()
        merged.title = "Test Doc"

        archive_path, cleanup_path = pipeline._prepare_archive_file(
            html_file, html_file, "html", merged
        )

        assert str(archive_path).endswith(".archive.pdf")
        assert archive_path == cleanup_path
        assert archive_path.exists()
        mock_gotenberg.convert_html_to_pdf.assert_called_once()

    @patch("app.orchestrator.pipeline.Config")
    def test_gotenberg_failure_falls_back(self, mock_config, pipeline, tmp_path):
        """Gotenberg exception falls back to original file."""
        mock_config.GOTENBERG_URL = "http://gotenberg:3156"

        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test")

        mock_gotenberg = Mock()
        mock_gotenberg.convert_markdown_to_pdf.side_effect = ConnectionError("down")
        pipeline.container.gotenberg_client = mock_gotenberg

        archive_path, cleanup_path = pipeline._prepare_archive_file(
            md_file, md_file, "markdown", Mock()
        )

        assert archive_path == md_file
        assert cleanup_path is None


# ── TestArchiveDocument ──────────────────────────────────────────────────


class TestArchiveDocument:
    """Tests for Pipeline._archive_document()."""

    def test_archive_success_returns_document_id(self, pipeline, tmp_path):
        """Returns document_id on successful archive."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        archive_result = ArchiveResult(
            success=True, document_id="123", archive_name="paperless"
        )
        pipeline.container.archive_backend.archive_document.return_value = archive_result

        merged = Mock()
        merged.title = "Test"
        merged.publication_date = "2024-01-15"
        merged.organization = "TestOrg"
        merged.tags = ["tag1"]
        merged.to_dict.return_value = {"title": "Test"}

        doc_id = pipeline._archive_document(pdf_file, merged)

        assert doc_id == "123"
        pipeline.container.archive_backend.archive_document.assert_called_once()

    def test_archive_failure_raises(self, pipeline, tmp_path):
        """ArchiveError raised when archive returns success=False."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        archive_result = ArchiveResult(
            success=False, error="Service unavailable", archive_name="paperless"
        )
        pipeline.container.archive_backend.archive_document.return_value = archive_result

        merged = Mock()
        merged.title = "Test"
        merged.publication_date = None
        merged.organization = None
        merged.tags = []
        merged.to_dict.return_value = {"title": "Test"}

        with pytest.raises(ArchiveError, match="Service unavailable"):
            pipeline._archive_document(pdf_file, merged)

    def test_metadata_includes_scraper_name(self, pipeline, tmp_path):
        """scraper_name is injected into the metadata dict."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        archive_result = ArchiveResult(
            success=True, document_id="456", archive_name="paperless"
        )
        pipeline.container.archive_backend.archive_document.return_value = archive_result

        merged = Mock()
        merged.title = "Test"
        merged.publication_date = None
        merged.organization = None
        merged.tags = []
        merged.to_dict.return_value = {"title": "Test"}

        pipeline._archive_document(pdf_file, merged)

        call_kwargs = pipeline.container.archive_backend.archive_document.call_args[1]
        assert call_kwargs["metadata"]["scraper_name"] == "test"

    def test_metadata_fields_passed_correctly(self, pipeline, tmp_path):
        """Title, created, correspondent, tags are passed to archive backend."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        archive_result = ArchiveResult(
            success=True, document_id="789", archive_name="paperless"
        )
        pipeline.container.archive_backend.archive_document.return_value = archive_result

        merged = Mock()
        merged.title = "My Document"
        merged.publication_date = "2024-06-01"
        merged.organization = "ACME Corp"
        merged.tags = ["finance", "q2"]
        merged.to_dict.return_value = {"title": "My Document"}

        pipeline._archive_document(pdf_file, merged)

        call_kwargs = pipeline.container.archive_backend.archive_document.call_args[1]
        assert call_kwargs["title"] == "My Document"
        assert call_kwargs["created"] == "2024-06-01"
        assert call_kwargs["correspondent"] == "ACME Corp"
        assert call_kwargs["tags"] == ["finance", "q2"]


# ── TestVerifyDocument ───────────────────────────────────────────────────


class TestVerifyDocument:
    """Tests for Pipeline._verify_document()."""

    def test_verify_success(self, pipeline):
        """Returns True when verify_document() returns True."""
        pipeline.container.archive_backend.verify_document.return_value = True

        assert pipeline._verify_document("123") is True

    def test_verify_timeout(self, pipeline):
        """Returns False when verify_document() returns False."""
        pipeline.container.archive_backend.verify_document.return_value = False

        assert pipeline._verify_document("123") is False

    def test_verify_uses_configured_timeout(self, pipeline):
        """verify_document() is called with self.verify_document_timeout."""
        pipeline.container.archive_backend.verify_document.return_value = True
        pipeline.verify_document_timeout = 42

        pipeline._verify_document("doc-999")

        pipeline.container.archive_backend.verify_document.assert_called_once_with(
            "doc-999", timeout=42
        )


# ── TestIngestToRag ──────────────────────────────────────────────────────


class TestIngestToRag:
    """Tests for Pipeline._ingest_to_rag()."""

    def test_ingest_success(self, pipeline, tmp_path):
        """Returns True on successful RAG ingestion."""
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Content")

        rag_result = Mock()
        rag_result.success = True
        rag_result.document_id = "rag-123"
        pipeline.container.rag_backend.ingest_document.return_value = rag_result

        merged = Mock()
        merged.to_dict.return_value = {"title": "Test"}

        assert pipeline._ingest_to_rag(md_file, merged) is True

    def test_ingest_failure_returns_false(self, pipeline, tmp_path):
        """Returns False on failed RAG ingestion (non-fatal)."""
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Content")

        rag_result = Mock()
        rag_result.success = False
        rag_result.error = "Workspace full"
        pipeline.container.rag_backend.ingest_document.return_value = rag_result

        merged = Mock()
        merged.to_dict.return_value = {"title": "Test"}

        assert pipeline._ingest_to_rag(md_file, merged) is False

    def test_ingest_passes_metadata_and_collection(self, pipeline, tmp_path):
        """Verify kwargs: content_path, metadata, collection_id."""
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Content")

        rag_result = Mock()
        rag_result.success = True
        rag_result.document_id = "rag-456"
        pipeline.container.rag_backend.ingest_document.return_value = rag_result

        merged = Mock()
        merged.to_dict.return_value = {"title": "My Doc", "url": "http://example.com"}

        pipeline._ingest_to_rag(md_file, merged)

        call_kwargs = pipeline.container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["content_path"] == md_file
        assert call_kwargs["metadata"] == {"title": "My Doc", "url": "http://example.com"}
        assert call_kwargs["collection_id"] == "ds-1"

    def test_ingest_uses_dataset_id(self, pipeline, tmp_path):
        """collection_id matches self.dataset_id."""
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Content")

        rag_result = Mock()
        rag_result.success = True
        rag_result.document_id = "rag-789"
        pipeline.container.rag_backend.ingest_document.return_value = rag_result

        pipeline.dataset_id = "custom-dataset-42"
        merged = Mock()
        merged.to_dict.return_value = {}

        pipeline._ingest_to_rag(md_file, merged)

        call_kwargs = pipeline.container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["collection_id"] == "custom-dataset-42"


# ── TestCleanupLocalFiles ────────────────────────────────────────────────


class TestCleanupLocalFiles:
    """Tests for Pipeline._cleanup_local_files()."""

    def test_deletes_files_when_verified(self, pipeline, tmp_path):
        """All files removed when result['verified']=True and upload_to_paperless."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md = tmp_path / "doc.md"
        md.write_text("# Content")
        json_f = tmp_path / "doc.json"
        json_f.write_text("{}")

        result = {"verified": True, "rag_indexed": False}

        pipeline._cleanup_local_files(pdf, md, None, {}, result)

        assert not pdf.exists()
        assert not md.exists()
        assert not json_f.exists()

    def test_deletes_files_when_rag_only_indexed(self, pipeline, tmp_path):
        """Files removed in RAG-only mode when rag_indexed=True."""
        pipeline.upload_to_paperless = False

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md = tmp_path / "doc.md"
        md.write_text("# Content")

        result = {"verified": False, "rag_indexed": True}

        pipeline._cleanup_local_files(pdf, md, None, {}, result)

        assert not pdf.exists()
        assert not md.exists()

    def test_keeps_files_when_not_verified(self, pipeline, tmp_path):
        """No deletion when verified=False and upload_to_paperless=True."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md = tmp_path / "doc.md"
        md.write_text("# Content")

        result = {"verified": False, "rag_indexed": False}

        pipeline._cleanup_local_files(pdf, md, None, {}, result)

        assert pdf.exists()
        assert md.exists()

    def test_deletes_archive_pdf(self, pipeline, tmp_path):
        """Gotenberg .archive.pdf is cleaned up."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md = tmp_path / "doc.md"
        md.write_text("# Content")
        archive_pdf = tmp_path / "doc.archive.pdf"
        archive_pdf.write_bytes(b"%PDF-1.4 gotenberg")

        result = {"verified": True, "rag_indexed": False}

        pipeline._cleanup_local_files(pdf, md, archive_pdf, {}, result)

        assert not archive_pdf.exists()

    def test_cleanup_failure_is_nonfatal(self, pipeline, tmp_path):
        """OSError during unlink doesn't propagate."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        md = tmp_path / "doc.md"
        md.write_text("# Content")

        result = {"verified": True, "rag_indexed": False}

        # Make unlink fail by using a mock that raises
        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            # Should not raise
            pipeline._cleanup_local_files(pdf, md, None, {}, result)
