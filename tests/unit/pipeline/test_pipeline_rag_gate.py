"""Tests for the pipeline RAG gate fix.

Verifies that RAG ingestion proceeds regardless of dataset_id value
when upload_to_ragflow=True.
"""

import pytest
from unittest.mock import Mock, patch

from app.orchestrator.pipeline import Pipeline
from app.backends.parsers.base import ParserResult
from app.scrapers.models import DocumentMetadata


@pytest.fixture
def mock_container():
    """Create mock service container."""
    container = Mock()
    container.settings.get.return_value = ""
    container.ragflow_client = Mock()
    return container


def _make_doc_metadata():
    """Create a DocumentMetadata instance for testing."""
    return DocumentMetadata(
        url="https://example.com/test.pdf",
        title="Test Document",
        filename="test.pdf",
    )


class TestRAGGateWithDatasetId:
    """Test that RAG ingestion works with an explicit dataset_id."""

    @patch("app.orchestrator.pipeline.Config")
    def test_rag_ingestion_with_dataset_id(self, mock_config, mock_container, tmp_path):
        """RAG ingestion should proceed when dataset_id is set."""
        mock_config.RAGFLOW_DATASET_ID = "test-dataset"
        mock_config.METADATA_MERGE_STRATEGY = "smart"
        mock_config.GOTENBERG_URL = ""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""
        mock_config.LLM_ENRICHMENT_ENABLED = False

        pipeline = Pipeline(
            scraper_name="test",
            dataset_id="ds-explicit",
            upload_to_ragflow=True,
            upload_to_paperless=False,
            container=mock_container,
        )

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test Content")

        parser_result = ParserResult(
            success=True,
            markdown_path=md_file,
            metadata={"title": "Test"},
            parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        rag_result = Mock(success=True, document_id="rag-1")
        mock_container.rag_backend.ingest_document.return_value = rag_result

        result = pipeline._process_document(_make_doc_metadata(), pdf_file)

        assert result["rag_indexed"] is True
        mock_container.rag_backend.ingest_document.assert_called_once()
        call_kwargs = mock_container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["collection_id"] == "ds-explicit"


class TestRAGGateWithoutDatasetId:
    """Test that RAG ingestion works WITHOUT a dataset_id (the fix)."""

    @patch("app.orchestrator.pipeline.Config")
    def test_rag_ingestion_without_dataset_id(self, mock_config, mock_container, tmp_path):
        """RAG ingestion should proceed even when dataset_id is None."""
        mock_config.RAGFLOW_DATASET_ID = ""
        mock_config.METADATA_MERGE_STRATEGY = "smart"
        mock_config.GOTENBERG_URL = ""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""
        mock_config.LLM_ENRICHMENT_ENABLED = False

        pipeline = Pipeline(
            scraper_name="test",
            dataset_id=None,
            upload_to_ragflow=True,
            upload_to_paperless=False,
            container=mock_container,
        )

        assert pipeline.dataset_id is None

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test Content")

        parser_result = ParserResult(
            success=True,
            markdown_path=md_file,
            metadata={"title": "Test"},
            parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        rag_result = Mock(success=True, document_id="rag-2")
        mock_container.rag_backend.ingest_document.return_value = rag_result

        result = pipeline._process_document(_make_doc_metadata(), pdf_file)

        assert result["rag_indexed"] is True
        mock_container.rag_backend.ingest_document.assert_called_once()
        call_kwargs = mock_container.rag_backend.ingest_document.call_args[1]
        assert call_kwargs["collection_id"] is None

    @patch("app.orchestrator.pipeline.Config")
    def test_rag_ingestion_with_empty_string_dataset_id(self, mock_config, mock_container, tmp_path):
        """Empty string dataset_id should normalize to None and still ingest."""
        mock_config.RAGFLOW_DATASET_ID = ""
        mock_config.METADATA_MERGE_STRATEGY = "smart"
        mock_config.GOTENBERG_URL = ""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""
        mock_config.LLM_ENRICHMENT_ENABLED = False

        pipeline = Pipeline(
            scraper_name="test",
            dataset_id="",
            upload_to_ragflow=True,
            upload_to_paperless=False,
            container=mock_container,
        )

        assert pipeline.dataset_id is None

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test")

        parser_result = ParserResult(
            success=True, markdown_path=md_file, metadata={}, parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        rag_result = Mock(success=True, document_id="rag-3")
        mock_container.rag_backend.ingest_document.return_value = rag_result

        result = pipeline._process_document(_make_doc_metadata(), pdf_file)

        assert result["rag_indexed"] is True


class TestRAGGateDisabled:
    """Test that RAG ingestion is skipped when upload_to_ragflow=False."""

    @patch("app.orchestrator.pipeline.Config")
    def test_rag_skipped_when_disabled(self, mock_config, mock_container, tmp_path):
        """RAG ingestion should NOT proceed when upload_to_ragflow=False."""
        mock_config.RAGFLOW_DATASET_ID = "test-dataset"
        mock_config.METADATA_MERGE_STRATEGY = "smart"
        mock_config.GOTENBERG_URL = ""
        mock_config.TIKA_ENRICHMENT_ENABLED = False
        mock_config.TIKA_SERVER_URL = ""
        mock_config.LLM_ENRICHMENT_ENABLED = False

        pipeline = Pipeline(
            scraper_name="test",
            dataset_id="ds-1",
            upload_to_ragflow=False,
            upload_to_paperless=False,
            container=mock_container,
        )

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test")

        parser_result = ParserResult(
            success=True, markdown_path=md_file, metadata={}, parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        result = pipeline._process_document(_make_doc_metadata(), pdf_file)

        assert result["rag_indexed"] is False
        mock_container.rag_backend.ingest_document.assert_not_called()


class TestDatasetIdNormalization:
    """Test that dataset_id is properly normalized in the constructor."""

    def test_none_stays_none(self, mock_container):
        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = ""
            p = Pipeline("test", dataset_id=None, container=mock_container)
            assert p.dataset_id is None

    def test_empty_string_becomes_none(self, mock_container):
        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = ""
            p = Pipeline("test", dataset_id="", container=mock_container)
            assert p.dataset_id is None

    def test_explicit_value_preserved(self, mock_container):
        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = ""
            p = Pipeline("test", dataset_id="my-dataset", container=mock_container)
            assert p.dataset_id == "my-dataset"

    def test_config_fallback_used(self, mock_container):
        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = "config-dataset"
            p = Pipeline("test", dataset_id=None, container=mock_container)
            assert p.dataset_id == "config-dataset"

    def test_config_empty_string_normalized(self, mock_container):
        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = ""
            p = Pipeline("test", container=mock_container)
            assert p.dataset_id is None
