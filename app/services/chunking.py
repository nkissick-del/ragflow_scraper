"""
Text chunking strategies for RAG ingestion.

Splits documents into overlapping chunks suitable for embedding and retrieval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

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
    """Wrapper around Docling's HybridChunker.

    Falls back to FixedChunker if docling is not available.
    Note: This requires a DoclingDocument object which means re-parsing
    markdown. Start with FixedChunker; evaluate this later.
    """

    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 64):
        self._max_tokens = max_tokens
        self._fallback = FixedChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        self.logger = get_logger("chunking.hybrid")

    @property
    def name(self) -> str:
        return "hybrid"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        # For now, always use the fallback FixedChunker.
        # Docling's HybridChunker needs a DoclingDocument, not raw text.
        self.logger.debug("Using FixedChunker fallback (HybridChunker needs DoclingDocument)")
        return self._fallback.chunk(text, metadata)


def create_chunker(
    strategy: str = "fixed",
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> ChunkingStrategy:
    """Factory function to create a chunking strategy.

    Args:
        strategy: Strategy name ("fixed" or "hybrid")
        max_tokens: Maximum tokens (words) per chunk
        overlap_tokens: Number of overlapping tokens between chunks

    Returns:
        ChunkingStrategy instance

    Raises:
        ValueError: If strategy is unknown
    """
    if strategy == "fixed":
        return FixedChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    elif strategy == "hybrid":
        return HybridDoclingChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    else:
        raise ValueError(f"Unknown chunking strategy: {strategy}")
