"""Stack tests for LLM enrichment against real Ollama on Unraid.

Tests Tier 1 (document-level metadata) and Tier 2 (chunk-level context)
against the live Ollama instance with llama3.1:8b.
"""

import json

from app.services.llm_client import OllamaLLMClient, create_llm_client
from app.services.document_enrichment import DocumentEnrichmentService
from app.services.chunking import Chunk


# ---------------------------------------------------------------------------
# Tier 0: LLM Client connectivity
# ---------------------------------------------------------------------------


class TestLLMClientStack:
    """Test LLM client against real Ollama."""

    def test_connection(self, ollama_url, ollama_alive):
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b")
        assert client.test_connection() is True

    def test_chat_simple(self, ollama_url, ollama_alive):
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b")
        messages = [
            {"role": "user", "content": "Reply with exactly: hello"},
        ]
        result = client.chat(messages)
        assert result.content  # non-empty
        assert result.model  # model name returned
        assert result.finish_reason  # finish reason populated

    def test_chat_json_format(self, ollama_url, ollama_alive):
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b")
        messages = [
            {"role": "system", "content": "Reply with valid JSON only."},
            {"role": "user", "content": 'Return: {"status": "ok"}'},
        ]
        result = client.chat(messages, response_format="json")
        parsed = json.loads(result.content)
        assert isinstance(parsed, dict)

    def test_factory_creates_ollama(self, ollama_url, ollama_alive):
        client = create_llm_client(
            backend="ollama",
            model="llama3.1:8b",
            url=ollama_url,
        )
        assert client.is_configured()
        assert client.test_connection()


# ---------------------------------------------------------------------------
# Tier 1: Document-level metadata extraction
# ---------------------------------------------------------------------------


class TestTier1EnrichmentStack:
    """Test Tier 1 document-level metadata extraction via real LLM."""

    def test_enrich_metadata_real_document(self, ollama_url, ollama_alive, tmp_path):
        """Full Tier 1 pipeline: markdown → LLM → structured JSON metadata."""
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b", timeout=120)
        service = DocumentEnrichmentService(client, max_tokens=8000)

        md_file = tmp_path / "test_policy.md"
        md_file.write_text(
            "# National Electricity Market Reform\n\n"
            "## Executive Summary\n\n"
            "The Australian Energy Market Commission (AEMC) has released its "
            "2024 review of the National Electricity Rules. The report examines "
            "the transition to renewable energy sources, the integration of "
            "distributed energy resources, and the impact on wholesale electricity "
            "prices.\n\n"
            "## Key Findings\n\n"
            "1. Renewable energy capacity has increased by 35% since 2020\n"
            "2. Battery storage deployment exceeded forecasts\n"
            "3. Grid reliability maintained despite coal plant closures\n\n"
            "## Recommendations\n\n"
            "The AEMC recommends updating market mechanisms to better reflect "
            "the changing generation mix, including capacity market reforms and "
            "enhanced demand response incentives.\n",
            encoding="utf-8",
        )

        result = service.enrich_metadata(md_file)

        # Should return a dict with structured metadata
        assert result is not None, "LLM returned None — check Ollama connectivity"
        assert isinstance(result, dict)

        # Check expected keys are present (LLM may include extra)
        print(f"\nTier 1 result keys: {list(result.keys())}")
        print(f"Tier 1 result: {json.dumps(result, indent=2, default=str)}")

        # At minimum we expect title and some keywords
        assert "title" in result or "summary" in result, (
            f"LLM response missing expected keys. Got: {list(result.keys())}"
        )

    def test_enrich_metadata_empty_document(self, ollama_url, ollama_alive, tmp_path):
        """Empty document should return None gracefully."""
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b")
        service = DocumentEnrichmentService(client)

        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        result = service.enrich_metadata(md_file)
        assert result is None


# ---------------------------------------------------------------------------
# Tier 2: Chunk-level contextual enrichment
# ---------------------------------------------------------------------------


