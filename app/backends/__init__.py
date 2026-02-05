"""
Backend abstractions for modular document processing pipeline.

Provides swappable implementations for:
- Parsers: PDF → Markdown conversion (Docling, MinerU, Tika)
- Archives: Document storage (Paperless-ngx, S3, local filesystem)
- RAG: Vector indexing (RAGFlow, AnythingLLM)
"""

from app.backends.parsers.base import ParserBackend, ParserResult
from app.backends.archives.base import ArchiveBackend, ArchiveResult
from app.backends.rag.base import RAGBackend, RAGResult

__all__ = [
    "ParserBackend",
    "ParserResult",
    "ArchiveBackend",
    "ArchiveResult",
    "RAGBackend",
    "RAGResult",
]
