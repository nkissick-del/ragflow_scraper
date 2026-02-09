"""Tests for chunking strategies."""

import pytest

from app.services.chunking import (
    Chunk,
    FixedChunker,
    HybridDoclingChunker,
    create_chunker,
)


class TestChunk:
    """Test Chunk dataclass."""

    def test_basic_creation(self):
        chunk = Chunk(content="hello world", index=0)
        assert chunk.content == "hello world"
        assert chunk.index == 0
        assert chunk.metadata == {}

    def test_with_metadata(self):
        chunk = Chunk(content="test", index=1, metadata={"source": "test"})
        assert chunk.metadata["source"] == "test"


class TestFixedChunker:
    """Test FixedChunker."""

    def test_name(self):
        chunker = FixedChunker()
        assert chunker.name == "fixed"

    def test_invalid_max_tokens(self):
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            FixedChunker(max_tokens=0)

    def test_invalid_overlap_negative(self):
        with pytest.raises(ValueError, match="overlap_tokens must be >= 0"):
            FixedChunker(overlap_tokens=-1)

    def test_invalid_overlap_exceeds_max(self):
        with pytest.raises(ValueError, match="overlap_tokens must be < max_tokens"):
            FixedChunker(max_tokens=10, overlap_tokens=10)

    def test_empty_text(self):
        chunker = FixedChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_short_text_single_chunk(self):
        chunker = FixedChunker(max_tokens=100)
        chunks = chunker.chunk("hello world this is a test")
        assert len(chunks) == 1
        assert chunks[0].content == "hello world this is a test"
        assert chunks[0].index == 0

    def test_exact_max_tokens(self):
        chunker = FixedChunker(max_tokens=5, overlap_tokens=0)
        text = "one two three four five"
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == "one two three four five"

    def test_chunking_with_overlap(self):
        chunker = FixedChunker(max_tokens=4, overlap_tokens=2)
        text = "word1 word2 word3 word4 word5 word6 word7 word8"
        chunks = chunker.chunk(text)

        # With max=4, overlap=2, step=2:
        # chunk 0: word1 word2 word3 word4
        # chunk 1: word3 word4 word5 word6
        # chunk 2: word5 word6 word7 word8
        assert len(chunks) == 3
        assert chunks[0].content == "word1 word2 word3 word4"
        assert chunks[1].content == "word3 word4 word5 word6"
        assert chunks[2].content == "word5 word6 word7 word8"

    def test_chunking_no_overlap(self):
        chunker = FixedChunker(max_tokens=3, overlap_tokens=0)
        text = "a b c d e f"
        chunks = chunker.chunk(text)
        assert len(chunks) == 2
        assert chunks[0].content == "a b c"
        assert chunks[1].content == "d e f"

    def test_metadata_propagation(self):
        chunker = FixedChunker(max_tokens=100)
        chunks = chunker.chunk("hello world", metadata={"source": "test", "title": "doc"})
        assert chunks[0].metadata["source"] == "test"
        assert chunks[0].metadata["title"] == "doc"
        assert chunks[0].metadata["chunk_index"] == 0

    def test_chunk_index_metadata(self):
        chunker = FixedChunker(max_tokens=3, overlap_tokens=0)
        chunks = chunker.chunk("a b c d e f")
        assert chunks[0].metadata["chunk_index"] == 0
        assert chunks[1].metadata["chunk_index"] == 1

    def test_word_position_metadata(self):
        chunker = FixedChunker(max_tokens=3, overlap_tokens=0)
        chunks = chunker.chunk("a b c d e f")
        assert chunks[0].metadata["word_start"] == 0
        assert chunks[0].metadata["word_end"] == 3
        assert chunks[1].metadata["word_start"] == 3
        assert chunks[1].metadata["word_end"] == 6

    def test_heading_context(self):
        chunker = FixedChunker(max_tokens=10, overlap_tokens=0)
        text = "# Introduction\nThis is the intro section with several words.\n# Methods\nHere we describe methods."
        chunks = chunker.chunk(text)

        # First chunk should have heading_context = "Introduction"
        assert chunks[0].metadata.get("heading_context") == "Introduction"

    def test_heading_context_propagates(self):
        chunker = FixedChunker(max_tokens=5, overlap_tokens=0)
        text = "# Title\nword1 word2 word3 word4 word5 word6 word7 word8 word9"
        chunks = chunker.chunk(text)

        # All chunks after the heading should inherit heading context
        for chunk in chunks:
            assert chunk.metadata.get("heading_context") == "Title"

    def test_multiple_headings(self):
        chunker = FixedChunker(max_tokens=5, overlap_tokens=0)
        text = "# First\nword1 word2 word3\n# Second\nword4 word5 word6"
        chunks = chunker.chunk(text)

        # First chunk under "First" heading, later chunks under "Second"
        assert chunks[0].metadata.get("heading_context") == "First"
        assert any(
            c.metadata.get("heading_context") == "Second" for c in chunks[1:]
        ), "Expected at least one chunk under 'Second' heading"

    def test_single_word(self):
        chunker = FixedChunker(max_tokens=5, overlap_tokens=0)
        chunks = chunker.chunk("hello")
        assert len(chunks) == 1
        assert chunks[0].content == "hello"

    def test_metadata_not_shared_between_chunks(self):
        """Ensure each chunk gets its own metadata dict."""
        chunker = FixedChunker(max_tokens=3, overlap_tokens=0)
        chunks = chunker.chunk("a b c d e f", metadata={"shared": True})
        chunks[0].metadata["extra"] = "modified"
        assert "extra" not in chunks[1].metadata


class TestHybridDoclingChunker:
    """Test HybridDoclingChunker (falls back to FixedChunker)."""

    def test_name(self):
        chunker = HybridDoclingChunker()
        assert chunker.name == "hybrid"

    def test_fallback_to_fixed(self):
        chunker = HybridDoclingChunker(max_tokens=100)
        chunks = chunker.chunk("hello world this is a test")
        assert len(chunks) == 1
        assert chunks[0].content == "hello world this is a test"


class TestCreateChunker:
    """Test factory function."""

    def test_create_fixed(self):
        chunker = create_chunker("fixed", max_tokens=100, overlap_tokens=10)
        assert isinstance(chunker, FixedChunker)

    def test_create_hybrid(self):
        chunker = create_chunker("hybrid", max_tokens=100)
        assert isinstance(chunker, HybridDoclingChunker)

    def test_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            create_chunker("unknown")
