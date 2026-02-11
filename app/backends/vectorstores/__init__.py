"""Vector store backend abstractions.

Provides swappable implementations for vector storage:
- PgVector: PostgreSQL + pgvector extension
"""

from app.backends.vectorstores.base import VectorStoreBackend, VectorStoreResult

__all__ = [
    "VectorStoreBackend",
    "VectorStoreResult",
]
