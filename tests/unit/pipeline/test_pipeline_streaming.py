"""Tests for Pipeline streaming (generator-based) document processing."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.orchestrator.pipeline import Pipeline
from app.scrapers.models import ScraperResult


def _make_generator(docs, scraper_result):
    """Create a generator that yields docs and returns scraper_result."""
    for doc in docs:
        yield doc
    return scraper_result


@pytest.fixture
def mock_container():
    """Create a mock container with all required attributes."""
    c = MagicMock()
    c.ragflow_client = MagicMock()
    c.settings.get.return_value = ""
    c.parser_backend = MagicMock()
    c.archive_backend = MagicMock()
    c.tika_client = MagicMock()
    c.gotenberg_client = MagicMock()
    return c


@pytest.fixture
def pipeline(mock_container):
    """Create a pipeline with mocked dependencies."""
    with patch("app.orchestrator.pipeline.get_container", return_value=mock_container):
        p = Pipeline(
            scraper_name="test",
            upload_to_ragflow=False,
            upload_to_paperless=False,
            container=mock_container,
        )
    return p


class TestPipelineStreaming:
    def test_consumes_generator(self, pipeline, tmp_path):
        """Pipeline processes docs as they are yielded from generator."""
        doc_file = tmp_path / "test.pdf"
        doc_file.write_text("dummy pdf")

        doc = {
            "title": "Test Doc",
            "url": "http://example.com/test.pdf",
            "filename": "test.pdf",
            "local_path": str(doc_file),
            "tags": [],
            "extra": {},
        }
        scraper_result = ScraperResult(
            status="completed",
            scraper="test",
            scraped_count=1,
            downloaded_count=1,
        )
        gen = _make_generator([doc], scraper_result)

        with patch.object(pipeline, "_create_scraper_generator", return_value=gen), \
             patch.object(pipeline, "_process_document") as mock_process:
            mock_process.return_value = {
                "parsed": True,
                "archived": False,
                "verified": False,
                "rag_indexed": False,
                "error": None,
            }
            result = pipeline.run()

        assert result.downloaded_count == 1
        assert result.parsed_count == 1
        mock_process.assert_called_once()

    def test_empty_generator(self, pipeline):
        """Pipeline handles generator that yields nothing."""
        scraper_result = ScraperResult(
            status="completed",
            scraper="test",
            scraped_count=0,
            downloaded_count=0,
        )
        gen = _make_generator([], scraper_result)

        with patch.object(pipeline, "_create_scraper_generator", return_value=gen):
            result = pipeline.run()

        assert result.status == "completed"
        assert result.downloaded_count == 0

    def test_scraper_failure(self, pipeline):
        """Pipeline handles failed scraper result."""
        scraper_result = ScraperResult(
            status="failed",
            scraper="test",
            errors=["Connection failed"],
        )
        gen = _make_generator([], scraper_result)

        with patch.object(pipeline, "_create_scraper_generator", return_value=gen):
            result = pipeline.run()

        assert result.status == "failed"
        assert any("Scraper failed" in e for e in result.errors)

    def test_document_processing_error(self, pipeline, tmp_path):
        """Pipeline continues after document processing error."""
        doc_file = tmp_path / "good.pdf"
        doc_file.write_text("pdf")

        docs = [
            {
                "title": "Bad Doc",
                "url": "http://example.com/bad.pdf",
                "filename": "bad.pdf",
                "local_path": "/nonexistent/bad.pdf",
                "tags": [],
                "extra": {},
            },
            {
                "title": "Good Doc",
                "url": "http://example.com/good.pdf",
                "filename": "good.pdf",
                "local_path": str(doc_file),
                "tags": [],
                "extra": {},
            },
        ]
        scraper_result = ScraperResult(
            status="completed",
            scraper="test",
            scraped_count=2,
            downloaded_count=2,
        )
        gen = _make_generator(docs, scraper_result)

        with patch.object(pipeline, "_create_scraper_generator", return_value=gen), \
             patch.object(pipeline, "_process_document") as mock_process:
            mock_process.return_value = {
                "parsed": True,
                "archived": False,
                "verified": False,
                "rag_indexed": False,
                "error": None,
            }
            result = pipeline.run()

        # Both docs downloaded, but bad.pdf fails (file not found)
        assert result.downloaded_count == 2
        assert result.failed_count == 1
        assert result.parsed_count == 1

    def test_scraper_result_stats_merged(self, pipeline):
        """Pipeline merges scraper stats (scraped_count, errors)."""
        scraper_result = ScraperResult(
            status="completed",
            scraper="test",
            scraped_count=10,
            downloaded_count=0,
            skipped_count=10,
            errors=["Page 5: timeout"],
        )
        gen = _make_generator([], scraper_result)

        with patch.object(pipeline, "_create_scraper_generator", return_value=gen):
            result = pipeline.run()

        assert result.scraped_count == 10
        assert "Page 5: timeout" in result.errors
