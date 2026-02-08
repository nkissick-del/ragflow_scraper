"""Tests for Tika enrichment logic in Pipeline._run_tika_enrichment()."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTikaEnrichment:
    """Tests for Pipeline._run_tika_enrichment() helper method."""

    def _make_pipeline(self, settings_override=""):
        """Create a minimal Pipeline with mocked dependencies."""
        mock_container = MagicMock()
        mock_container.settings.get.return_value = settings_override
        mock_container.ragflow_client = MagicMock()

        with patch("app.orchestrator.pipeline.ScraperRegistry"):
            from app.orchestrator.pipeline import Pipeline
            pipeline = Pipeline(
                scraper_name="test",
                upload_to_ragflow=False,
                upload_to_paperless=False,
                container=mock_container,
            )
        return pipeline

    def test_enrichment_fills_missing_keys(self):
        """Tika metadata keys not in parse_metadata get added."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Existing Title"}
        tika_response = {"author": "John Doe", "page_count": 5}
        pipeline.container.tika_client.extract_metadata.return_value = tika_response

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        assert parse_metadata == {
            "title": "Existing Title",
            "author": "John Doe",
            "page_count": 5,
        }
        pipeline.container.tika_client.extract_metadata.assert_called_once()

    def test_enrichment_does_not_overwrite_existing(self):
        """Tika metadata doesn't replace existing parse_metadata keys."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Parser Title", "author": "Parser Author"}
        tika_response = {"title": "Tika Title", "author": "Tika Author", "page_count": 10}
        pipeline.container.tika_client.extract_metadata.return_value = tika_response

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        assert parse_metadata["title"] == "Parser Title"
        assert parse_metadata["author"] == "Parser Author"
        assert parse_metadata["page_count"] == 10

    def test_enrichment_skipped_when_disabled(self):
        """TIKA_ENRICHMENT_ENABLED=False -> extract_metadata never called."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Test"}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = False
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        pipeline.container.tika_client.extract_metadata.assert_not_called()
        assert parse_metadata == {"title": "Test"}

    def test_enrichment_skipped_when_no_url(self):
        """TIKA_SERVER_URL="" -> extract_metadata never called."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Test"}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = ""
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        pipeline.container.tika_client.extract_metadata.assert_not_called()

    def test_enrichment_skipped_for_office_docs(self):
        """doc_type='office' -> extract_metadata never called."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Test"}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.docx"), parse_metadata, "office"
            )

        pipeline.container.tika_client.extract_metadata.assert_not_called()

    def test_enrichment_failure_is_nonfatal(self):
        """extract_metadata raises -> pipeline continues, metadata unchanged."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Original"}
        pipeline.container.tika_client.extract_metadata.side_effect = ConnectionError(
            "Tika unreachable"
        )

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            # Should NOT raise
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        assert parse_metadata == {"title": "Original"}

    def test_enrichment_with_empty_tika_response(self):
        """Tika returns {} -> parse_metadata unchanged."""
        pipeline = self._make_pipeline()
        parse_metadata = {"title": "Existing"}
        pipeline.container.tika_client.extract_metadata.return_value = {}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        assert parse_metadata == {"title": "Existing"}
        pipeline.container.tika_client.extract_metadata.assert_called_once()

    def test_enrichment_respects_settings_override(self):
        """Settings toggle overrides Config.TIKA_ENRICHMENT_ENABLED."""
        # Config says disabled, but settings override says "true"
        pipeline = self._make_pipeline(settings_override="true")
        parse_metadata = {}
        tika_response = {"author": "Tika Author"}
        pipeline.container.tika_client.extract_metadata.return_value = tika_response

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = False  # Disabled in env
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        # Should still enrich because settings override is "true"
        assert parse_metadata == {"author": "Tika Author"}
        pipeline.container.tika_client.extract_metadata.assert_called_once()

    def test_enrichment_settings_override_disables(self):
        """Settings override 'false' disables enrichment even if Config enables it."""
        pipeline = self._make_pipeline(settings_override="false")
        parse_metadata = {"title": "Test"}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.TIKA_ENRICHMENT_ENABLED = True  # Enabled in env
            mock_config.TIKA_SERVER_URL = "http://tika:9998"
            pipeline._run_tika_enrichment(
                Path("/tmp/test.pdf"), parse_metadata, "pdf"
            )

        pipeline.container.tika_client.extract_metadata.assert_not_called()
