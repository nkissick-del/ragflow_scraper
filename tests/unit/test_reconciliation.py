"""Tests for ReconciliationService."""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

from app.services.reconciliation import ReconciliationService, ReconciliationReport


@pytest.fixture
def mock_container():
    """Create a mock ServiceContainer."""
    container = Mock()

    # Mock archive backend with a Paperless client
    mock_client = Mock()
    mock_client.is_configured = True
    mock_client.check_alive.return_value = True
    mock_client.get_scraper_document_urls.return_value = {}
    mock_client.download_document.return_value = b"%PDF test"

    mock_archive = Mock()
    mock_archive.client = mock_client
    container.archive_backend = mock_archive

    # Mock state tracker
    mock_tracker = Mock()
    mock_tracker.get_processed_urls.return_value = []
    mock_tracker.mark_processed = Mock()
    mock_tracker.save = Mock()
    container.state_tracker.return_value = mock_tracker

    # Mock RAG backend
    mock_rag = Mock()
    mock_rag.list_documents.return_value = []
    mock_rag.ingest_document.return_value = Mock(success=True, document_id="rag-1", error=None)
    container.rag_backend = mock_rag

    # Mock parser backend
    mock_parse_result = Mock()
    mock_parse_result.success = True
    mock_parse_result.markdown_path = Mock()
    mock_parse_result.markdown_path.exists.return_value = True
    mock_parse_result.error = None
    mock_parser = Mock()
    mock_parser.parse_document.return_value = mock_parse_result
    container.parser_backend = mock_parser

    return container


@pytest.fixture
def service(mock_container):
    """Create ReconciliationService with mock container."""
    return ReconciliationService(container=mock_container)


class TestPreflightSync:
    """Test pre-flight state sync from Paperless."""

    def test_returns_zero_when_paperless_not_configured(self, mock_container):
        """Should return 0 when Paperless is not configured."""
        mock_container.archive_backend.client.is_configured = False
        service = ReconciliationService(container=mock_container)
        assert service.preflight_sync("aemo") == 0

    def test_returns_zero_when_paperless_unreachable(self, service, mock_container):
        """Should return 0 when Paperless is not reachable."""
        mock_container.archive_backend.client.check_alive.return_value = False
        assert service.preflight_sync("aemo") == 0

    def test_returns_zero_when_no_new_urls(self, service, mock_container):
        """Should return 0 when Paperless has no more URLs than state."""
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
        }
        mock_container.state_tracker.return_value.get_processed_urls.return_value = [
            "https://example.com/a.pdf",
            "https://example.com/b.pdf",  # state has MORE than Paperless
        ]
        assert service.preflight_sync("aemo") == 0

    def test_adds_missing_urls_to_state(self, service, mock_container):
        """Should add URLs from Paperless that are missing from state."""
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
            "https://example.com/b.pdf": 2,
            "https://example.com/c.pdf": 3,
        }
        mock_container.state_tracker.return_value.get_processed_urls.return_value = [
            "https://example.com/a.pdf",
        ]

        result = service.preflight_sync("aemo")

        assert result == 2
        tracker = mock_container.state_tracker.return_value
        assert tracker.mark_processed.call_count == 2
        tracker.save.assert_called_once()

    def test_fast_path_skips_when_all_urls_in_state(self, service, mock_container):
        """Should skip when all Paperless URLs are already in state."""
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
        }
        mock_container.state_tracker.return_value.get_processed_urls.return_value = [
            "https://example.com/a.pdf",
        ]

        result = service.preflight_sync("aemo")
        assert result == 0
        # mark_processed should not be called
        mock_container.state_tracker.return_value.mark_processed.assert_not_called()


class TestRebuildState:
    """Test full state rebuild."""

    def test_rebuilds_state_from_paperless(self, service, mock_container):
        """Should add all Paperless URLs not in state."""
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
            "https://example.com/b.pdf": 2,
        }
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []

        result = service.rebuild_state("aemo")

        assert result == 2
        tracker = mock_container.state_tracker.return_value
        assert tracker.mark_processed.call_count == 2
        tracker.save.assert_called_once()

    def test_rebuild_no_duplicates(self, service, mock_container):
        """Should not add URLs already in state."""
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
        }
        mock_container.state_tracker.return_value.get_processed_urls.return_value = [
            "https://example.com/a.pdf",
        ]

        result = service.rebuild_state("aemo")

        assert result == 0
        mock_container.state_tracker.return_value.mark_processed.assert_not_called()

    def test_raises_when_paperless_not_configured(self, mock_container):
        """Should raise RuntimeError when Paperless is not configured."""
        mock_container.archive_backend.client.is_configured = False
        service = ReconciliationService(container=mock_container)

        with pytest.raises(RuntimeError, match="not configured"):
            service.rebuild_state("aemo")


