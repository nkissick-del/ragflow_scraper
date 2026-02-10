"""Unit tests for Pipeline._run_llm_enrichment()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.orchestrator.pipeline import Pipeline


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.settings.get.return_value = ""
    return container


@pytest.fixture
def pipeline(mock_container):
    with patch("app.orchestrator.pipeline.Config") as mock_config:
        mock_config.RAGFLOW_DATASET_ID = "test-dataset"
        mock_config.LLM_ENRICHMENT_ENABLED = False
        mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
        mock_config.METADATA_MERGE_STRATEGY = "smart"
        p = Pipeline(
            scraper_name="test",
            upload_to_ragflow=False,
            upload_to_paperless=False,
            container=mock_container,
        )
    return p


class TestRunLLMEnrichment:
    def test_disabled_by_default(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.LLM_ENRICHMENT_ENABLED = False
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        # LLM client should not have been used
        mock_container.llm_client.is_configured.assert_not_called()
        assert parse_metadata == {}

    def test_enabled_via_config(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test\n\nContent", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = {
            "title": "LLM Title",
            "document_type": "report",
            "summary": "A summary",
            "keywords": ["k1", "k2"],
            "entities": ["Org1"],
            "key_topics": ["topic1"],
            "suggested_tags": ["tag1", "tag2"],
        }

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        # Title and document_type fill-gaps
        assert parse_metadata["title"] == "LLM Title"
        assert parse_metadata["document_type"] == "report"

        # Extra fields populated
        assert parse_metadata["extra"]["llm_summary"] == "A summary"
        assert parse_metadata["extra"]["llm_keywords"] == "k1, k2"
        assert parse_metadata["extra"]["llm_entities"] == "Org1"
        assert parse_metadata["extra"]["llm_topics"] == "topic1"

        # Tags merged
        assert "tag1" in parse_metadata["tags"]
        assert "tag2" in parse_metadata["tags"]

    def test_enabled_via_settings_override(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = {"title": "Override Title"}

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = False  # Config says disabled
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            # Settings override enables it
            mock_container.settings.get.return_value = "true"
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        assert parse_metadata["title"] == "Override Title"

    def test_settings_override_false(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.LLM_ENRICHMENT_ENABLED = True  # Config says enabled
            # Settings override disables it
            mock_container.settings.get.return_value = "false"
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        assert parse_metadata == {}

    def test_fill_gaps_does_not_overwrite(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {
            "title": "Existing Title",
            "document_type": "policy",
        }

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = {
            "title": "LLM Title",
            "document_type": "report",
        }

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        # Existing values should NOT be overwritten
        assert parse_metadata["title"] == "Existing Title"
        assert parse_metadata["document_type"] == "policy"

    def test_tags_deduplication(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {"tags": ["existing", "Policy"]}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = {
            "suggested_tags": ["policy", "new_tag"],
        }

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        # "policy" should not be added (case-insensitive dedup with "Policy")
        tags = parse_metadata["tags"]
        assert tags.count("existing") == 1
        assert "Policy" in tags
        assert "new_tag" in tags
        # "policy" should NOT be added since "Policy" already exists
        assert "policy" not in tags

    def test_non_fatal_on_exception(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService") as MockService:
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            MockService.side_effect = RuntimeError("LLM crash")
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        # Should not raise, metadata should be unchanged
        assert parse_metadata == {}

    def test_llm_not_configured(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = False
        mock_container.llm_client = mock_llm

        with patch("app.orchestrator.pipeline.Config") as mock_config:
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        assert parse_metadata == {}

    def test_enrichment_returns_none(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = None

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        assert parse_metadata == {}

    def test_list_values_converted_to_strings(self, pipeline, mock_container, tmp_path):
        md_path = tmp_path / "doc.md"
        md_path.write_text("# Test", encoding="utf-8")
        parse_metadata: dict = {}

        mock_llm = MagicMock()
        mock_llm.is_configured.return_value = True
        mock_container.llm_client = mock_llm

        mock_enrichment = MagicMock()
        mock_enrichment.enrich_metadata.return_value = {
            "keywords": ["alpha", "beta", "gamma"],
            "entities": ["Org A", "Person B"],
        }

        with patch("app.orchestrator.pipeline.Config") as mock_config, \
             patch("app.services.document_enrichment.DocumentEnrichmentService", return_value=mock_enrichment):
            mock_config.LLM_ENRICHMENT_ENABLED = True
            mock_config.LLM_ENRICHMENT_MAX_TOKENS = 8000
            mock_container.settings.get.return_value = ""
            pipeline._run_llm_enrichment(md_path, parse_metadata)

        assert parse_metadata["extra"]["llm_keywords"] == "alpha, beta, gamma"
        assert parse_metadata["extra"]["llm_entities"] == "Org A, Person B"
