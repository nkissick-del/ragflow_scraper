"""Search API and UI for pgvector semantic search."""

from __future__ import annotations

import re

from flask import Blueprint, render_template, request, jsonify

from app.utils import get_logger
from app.utils.logging_config import log_exception
from app.web.runtime import container

bp = Blueprint("search", __name__)
logger = get_logger("web.search")

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.@-]+$")


@bp.route("/search")
def search_page():
    """Render the search page."""
    sources = []
    try:
        client = container.pgvector_client
        if client.is_configured() and client.test_connection():
            sources = client.get_sources()
    except Exception as exc:
        log_exception(logger, exc, "search.sources.error")

    return render_template("search.html", sources=sources)


@bp.route("/api/search", methods=["POST"])
def search():
    """Semantic search across document chunks.

    Request JSON:
        query: str - search text
        sources: list[str] - optional source filter
        limit: int - max results (default 10, max 50)
        metadata_filter: dict - optional JSONB containment filter
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Query is required"}), 400

    sources = data.get("sources", None)
    if sources is not None:
        if not isinstance(sources, list):
            return jsonify({"error": "sources must be a list"}), 400
        for src in sources:
            if not isinstance(src, str) or not _SAFE_NAME_RE.match(src):
                return jsonify({"error": "Invalid source name"}), 400
    try:
        limit = int(data.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))
    metadata_filter = data.get("metadata_filter", None)
    if metadata_filter is not None and not isinstance(metadata_filter, dict):
        return jsonify({"error": "metadata_filter must be an object"}), 400

    try:
        embedder = container.embedding_client
        if not embedder.is_configured():
            return jsonify({"error": "Embedding service not configured"}), 503

        pgvector = container.pgvector_client
        if not pgvector.is_configured():
            return jsonify({"error": "pgvector not configured"}), 503

        # Embed the query
        query_embedding = embedder.embed_single(query)

        # Search
        results = pgvector.search(
            query_embedding=query_embedding,
            sources=sources if sources else None,
            metadata_filter=metadata_filter,
            limit=limit,
        )

        return jsonify({
            "query": query,
            "count": len(results),
            "results": results,
        })

    except Exception as exc:
        log_exception(logger, exc, "search.query.error")
        return jsonify({"error": "Search failed"}), 500


@bp.route("/api/sources")
def list_sources():
    """List available sources with chunk counts."""
    try:
        client = container.pgvector_client
        if not client.is_configured():
            return jsonify({"error": "pgvector not configured"}), 503

        sources = client.get_sources()
        stats = client.get_stats()
        return jsonify({
            "sources": sources,
            "stats": stats,
        })
    except Exception as exc:
        log_exception(logger, exc, "search.sources.error")
        return jsonify({"error": "Failed to list sources"}), 500


@bp.route("/api/search/document/<source>/<path:filename>")
def get_document_chunks(source: str, filename: str):
    """Get all chunks for a specific document."""
    if not source or ".." in source or not _SAFE_NAME_RE.match(source):
        return jsonify({"error": "Invalid source"}), 400
    if not filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    try:
        client = container.pgvector_client
        if not client.is_configured():
            return jsonify({"error": "pgvector not configured"}), 503

        chunks = client.get_document_chunks(source, filename)

        return jsonify({
            "source": source,
            "filename": filename,
            "chunk_count": len(chunks),
            "chunks": chunks,
        })
    except Exception as exc:
        log_exception(logger, exc, "search.document.error")
        return jsonify({"error": "Failed to get document chunks"}), 500
