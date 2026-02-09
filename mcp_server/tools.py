"""MCP tool definitions for document search.

These tools can be called by any MCP-compatible LLM client.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure project root is on sys.path for app imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_int_env(name: str, default: int) -> int:
    """Parse an integer environment variable with clear error handling."""
    value = os.environ.get(name, str(default))
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be a valid integer, got: {value!r}")


def _get_pgvector_client():
    """Create a PgVectorClient from environment."""
    from app.services.pgvector_client import PgVectorClient

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    return PgVectorClient(
        database_url=database_url,
        dimensions=_parse_int_env("EMBEDDING_DIMENSIONS", 768),
    )


def _get_embedding_client():
    """Create an EmbeddingClient from environment."""
    from app.services.embedding_client import create_embedding_client

    backend = os.environ.get("EMBEDDING_BACKEND", "ollama")
    url = os.environ.get("EMBEDDING_URL", "")
    if not url:
        raise ValueError(
            f"EMBEDDING_URL environment variable is required for {backend} backend"
        )

    return create_embedding_client(
        backend=backend,
        model=os.environ.get("EMBEDDING_MODEL", "nomic-embed-text"),
        url=url,
        api_key=os.environ.get("EMBEDDING_API_KEY", ""),
        dimensions=_parse_int_env("EMBEDDING_DIMENSIONS", 768),
        timeout=_parse_int_env("EMBEDDING_TIMEOUT", 60),
    )


def search_documents(
    query: str,
    sources: Optional[list[str]] = None,
    limit: int = 10,
    metadata_filter: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Search documents by semantic similarity.

    Args:
        query: Natural language search query
        sources: Optional list of source names to filter by
        limit: Maximum number of results (default 10, max 50)
        metadata_filter: Optional metadata containment filter

    Returns:
        Dict with query, count, and results list
    """
    query = query.strip() if query else ""
    if not query:
        raise ValueError("query cannot be empty")
    if limit < 1:
        raise ValueError("limit must be a positive integer")

    embedder = None
    pgvector = None

    try:
        embedder = _get_embedding_client()
        pgvector = _get_pgvector_client()

        query_embedding = embedder.embed_single(query)
        results = pgvector.search(
            query_embedding=query_embedding,
            sources=sources,
            metadata_filter=metadata_filter,
            limit=min(limit, 50),
        )
        return {
            "query": query,
            "count": len(results),
            "results": results,
        }
    finally:
        try:
            if embedder is not None and hasattr(embedder, "close"):
                embedder.close()
        except Exception:
            pass
        try:
            if pgvector is not None:
                pgvector.close()
        except Exception:
            pass


def list_sources() -> dict[str, Any]:
    """List all available document sources with chunk counts.

    Returns:
        Dict with sources list and overall stats
    """
    pgvector = _get_pgvector_client()
    try:
        sources = pgvector.get_sources()
        stats = pgvector.get_stats()
        return {
            "sources": sources,
            "stats": stats,
        }
    finally:
        pgvector.close()


def get_document(source: str, filename: str) -> dict[str, Any]:
    """Get all chunks for a specific document.

    Args:
        source: Source/partition name
        filename: Document filename

    Returns:
        Dict with source, filename, chunk_count, and chunks list
    """
    source = source.strip() if source else ""
    if not source:
        raise ValueError("source cannot be empty")
    filename = filename.strip() if filename else ""
    if not filename:
        raise ValueError("filename cannot be empty")

    pgvector = _get_pgvector_client()
    try:
        chunks = pgvector.get_document_chunks(source, filename)
        return {
            "source": source,
            "filename": filename,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }
    finally:
        pgvector.close()
