"""
Document enrichment via LLM.

Tier 1: Document-level metadata extraction (title, summary, keywords, etc.)
Tier 2: Chunk-level contextual descriptions for improved retrieval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.services.llm_client import LLMClient
    from app.services.chunking import Chunk

# Tier 1 system prompt — requests structured JSON metadata
_TIER1_SYSTEM_PROMPT = """\
You are a document analysis assistant. Given the full text of a document, \
extract structured metadata as JSON with these exact keys:

- "title": The document's title (string)
- "summary": A 2-3 sentence summary (string)
- "keywords": 5-10 relevant keywords (list of strings)
- "entities": Named entities — organizations, people, locations (list of strings)
- "suggested_tags": 3-7 category tags for filing (list of strings)
- "document_type": One of: report, policy, guideline, regulation, legislation, \
standard, manual, briefing, correspondence, media_release, submission, other (string)
- "key_topics": 3-5 main topics discussed (list of strings)

Respond with ONLY valid JSON, no markdown formatting or explanation."""

# Tier 2 system prompt — requests plain-text contextual description
_TIER2_SYSTEM_PROMPT = """\
You are a document analysis assistant. Given a chunk of text from a larger document, \
along with context about the document's structure and surrounding content, write a \
short 2-3 sentence paragraph that situates this chunk within the document.

Explain what section this chunk belongs to, what the document is about, and how this \
chunk relates to the broader content. This description will be prepended to the chunk \
to improve search retrieval.

Respond with ONLY the situating paragraph in plain text, no markdown formatting."""


class DocumentEnrichmentService:
    """Service for enriching documents and chunks with LLM-generated metadata."""

    def __init__(self, llm_client: "LLMClient", max_tokens: int = 8000):
        from app.utils import get_logger

        self._llm = llm_client
        self._max_tokens = max_tokens
        self.logger = get_logger("services.document_enrichment")

    def enrich_metadata(self, content_path: Path) -> Optional[dict]:
        """Extract structured metadata from a document.

        Reads the document, truncates if needed, and asks the LLM
        for structured JSON metadata (Tier 1).

        Args:
            content_path: Path to the content file (HTML, Markdown, etc.)

        Returns:
            Dict with extracted metadata, or None on any failure
        """
        try:
            text = content_path.read_text(encoding="utf-8")
            if not text.strip():
                self.logger.warning(f"Empty document, skipping enrichment: {content_path.name}")
                return None

            # Truncate to approximate token limit (~4 chars/token)
            char_limit = self._max_tokens * 4
            if len(text) > char_limit:
                text = text[:char_limit]
                self.logger.debug(
                    f"Truncated document to {char_limit} chars for enrichment"
                )

            messages = [
                {"role": "system", "content": _TIER1_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]

            result = self._llm.chat(messages, response_format="json")

            # Parse JSON response
            parsed = json.loads(result.content)
            if not isinstance(parsed, dict):
                self.logger.warning("LLM returned non-dict JSON, skipping enrichment")
                return None

            self.logger.debug(f"LLM enrichment extracted {len(parsed)} fields")
            return parsed

        except json.JSONDecodeError as e:
            self.logger.warning(f"LLM returned invalid JSON: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"LLM enrichment failed (non-fatal): {e}")
            return None

    # ---- Tier 2: Chunk-level contextual enrichment ----

    def _extract_outline(self, text: str) -> str:
        """Extract markdown headings as a document outline."""
        lines = text.split("\n")
        headings = [line for line in lines if line.startswith("#")]
        return "\n".join(headings[:50])

    def _build_chunk_context(
        self,
        chunk_idx: int,
        chunk_content: str,
        all_chunks: list["Chunk"],
        outline: str,
        window: int,
    ) -> str:
        """Build context string for a single chunk."""
        parts = [f"Document outline:\n{outline}\n"]

        # Add surrounding chunks (truncated)
        start = max(0, chunk_idx - window)
        end = min(len(all_chunks), chunk_idx + window + 1)

        for i in range(start, end):
            if i == chunk_idx:
                continue
            neighbor = all_chunks[i].content[:200]
            label = "preceding" if i < chunk_idx else "following"
            parts.append(f"[{label} chunk {i}]: {neighbor}")

        parts.append(f"\nCurrent chunk ({chunk_idx}):\n{chunk_content}")
        return "\n\n".join(parts)

    def enrich_chunks(
        self,
        chunks: list["Chunk"],
        full_text: str,
        window: int = 3,
    ) -> list[str]:
        """Add contextual descriptions to chunks for improved retrieval.

        For short documents (under max_tokens), passes full text as context.
        For long documents, passes outline + surrounding chunks.

        Args:
            chunks: List of Chunk objects
            full_text: Full document text
            window: Number of surrounding chunks to include as context

        Returns:
            List of enriched text strings (description prepended to chunk content)
        """
        if not chunks:
            return []

        try:
            outline = self._extract_outline(full_text)
            char_limit = self._max_tokens * 4
            is_short = len(full_text) <= char_limit

            enriched: list[str] = []
            for i, chunk in enumerate(chunks):
                try:
                    if is_short:
                        # Leave room for chunk content and system prompt overhead
                        max_doc_chars = char_limit - len(chunk.content) - 500
                        doc_text = full_text[:max_doc_chars] if len(full_text) > max_doc_chars else full_text
                        context = f"Full document:\n{doc_text}\n\nCurrent chunk ({i}):\n{chunk.content}"
                    else:
                        context = self._build_chunk_context(
                            i, chunk.content, chunks, outline, window
                        )

                    messages = [
                        {"role": "system", "content": _TIER2_SYSTEM_PROMPT},
                        {"role": "user", "content": context},
                    ]

                    result = self._llm.chat(messages)
                    situating_text = result.content.strip()
                    enriched.append(f"{situating_text}\n\n{chunk.content}")
                except Exception as e:
                    self.logger.warning(
                        f"Chunk {i} enrichment failed, using raw content: {e}"
                    )
                    enriched.append(chunk.content)

            return enriched

        except Exception as e:
            self.logger.warning(
                f"Chunk enrichment failed entirely, using raw content: {e}"
            )
            return [c.content for c in chunks]