class TestGetReport:
    """Test three-way reconciliation report."""

    def test_basic_report(self, service, mock_container):
        """Should generate correct report with all sources."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = [
            "https://example.com/a.pdf",
            "https://example.com/b.pdf",
        ]
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
            "https://example.com/c.pdf": 3,
        }

        with patch("app.config.Config.RAGFLOW_DATASET_ID", None):
            report = service.get_report("aemo")

        assert report.scraper_name == "aemo"
        assert report.state_url_count == 2
        assert report.paperless_url_count == 2
        assert "https://example.com/b.pdf" in report.urls_only_in_state
        assert "https://example.com/c.pdf" in report.urls_only_in_paperless

    def test_report_with_paperless_error(self, mock_container):
        """Should include error when Paperless is unavailable."""
        mock_container.archive_backend.client.is_configured = False
        service = ReconciliationService(container=mock_container)

        mock_container.state_tracker.return_value.get_processed_urls.return_value = []

        with patch("app.config.Config.RAGFLOW_DATASET_ID", None):
            report = service.get_report("aemo")

        assert len(report.errors) > 0
        assert "Paperless" in report.errors[0]

    def test_report_to_dict(self):
        """Should serialize to dict correctly."""
        report = ReconciliationReport(
            scraper_name="test",
            state_url_count=5,
            paperless_url_count=3,
            rag_document_count=2,
            urls_only_in_state=["a"],
            urls_only_in_paperless=["b"],
            urls_in_paperless_not_rag=["c"],
            urls_added_to_state=1,
            errors=["some error"],
        )
        d = report.to_dict()
        assert d["scraper_name"] == "test"
        assert d["state_url_count"] == 5
        assert d["errors"] == ["some error"]


class TestSyncRagGaps:
    """Test RAG gap sync."""

    def test_dry_run_returns_urls_only(self, service, mock_container):
        """Should return URLs without re-ingesting in dry run mode."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
        }

        with patch("app.services.reconciliation.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = "ds-1"
            result = service.sync_rag_gaps("aemo", dry_run=True)

        assert "https://example.com/a.pdf" in result
        # Parser and RAG should NOT be called in dry run
        mock_container.parser_backend.parse_document.assert_not_called()
        mock_container.rag_backend.ingest_document.assert_not_called()

    def test_returns_empty_when_no_gaps(self, service, mock_container):
        """Should return empty list when no gaps exist."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {}

        with patch("app.services.reconciliation.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = None
            result = service.sync_rag_gaps("aemo", dry_run=False)

        assert result == []

    def test_re_ingests_missing_documents(self, service, mock_container):
        """Should download, parse, and ingest missing documents."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/a.pdf": 1,
        }
        mock_container.archive_backend.client.download_document.return_value = b"%PDF test"

        # Mock RAGResult
        mock_rag_result = Mock()
        mock_rag_result.success = True
        mock_rag_result.document_id = "rag-1"
        mock_rag_result.error = None
        mock_container.rag_backend.ingest_document.return_value = mock_rag_result

        with patch("app.services.reconciliation.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = "ds-1"
            result = service.sync_rag_gaps("aemo", dry_run=False)

        assert "https://example.com/a.pdf" in result
        mock_container.parser_backend.parse_document.assert_called_once()
        mock_container.rag_backend.ingest_document.assert_called_once()

    def test_handles_download_failure(self, service, mock_container):
        """Should skip document if download fails."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/fail.pdf": 1,
        }
        mock_container.archive_backend.client.download_document.return_value = None

        with patch("app.services.reconciliation.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = "ds-1"
            result = service.sync_rag_gaps("aemo", dry_run=False)

        assert result == []

    def test_handles_parse_failure(self, service, mock_container):
        """Should skip document if parse fails."""
        mock_container.state_tracker.return_value.get_processed_urls.return_value = []
        mock_container.archive_backend.client.get_scraper_document_urls.return_value = {
            "https://example.com/bad.pdf": 1,
        }
        mock_container.archive_backend.client.download_document.return_value = b"%PDF test"

        mock_parse_result = Mock()
        mock_parse_result.success = False
        mock_parse_result.markdown_path = None
        mock_parse_result.error = "Parse error"
        mock_container.parser_backend.parse_document.return_value = mock_parse_result

        with patch("app.services.reconciliation.Config") as mock_config:
            mock_config.RAGFLOW_DATASET_ID = "ds-1"
            result = service.sync_rag_gaps("aemo", dry_run=False)

        assert result == []