class TestTier2EnrichmentStack:
    """Test Tier 2 chunk-level contextual descriptions via real LLM."""

    def test_enrich_chunks_short_doc(self, ollama_url, ollama_alive):
        """Short document: full text passed as context."""
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b", timeout=120)
        service = DocumentEnrichmentService(client, max_tokens=8000)

        full_text = (
            "# Energy Market Report\n\n"
            "## Section 1: Solar Capacity\n\n"
            "Australia's solar capacity reached 30 GW in 2024.\n\n"
            "## Section 2: Wind Capacity\n\n"
            "Wind capacity reached 12 GW with new projects in South Australia.\n"
        )

        chunks = [
            Chunk(content="Australia's solar capacity reached 30 GW in 2024.", index=0),
            Chunk(content="Wind capacity reached 12 GW with new projects in South Australia.", index=1),
        ]

        result = service.enrich_chunks(chunks, full_text, window=3)

        assert len(result) == 2

        # Each enriched text should contain the original content
        assert "30 GW" in result[0]
        assert "12 GW" in result[1]

        # Each should have a situating description prepended (longer than raw)
        assert len(result[0]) > len(chunks[0].content)
        assert len(result[1]) > len(chunks[1].content)

        print(f"\nChunk 0 enriched ({len(result[0])} chars):\n{result[0][:200]}...")
        print(f"\nChunk 1 enriched ({len(result[1])} chars):\n{result[1][:200]}...")

    def test_enrich_chunks_empty_list(self, ollama_url, ollama_alive):
        """Empty chunk list should return empty list."""
        client = OllamaLLMClient(url=ollama_url, model="llama3.1:8b")
        service = DocumentEnrichmentService(client)

        result = service.enrich_chunks([], "Some text", window=3)
        assert result == []


# ---------------------------------------------------------------------------
# End-to-end: pgvector adapter with enrichment
# ---------------------------------------------------------------------------


class TestPgVectorEnrichmentStack:
    """Test that pgvector adapter enrichment works with real services."""

    def test_contextual_enrichment_method(self, ollama_url, ollama_alive):
        """Test _apply_contextual_enrichment() with real LLM."""
        from unittest.mock import MagicMock, patch
        from app.config import Config
        from app.backends.rag.vector_adapter import VectorRAGBackend

        # Create backend with mocked vector store/embedding (we only test enrichment)
        mock_store = MagicMock()
        mock_store.name = "pgvector"
        with patch("app.backends.rag.vector_adapter.get_logger"), \
             patch("app.services.chunking.get_logger"):
            backend = VectorRAGBackend(
                vector_store=mock_store,
                embedding_client=MagicMock(),
            )

        chunks = [
            Chunk(content="The AEMC regulates the National Electricity Market.", index=0),
            Chunk(content="Wholesale prices decreased 15% due to renewable growth.", index=1),
        ]
        full_text = (
            "# AEMC Market Report\n\n"
            "The AEMC regulates the National Electricity Market.\n\n"
            "Wholesale prices decreased 15% due to renewable growth.\n"
        )

        # Create a mock container with a real LLM client
        from app.services.llm_client import OllamaLLMClient
        real_llm = OllamaLLMClient(url=ollama_url, model="llama3.1:8b", timeout=120)

        mock_container = MagicMock()
        mock_container.llm_client = real_llm
        mock_container.settings.get.return_value = ""

        with patch.object(Config, "CONTEXTUAL_ENRICHMENT_ENABLED", True), \
             patch.object(Config, "CONTEXTUAL_ENRICHMENT_WINDOW", 3), \
             patch.object(Config, "LLM_ENRICHMENT_MAX_TOKENS", 8000), \
             patch("app.container.get_container", return_value=mock_container):
            result = backend._apply_contextual_enrichment(chunks, full_text)

        assert len(result) == 2
        # Enriched texts should be longer (context prepended)
        assert len(result[0]) > len(chunks[0].content)
        assert len(result[1]) > len(chunks[1].content)
        # Original content preserved
        assert "AEMC" in result[0]
        assert "15%" in result[1]

        print(f"\nEnriched chunk 0:\n{result[0][:300]}")
        print(f"\nEnriched chunk 1:\n{result[1][:300]}")
