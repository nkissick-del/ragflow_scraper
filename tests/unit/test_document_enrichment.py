"""Unit tests for DocumentEnrichmentService."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


from app.services.document_enrichment import DocumentEnrichmentService
from app.services.llm_client import LLMResult


class TestEnrichMetadata:
    """Tier 1: Document-level metadata extraction."""

    def _make_service(self, llm_response=None, side_effect=None):
        mock_llm = MagicMock()
        if side_effect:
            mock_llm.chat.side_effect = side_effect
        elif llm_response is not None:
            mock_llm.chat.return_value = llm_response
        return DocumentEnrichmentService(mock_llm, max_tokens=8000), mock_llm

    def test_enrich_metadata_success(self, tmp_path):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test Document\n\nSome content here.", encoding="utf-8")

        enriched_data = {
            "title": "Test Document",
            "summary": "A test document about content.",
            "keywords": ["test", "document"],
            "entities": ["TestOrg"],
            "suggested_tags": ["testing"],
            "document_type": "report",
            "key_topics": ["testing"],
        }
        llm_result = LLMResult(
            content=json.dumps(enriched_data),
            model="llama3.1:8b",
            finish_reason="stop",
        )
        service, mock_llm = self._make_service(llm_response=llm_result)

        result = service.enrich_metadata(md_file)

        assert result is not None
        assert result["title"] == "Test Document"
        assert result["document_type"] == "report"
        assert result["keywords"] == ["test", "document"]
        mock_llm.chat.assert_called_once()

    def test_enrich_metadata_empty_document(self, tmp_path):
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        service, mock_llm = self._make_service()
        result = service.enrich_metadata(md_file)

        assert result is None
        mock_llm.chat.assert_not_called()

    def test_enrich_metadata_whitespace_only(self, tmp_path):
        md_file = tmp_path / "ws.md"
        md_file.write_text("   \n\n  ", encoding="utf-8")

        service, mock_llm = self._make_service()
        result = service.enrich_metadata(md_file)

        assert result is None

    def test_enrich_metadata_invalid_json(self, tmp_path):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\n\nContent", encoding="utf-8")

        llm_result = LLMResult(
            content="This is not valid JSON",
            model="llama3.1:8b",
            finish_reason="stop",
        )
        service, _ = self._make_service(llm_response=llm_result)

        result = service.enrich_metadata(md_file)
        assert result is None

    def test_enrich_metadata_non_dict_json(self, tmp_path):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\n\nContent", encoding="utf-8")

        llm_result = LLMResult(
            content='["a", "b"]',
            model="llama3.1:8b",
            finish_reason="stop",
        )
        service, _ = self._make_service(llm_response=llm_result)

        result = service.enrich_metadata(md_file)
        assert result is None

    def test_enrich_metadata_llm_failure(self, tmp_path):
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\n\nContent", encoding="utf-8")

        service, _ = self._make_service(side_effect=ConnectionError("timeout"))

        result = service.enrich_metadata(md_file)
        assert result is None

    def test_enrich_metadata_truncation(self, tmp_path):
        md_file = tmp_path / "big.md"
        # Write a document larger than max_tokens * 4
        big_content = "x" * 50000
        md_file.write_text(big_content, encoding="utf-8")

        llm_result = LLMResult(
            content='{"title": "Big Doc"}',
            model="llama3.1:8b",
            finish_reason="stop",
        )
        service, mock_llm = self._make_service(llm_response=llm_result)
        # Set small max_tokens to trigger truncation
        service._max_tokens = 1000

        result = service.enrich_metadata(md_file)
        assert result is not None

        # Verify the text sent to LLM was truncated
        call_args = mock_llm.chat.call_args
        user_message = call_args[0][0][1]["content"]
        assert len(user_message) == 4000  # 1000 * 4

    def test_enrich_metadata_file_not_found(self):
        service, _ = self._make_service()
        result = service.enrich_metadata(Path("/nonexistent/file.md"))
        assert result is None


class TestEnrichChunks:
    """Tier 2: Chunk-level contextual enrichment."""

    def _make_chunk(self, content, index=0, metadata=None):
        from app.services.chunking import Chunk
        return Chunk(content=content, index=index, metadata=metadata or {})

    def _make_service(self, llm_responses=None, side_effect=None):
        mock_llm = MagicMock()
        if side_effect:
            mock_llm.chat.side_effect = side_effect
        elif llm_responses is not None:
            mock_llm.chat.side_effect = llm_responses
        return DocumentEnrichmentService(mock_llm, max_tokens=8000), mock_llm

    def test_enrich_chunks_success(self):
        chunks = [
            self._make_chunk("Chunk 0 content", 0),
            self._make_chunk("Chunk 1 content", 1),
        ]
        llm_responses = [
            LLMResult(content="This chunk is from the introduction.", model="m", finish_reason="stop"),
            LLMResult(content="This chunk covers the methodology.", model="m", finish_reason="stop"),
        ]
        service, _ = self._make_service(llm_responses=llm_responses)

        result = service.enrich_chunks(chunks, "# Doc\n\nChunk 0 content\n\nChunk 1 content")

        assert len(result) == 2
        assert result[0].startswith("This chunk is from the introduction.")
        assert "Chunk 0 content" in result[0]
        assert result[1].startswith("This chunk covers the methodology.")

    def test_enrich_chunks_empty_list(self):
        service, _ = self._make_service()
        result = service.enrich_chunks([], "some text")
        assert result == []

    def test_enrich_chunks_per_chunk_fallback(self):
        chunks = [
            self._make_chunk("Chunk 0", 0),
            self._make_chunk("Chunk 1", 1),
        ]
        # First call succeeds, second fails
        llm_responses = [
            LLMResult(content="Context for chunk 0.", model="m", finish_reason="stop"),
            ConnectionError("timeout"),
        ]
        service, _ = self._make_service(llm_responses=llm_responses)

        result = service.enrich_chunks(chunks, "doc text")

        assert len(result) == 2
        assert "Context for chunk 0." in result[0]
        assert result[1] == "Chunk 1"  # Fell back to raw content

    def test_enrich_chunks_total_failure(self):
        chunks = [
            self._make_chunk("Chunk 0", 0),
            self._make_chunk("Chunk 1", 1),
        ]
        service, mock_llm = self._make_service()
        # Make the outline extraction raise
        service._extract_outline = MagicMock(side_effect=RuntimeError("boom"))

        result = service.enrich_chunks(chunks, "doc text")

        assert result == ["Chunk 0", "Chunk 1"]

    def test_enrich_chunks_short_doc_uses_full_text(self):
        chunks = [self._make_chunk("Content", 0)]
        llm_responses = [
            LLMResult(content="Context.", model="m", finish_reason="stop"),
        ]
        service, mock_llm = self._make_service(llm_responses=llm_responses)
        service._max_tokens = 10000  # Large enough that "short text" < limit

        service.enrich_chunks(chunks, "short text")

        call_args = mock_llm.chat.call_args[0][0]
        user_msg = call_args[1]["content"]
        assert "Full document:" in user_msg

    def test_enrich_chunks_long_doc_uses_outline(self):
        chunks = [self._make_chunk("Content", 0)]
        llm_responses = [
            LLMResult(content="Context.", model="m", finish_reason="stop"),
        ]
        service, mock_llm = self._make_service(llm_responses=llm_responses)
        service._max_tokens = 1  # Very small so doc is "long"

        long_text = "# Heading\n\n" + "x" * 10000
        service.enrich_chunks(chunks, long_text)

        call_args = mock_llm.chat.call_args[0][0]
        user_msg = call_args[1]["content"]
        assert "Document outline:" in user_msg


class TestExtractOutline:
    def test_extracts_headings(self):
        service = DocumentEnrichmentService(MagicMock())
        text = "# Title\n\nParagraph\n\n## Section 1\n\nMore text\n\n### Sub\n"
        outline = service._extract_outline(text)
        assert "# Title" in outline
        assert "## Section 1" in outline
        assert "### Sub" in outline
        assert "Paragraph" not in outline

    def test_limits_to_50_headings(self):
        service = DocumentEnrichmentService(MagicMock())
        text = "\n".join([f"# Heading {i}" for i in range(100)])
        outline = service._extract_outline(text)
        assert outline.count("# Heading") == 50
