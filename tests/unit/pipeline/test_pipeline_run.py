"""Unit tests for Pipeline.run() orchestration logic.

Individual step methods are covered by test_pipeline_steps.py (28 tests).
These tests focus on flow control, counter accumulation, and error recovery
in run() itself.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.orchestrator.pipeline import Pipeline
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
        upload_to_ragflow=False,
        upload_to_paperless=False,
        verify_document_timeout=5,
        container=mock_container,
    )


def _make_scraper_result(status="completed", downloaded_count=0, scraped_count=0,
                         documents=None, errors=None):
    """Helper to create a mock scraper result."""
    result = Mock()
    result.status = status
    result.downloaded_count = downloaded_count
    result.scraped_count = scraped_count
    result.documents = documents or []
    result.errors = errors or []
    return result


def _make_doc_dict(title="Test Doc", url="http://example.com/doc.pdf",
                   pdf_path=None, **extra):
    """Helper to create a document dict."""
    d = {
        "url": url,
        "title": title,
        "filename": "doc.pdf",
        "tags": [],
        "extra": {},
    }
    if pdf_path:
        d["pdf_path"] = str(pdf_path)
    d.update(extra)
    return d


# ── TestRunScraperFails ─────────────────────────────────────────────────


class TestRunScraperFails:
    """Tests for scraper-level failures in Pipeline.run()."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_scraper_not_found_raises(self, mock_registry, pipeline):
        """ValueError propagated when scraper is not found."""
        mock_registry.get_scraper.return_value = None

        result = pipeline.run()

        assert result.status == "failed"
        assert any("not found" in e.lower() for e in result.errors)

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_scraper_returns_failed_status(self, mock_registry, pipeline):
        """Early return when scraper result.status == 'failed'."""
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="failed", errors=["Network timeout"]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.status == "failed"
        assert "Scraper failed" in result.errors

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_scraper_errors_propagated(self, mock_registry, pipeline):
        """Scraper errors are included in final result."""
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="failed", errors=["Error A", "Error B"]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert "Error A" in result.errors
        assert "Error B" in result.errors


# ── TestRunNoDocuments ──────────────────────────────────────────────────


