"""AnythingLLM-compatible VIEW creation for pgvector.

Extracted from PgVectorClient to keep the VIEW SQL in one place.
"""

from __future__ import annotations

import re
from typing import Any

_VIEW_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def create_anythingllm_view(cursor: Any, view_name: str) -> None:
    """Create or replace the AnythingLLM-compatible VIEW.

    The VIEW adapts the scraper's document_chunks table schema
    to what AnythingLLM expects for pgvector queries:
    - id: UUID (deterministic from source/filename/chunk_index/id)
    - namespace: source column mapped
    - embedding: passed through
    - metadata: original metadata merged with 'text' key containing content
    - created_at: passed through

    Args:
        cursor: psycopg cursor
        view_name: Name for the VIEW (validated for safety)

    Raises:
        ValueError: If view_name contains invalid characters
    """
    if not _VIEW_NAME_RE.match(view_name):
        raise ValueError(
            f"Invalid view name: {view_name!r}. "
            "Only alphanumeric, underscore, and hyphen allowed."
        )

    from psycopg import sql as psql

    cursor.execute(psql.SQL("""
        CREATE OR REPLACE VIEW {} AS
        SELECT
            md5(COALESCE(source, '') || '/' || COALESCE(filename, '') || '/'
                || COALESCE(chunk_index::text, '') || '/' || COALESCE(id::text, ''))::uuid AS id,
            source AS namespace,
            embedding,
            metadata || jsonb_build_object('text', content) AS metadata,
            created_at
        FROM document_chunks
    """).format(psql.Identifier(view_name)))
