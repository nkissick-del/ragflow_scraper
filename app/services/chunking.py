"""
Text chunking strategies for RAG ingestion.

Splits documents into overlapping chunks suitable for embedding and retrieval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests

from app.utils import get_logger


@dataclass
class Chunk:
    """A single chunk of text with positional and contextual metadata."""

    content: str
    index: int
    metadata: dict = field(default_factory=dict)


class ChunkingStrategy(ABC):
    """Abstract base class for chunking strategies."""

    @abstractmethod
    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split text into chunks.

        Args:
            text: Full document text
            metadata: Optional document-level metadata to propagate

        Returns:
            List of Chunk objects
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        raise NotImplementedError


class FixedChunker(ChunkingStrategy):
    """Fixed-size word-boundary chunker with overlap.

    Splits text on word boundaries with configurable max tokens (words)
    and overlap. Detects Markdown headings (lines starting with #) and
    attaches them as heading_context in chunk metadata.
    """

    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 64):
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if overlap_tokens < 0:
            raise ValueError("overlap_tokens must be >= 0")
        if overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be < max_tokens")
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self.logger = get_logger("chunking.fixed")

    @property
    def name(self) -> str:
        return "fixed"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        if not text or not text.strip():
            return []

        base_metadata = dict(metadata or {})
        words = text.split()

        if not words:
            return []

        # Pre-compute heading context for each word position.
        # Walk through words and track the most recent heading line.
        heading_context = self._build_heading_map(text)

        chunks: list[Chunk] = []
        start = 0
        chunk_index = 0

        while start < len(words):
            end = min(start + self._max_tokens, len(words))
            chunk_words = words[start:end]
            content = " ".join(chunk_words)

            chunk_meta = dict(base_metadata)
            chunk_meta["chunk_index"] = chunk_index
            chunk_meta["word_start"] = start
            chunk_meta["word_end"] = end

            # Attach heading context from the start position
            if start in heading_context:
                chunk_meta["heading_context"] = heading_context[start]

            chunks.append(Chunk(content=content, index=chunk_index, metadata=chunk_meta))
            chunk_index += 1

            # Advance by (max_tokens - overlap_tokens)
            step = self._max_tokens - self._overlap_tokens
            start += step

            # If we've consumed all words, stop
            if end >= len(words):
                break

        return chunks

    def _build_heading_map(self, text: str) -> dict[int, str]:
        """Build a mapping from word index to the current heading context.

        Only records entries at positions where a heading starts, so lookup
        should find the most recent heading at or before a given word index.
        """
        heading_map: dict[int, str] = {}
        current_heading: Optional[str] = None
        word_pos = 0

        for line in text.split("\n"):
            stripped = line.strip()
            line_words = line.split()

            if stripped.startswith("#"):
                # Extract heading text (remove # prefix)
                current_heading = stripped.lstrip("#").strip()
                if current_heading and line_words:
                    heading_map[word_pos] = current_heading

            word_pos += len(line_words)

        # Propagate headings forward: for each chunk start position,
        # we want the most recent heading.
        if heading_map:
            sorted_positions = sorted(heading_map.keys())
            full_map: dict[int, str] = {}
            total_words = len(text.split())
            heading_idx = 0

            for pos in range(total_words):
                # Advance to the right heading
                while (
                    heading_idx < len(sorted_positions) - 1
                    and sorted_positions[heading_idx + 1] <= pos
                ):
                    heading_idx += 1

                if sorted_positions[heading_idx] <= pos:
                    full_map[pos] = heading_map[sorted_positions[heading_idx]]

            return full_map

        return heading_map


class HybridDoclingChunker(ChunkingStrategy):
    """Structure-aware chunker using docling-serve's HybridChunker endpoint.

    Sends markdown to docling-serve POST /v1/chunk/hybrid/file, which returns
    chunks that respect headings, tables, and document structure.
    Falls back to FixedChunker when docling-serve is unreachable.
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        docling_serve_url: str = "",
        docling_serve_timeout: int = 120,
    ):
        self._max_tokens = max_tokens
        self._docling_url = docling_serve_url.rstrip("/") if docling_serve_url else ""
        self._timeout = docling_serve_timeout
        self._fallback = FixedChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        self.logger = get_logger("chunking.hybrid")

    @property
    def name(self) -> str:
        return "hybrid"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        if not text or not text.strip():
            return []

        # Try docling-serve first
        if self._docling_url:
            try:
                return self._chunk_via_docling(text, metadata)
            except Exception as e:
                self.logger.warning(
                    f"docling-serve chunking failed, using fallback: {e}"
                )

        # Fallback to FixedChunker
        return self._fallback.chunk(text, metadata)

    def _chunk_via_docling(
        self, text: str, metadata: Optional[dict] = None
    ) -> list[Chunk]:
        """Send markdown to docling-serve and parse chunked response."""

        # Build a filename for the upload
        filename = (metadata or {}).get("filename", "document.md")
        if not filename.endswith(".md"):
            filename = (
                filename.rsplit(".", 1)[0] + ".md" if "." in filename else filename + ".md"
            )

        params = {
            "chunking_max_tokens": self._max_tokens,
            "chunking_include_raw_text": True,
        }

        response = requests.post(
            f"{self._docling_url}/v1/chunk/hybrid/file",
            files={"files": (filename, text.encode("utf-8"), "text/markdown")},
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()

        # Parse response into Chunk objects
        raw_chunks = data.get("chunks", [])
        if not raw_chunks:
            self.logger.warning("docling-serve returned 0 chunks, falling back")
            return self._fallback.chunk(text, metadata)

        base_metadata = dict(metadata or {})
        chunks: list[Chunk] = []
        output_index = 0
        for item in raw_chunks:
            content = item.get("text", item.get("raw_text", ""))
            if not content or not content.strip():
                continue

            chunk_index = item.get("chunk_index", output_index)
            chunk_meta = dict(base_metadata)
            chunk_meta["chunk_index"] = chunk_index
            chunk_meta["num_tokens"] = item.get("num_tokens", 0)
            chunk_meta["chunker"] = "docling_hybrid"

            headings = item.get("headings", [])
            if headings:
                chunk_meta["heading_context"] = headings[-1]
                chunk_meta["headings"] = headings

            chunks.append(
                Chunk(
                    content=content,
                    index=chunk_index,
                    metadata=chunk_meta,
                )
            )
            output_index += 1

        return chunks


def create_chunker(
    strategy: str = "hybrid",
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    docling_serve_url: str = "",
    docling_serve_timeout: int = 120,
) -> ChunkingStrategy:
    """Factory function to create a chunking strategy.

    Args:
        strategy: Strategy name ("fixed" or "hybrid")
        max_tokens: Maximum tokens (words) per chunk
        overlap_tokens: Number of overlapping tokens between chunks
        docling_serve_url: URL for docling-serve (hybrid strategy)
        docling_serve_timeout: Request timeout for docling-serve

    Returns:
        ChunkingStrategy instance

    Raises:
        ValueError: If strategy is unknown
    """
    if strategy == "fixed":
        return FixedChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    elif strategy == "hybrid":
        return HybridDoclingChunker(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            docling_serve_url=docling_serve_url,
            docling_serve_timeout=docling_serve_timeout,
        )
    else:
        raise ValueError(f"Unknown chunking strategy: {strategy}")