class TestRunNoDocuments:
    """Tests when scraper returns no documents."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_zero_downloads_returns_completed(self, mock_registry, pipeline):
        """Status is 'completed' when downloaded_count is 0."""
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=0, scraped_count=5
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.status == "completed"
        assert result.downloaded_count == 0

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_scraped_count_passed_through(self, mock_registry, pipeline):
        """scraped_count from scraper result is preserved."""
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=0, scraped_count=42
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.scraped_count == 42


# ── TestRunDocumentProcessing ───────────────────────────────────────────


class TestRunDocumentProcessing:
    """Tests for document processing loop in Pipeline.run()."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_single_doc_success(self, mock_registry, pipeline, tmp_path):
        """Single document success increments all counters."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        doc = _make_doc_dict(pdf_path=pdf)
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=1, documents=[doc]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(return_value={
            "parsed": True, "archived": True, "verified": True, "rag_indexed": False,
        })

        result = pipeline.run()

        assert result.parsed_count == 1
        assert result.archived_count == 1
        assert result.verified_count == 1
        assert result.failed_count == 0
        assert result.status == "completed"

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_two_docs_both_succeed(self, mock_registry, pipeline, tmp_path):
        """Two documents processed, both succeed."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2 = tmp_path / "doc2.pdf"
        pdf2.write_bytes(b"%PDF-1.4")

        docs = [
            _make_doc_dict(title="Doc 1", pdf_path=pdf1),
            _make_doc_dict(title="Doc 2", pdf_path=pdf2),
        ]
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=2, documents=docs
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(return_value={
            "parsed": True, "archived": True, "verified": True, "rag_indexed": True,
        })

        result = pipeline.run()

        assert result.parsed_count == 2
        assert result.rag_indexed_count == 2
        assert pipeline._process_document.call_count == 2

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_missing_file_path_skipped(self, mock_registry, pipeline):
        """Document with no file_path is skipped (failed_count++)."""
        doc = {"url": "http://example.com", "title": "No Path", "filename": "x.pdf",
               "tags": [], "extra": {}}
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=1, documents=[doc]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.failed_count == 1

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_file_not_found_skipped(self, mock_registry, pipeline):
        """Document with non-existent file is skipped."""
        doc = _make_doc_dict(pdf_path="/nonexistent/doc.pdf")
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=1, documents=[doc]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.failed_count == 1

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_invalid_metadata_fields_dropped(self, mock_registry, pipeline, tmp_path):
        """Unknown fields in doc_dict are dropped from DocumentMetadata."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        doc = _make_doc_dict(pdf_path=pdf, unknown_field="should_be_dropped")
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=1, documents=[doc]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(return_value={
            "parsed": True, "archived": False, "verified": False, "rag_indexed": False,
        })

        result = pipeline.run()

        # Should not fail — unknown fields are just dropped
        assert result.parsed_count == 1
        assert result.failed_count == 0


# ── TestRunErrorRecovery ────────────────────────────────────────────────


class TestRunErrorRecovery:
    """Tests for per-document error recovery in Pipeline.run()."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_parser_error_continues_loop(self, mock_registry, pipeline, tmp_path):
        """ParserBackendError doesn't stop processing of remaining docs."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2 = tmp_path / "doc2.pdf"
        pdf2.write_bytes(b"%PDF-1.4")

        docs = [
            _make_doc_dict(title="Doc 1", pdf_path=pdf1),
            _make_doc_dict(title="Doc 2", pdf_path=pdf2),
        ]
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=2, documents=docs
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(side_effect=[
            ParserBackendError("OCR failed"),
            {"parsed": True, "archived": True, "verified": True, "rag_indexed": False},
        ])

        result = pipeline.run()

        assert result.failed_count == 1
        assert result.parsed_count == 1
        assert result.status == "partial"

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_archive_error_continues_loop(self, mock_registry, pipeline, tmp_path):
        """ArchiveError doesn't stop processing of remaining docs."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2 = tmp_path / "doc2.pdf"
        pdf2.write_bytes(b"%PDF-1.4")

        docs = [
            _make_doc_dict(title="Doc 1", pdf_path=pdf1),
            _make_doc_dict(title="Doc 2", pdf_path=pdf2),
        ]
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=2, documents=docs
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(side_effect=[
            ArchiveError("Service down"),
            {"parsed": True, "archived": True, "verified": True, "rag_indexed": False},
        ])

        result = pipeline.run()

        assert result.failed_count == 1
        assert result.parsed_count == 1

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_generic_exception_continues_loop(self, mock_registry, pipeline, tmp_path):
        """Generic Exception doesn't stop processing of remaining docs."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2 = tmp_path / "doc2.pdf"
        pdf2.write_bytes(b"%PDF-1.4")

        docs = [
            _make_doc_dict(title="Doc 1", pdf_path=pdf1),
            _make_doc_dict(title="Doc 2", pdf_path=pdf2),
        ]
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=2, documents=docs
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(side_effect=[
            RuntimeError("Unexpected"),
            {"parsed": True, "archived": False, "verified": False, "rag_indexed": False},
        ])

        result = pipeline.run()

        assert result.failed_count == 1
        assert result.parsed_count == 1


# ── TestRunStatusDetermination ──────────────────────────────────────────


class TestRunStatusDetermination:
    """Tests for final status logic in Pipeline.run()."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_all_succeed_completed(self, mock_registry, pipeline, tmp_path):
        """All docs succeed → status 'completed'."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=1,
            documents=[_make_doc_dict(pdf_path=pdf)]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(return_value={
            "parsed": True, "archived": True, "verified": True, "rag_indexed": False,
        })

        result = pipeline.run()

        assert result.status == "completed"

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_some_fail_partial(self, mock_registry, pipeline, tmp_path):
        """Some docs fail → status 'partial'."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2 = tmp_path / "doc2.pdf"
        pdf2.write_bytes(b"%PDF-1.4")

        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=2,
            documents=[
                _make_doc_dict(title="Doc 1", pdf_path=pdf1),
                _make_doc_dict(title="Doc 2", pdf_path=pdf2),
            ]
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline._process_document = Mock(side_effect=[
            ParserBackendError("fail"),
            {"parsed": True, "archived": True, "verified": True, "rag_indexed": False},
        ])

        result = pipeline.run()

        assert result.status == "partial"

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_top_level_exception_failed(self, mock_registry, pipeline):
        """Top-level exception → status 'failed'."""
        mock_registry.get_scraper.side_effect = RuntimeError("Registry broken")

        result = pipeline.run()

        assert result.status == "failed"
        assert any("Registry broken" in e for e in result.errors)


# ── TestRunPreflightReconciliation ──────────────────────────────────────


class TestRunPreflightReconciliation:
    """Tests for pre-flight reconciliation step."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    @patch("app.services.reconciliation.ReconciliationService")
    def test_preflight_called_when_paperless_enabled(
        self, mock_recon_cls, mock_registry, mock_container
    ):
        """Reconciliation is called when upload_to_paperless=True."""
        pipeline = Pipeline(
            scraper_name="test",
            upload_to_ragflow=False,
            upload_to_paperless=True,
            container=mock_container,
        )

        mock_recon = Mock()
        mock_recon.preflight_sync.return_value = 3
        mock_recon_cls.return_value = mock_recon

        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=0
        )
        mock_registry.get_scraper.return_value = mock_scraper

        pipeline.run()

        mock_recon.preflight_sync.assert_called_once_with("test")

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    @patch("app.services.reconciliation.ReconciliationService")
    def test_preflight_failure_is_nonfatal(
        self, mock_recon_cls, mock_registry, mock_container
    ):
        """Reconciliation failure doesn't stop the pipeline."""
        pipeline = Pipeline(
            scraper_name="test",
            upload_to_ragflow=False,
            upload_to_paperless=True,
            container=mock_container,
        )

        mock_recon_cls.side_effect = RuntimeError("Paperless unreachable")

        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=0
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        # Pipeline continues despite reconciliation failure
        assert result.status == "completed"


# ── TestRunFinalization ─────────────────────────────────────────────────


class TestRunFinalization:
    """Tests for finalization in Pipeline.run()."""

    @patch("app.orchestrator.pipeline.ScraperRegistry")
    def test_duration_and_completed_at_populated(self, mock_registry, pipeline):
        """duration_seconds and completed_at are set."""
        mock_scraper = Mock()
        mock_scraper.run.return_value = _make_scraper_result(
            status="completed", downloaded_count=0
        )
        mock_registry.get_scraper.return_value = mock_scraper

        result = pipeline.run()

        assert result.duration_seconds > 0
        assert result.completed_at is not None
