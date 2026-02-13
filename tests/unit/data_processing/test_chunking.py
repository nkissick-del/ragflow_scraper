"""Tests for chunking strategies."""

import pytest
from unittest.mock import patch, MagicMock

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

    def test_fallback_to_fixed_no_url(self):
        """Falls back to FixedChunker when no URL configured."""
        chunker = HybridDoclingChunker(max_tokens=100)
        chunks = chunker.chunk("hello world this is a test")
        assert len(chunks) == 1
        assert chunks[0].content == "hello world this is a test"

    def test_empty_text_returns_empty(self):
        """Empty input returns empty list without HTTP call."""
        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    @patch("app.services.chunking.requests")
    def test_calls_docling_serve(self, mock_requests):
        """Sends markdown to docling-serve and parses response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {
                    "text": "# Intro\n\nHello world",
                    "raw_text": "Hello world",
                    "headings": ["Intro"],
                    "num_tokens": 5,
                    "chunk_index": 0,
                },
                {
                    "text": "# Methods\n\nWe did stuff",
                    "raw_text": "We did stuff",
                    "headings": ["Methods"],
                    "num_tokens": 7,
                    "chunk_index": 1,
                },
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            max_tokens=256,
            docling_serve_url="http://localhost:4949",
            docling_serve_timeout=60,
        )
        chunks = chunker.chunk("# Intro\nHello world\n# Methods\nWe did stuff")

        assert len(chunks) == 2
        assert chunks[0].content == "# Intro\n\nHello world"
        assert chunks[1].content == "# Methods\n\nWe did stuff"

        # Verify HTTP call
        mock_requests.post.assert_called_once()
        call_kwargs = mock_requests.post.call_args
        assert "/v1/chunk/hybrid/file" in call_kwargs.args[0]
        assert call_kwargs.kwargs["timeout"] == 60

    @patch("app.services.chunking.requests")
    def test_fallback_on_http_error(self, mock_requests):
        """Falls back to FixedChunker when docling-serve returns error."""
        mock_requests.post.side_effect = Exception("Connection refused")

        chunker = HybridDoclingChunker(
            max_tokens=100,
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("hello world test content")

        # Should still return chunks via FixedChunker fallback
        assert len(chunks) >= 1
        assert chunks[0].content == "hello world test content"

    @patch("app.services.chunking.requests")
    def test_fallback_on_timeout(self, mock_requests):
        """Falls back to FixedChunker on request timeout."""
        import requests as real_requests

        mock_requests.post.side_effect = real_requests.exceptions.Timeout("timed out")

        chunker = HybridDoclingChunker(
            max_tokens=100,
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("hello world test content")
        assert len(chunks) >= 1

    @patch("app.services.chunking.requests")
    def test_fallback_on_empty_chunks(self, mock_requests):
        """Falls back when docling-serve returns empty chunks list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"chunks": []}
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            max_tokens=100,
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("hello world test content")

        # Should fall back to FixedChunker
        assert len(chunks) >= 1
        assert chunks[0].content == "hello world test content"

    @patch("app.services.chunking.requests")
    def test_heading_context_in_metadata(self, mock_requests):
        """Headings from response are stored in chunk metadata."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {
                    "text": "# Section A\n\nContent here",
                    "headings": ["Document", "Section A"],
                    "num_tokens": 10,
                    "chunk_index": 0,
                },
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("# Section A\nContent here")

        assert chunks[0].metadata["heading_context"] == "Section A"
        assert chunks[0].metadata["headings"] == ["Document", "Section A"]

    @patch("app.services.chunking.requests")
    def test_num_tokens_in_metadata(self, mock_requests):
        """Token count from response propagated to metadata."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {"text": "hello", "num_tokens": 42, "chunk_index": 0},
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("hello")

        assert chunks[0].metadata["num_tokens"] == 42
        assert chunks[0].metadata["chunker"] == "docling_hybrid"

    @patch("app.services.chunking.requests")
    def test_metadata_propagation(self, mock_requests):
        """Document-level metadata propagated to all chunks."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {"text": "chunk 1", "chunk_index": 0, "num_tokens": 2},
                {"text": "chunk 2", "chunk_index": 1, "num_tokens": 2},
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        metadata = {"source": "aemo", "title": "Test Doc", "url": "http://example.com"}
        chunks = chunker.chunk("chunk 1 chunk 2", metadata=metadata)

        for chunk in chunks:
            assert chunk.metadata["source"] == "aemo"
            assert chunk.metadata["title"] == "Test Doc"
            assert chunk.metadata["url"] == "http://example.com"
            assert chunk.metadata["chunker"] == "docling_hybrid"

    @patch("app.services.chunking.requests")
    def test_uses_text_field_for_content(self, mock_requests):
        """Chunk content uses contextualized 'text' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {
                    "text": "# Heading\n\nContextualized content",
                    "raw_text": "Contextualized content",
                    "chunk_index": 0,
                    "num_tokens": 5,
                },
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("# Heading\nContextualized content")

        # Should use 'text' (contextualized), not 'raw_text'
        assert chunks[0].content == "# Heading\n\nContextualized content"

    @patch("app.services.chunking.requests")
    def test_chunking_max_tokens_param(self, mock_requests):
        """max_tokens passed as chunking_max_tokens query param."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [{"text": "hello", "chunk_index": 0, "num_tokens": 1}]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            max_tokens=256,
            docling_serve_url="http://localhost:4949",
        )
        chunker.chunk("hello")

        call_kwargs = mock_requests.post.call_args
        params = call_kwargs.kwargs["params"]
        assert params["chunking_max_tokens"] == 256

    @patch("app.services.chunking.requests")
    def test_filename_from_metadata(self, mock_requests):
        """Filename in upload derived from metadata."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [{"text": "hello", "chunk_index": 0, "num_tokens": 1}]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        chunker.chunk("hello", metadata={"filename": "report.pdf"})

        call_kwargs = mock_requests.post.call_args
        files_arg = call_kwargs.kwargs["files"]
        # files dict: key "files", value is (filename, content, content_type)
        assert files_arg["files"][0] == "report.md"

    @patch("app.services.chunking.requests")
    def test_no_headings_in_metadata(self, mock_requests):
        """Chunks without headings don't have heading_context in metadata."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "chunks": [
                {"text": "plain content", "headings": [], "chunk_index": 0, "num_tokens": 2},
            ]
        }
        mock_requests.post.return_value = mock_response

        chunker = HybridDoclingChunker(
            docling_serve_url="http://localhost:4949",
        )
        chunks = chunker.chunk("plain content")

        assert "heading_context" not in chunks[0].metadata
        assert "headings" not in chunks[0].metadata


class TestCreateChunker:
    """Test factory function."""

    def test_create_fixed(self):
        chunker = create_chunker("fixed", max_tokens=100, overlap_tokens=10)
        assert isinstance(chunker, FixedChunker)

    def test_create_hybrid(self):
        chunker = create_chunker("hybrid", max_tokens=100)
        assert isinstance(chunker, HybridDoclingChunker)

    def test_create_hybrid_with_url(self):
        chunker = create_chunker(
            "hybrid",
            max_tokens=256,
            docling_serve_url="http://localhost:4949",
            docling_serve_timeout=60,
        )
        assert isinstance(chunker, HybridDoclingChunker)
        assert chunker._docling_url == "http://localhost:4949"
        assert chunker._timeout == 60

    def test_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            create_chunker("unknown")
