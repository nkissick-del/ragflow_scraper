"""
Backend registry for dynamic backend instantiation.

Replaces if/elif chains in ServiceContainer with a lookup table of factory functions.
Adding a new backend requires only a single register() call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Union

if TYPE_CHECKING:
    from app.backends import ParserBackend, ArchiveBackend, RAGBackend, VectorStoreBackend
    from app.services.container import ServiceContainer

BackendInstance = Union["ParserBackend", "ArchiveBackend", "RAGBackend", "VectorStoreBackend"]
BackendFactory = Callable[["ServiceContainer"], BackendInstance]


class BackendRegistry:
    """Registry mapping (backend_type, backend_name) to factory functions."""

    def __init__(self):
        self._factories: dict[tuple[str, str], BackendFactory] = {}

    def register(self, backend_type: str, backend_name: str, factory: BackendFactory) -> None:
        """Register a factory for a given backend type and name."""
        self._factories[(backend_type, backend_name)] = factory

    def create(self, backend_type: str, backend_name: str, container: ServiceContainer) -> Any:
        """Create a backend instance. Raises ValueError if unknown."""
        key = (backend_type, backend_name)
        if key not in self._factories:
            raise ValueError(f"Unknown {backend_type} backend: {backend_name}")
        return self._factories[key](container)

    def has(self, backend_type: str, backend_name: str) -> bool:
        """Check if a backend is registered."""
        return (backend_type, backend_name) in self._factories

    def names(self, backend_type: str) -> list[str]:
        """List registered backend names for a given type."""
        return [name for (btype, name) in self._factories if btype == backend_type]


# --- Parser factories ---

def _create_docling_parser(container: ServiceContainer) -> Any:
    from app.backends.parsers.docling_parser import DoclingParser
    return DoclingParser()


def _create_docling_serve_parser(container: ServiceContainer) -> Any:
    from app.backends.parsers.docling_serve_parser import DoclingServeParser
    return DoclingServeParser(
        url=container._get_effective_url("docling_serve", "DOCLING_SERVE_URL"),
        timeout=container._get_effective_timeout("docling_serve", "DOCLING_SERVE_TIMEOUT"),
    )


def _create_tika_parser(container: ServiceContainer) -> Any:
    from app.backends.parsers.tika_parser import TikaParser
    return TikaParser(
        url=container._get_effective_url("tika", "TIKA_SERVER_URL"),
        timeout=container._get_effective_timeout("tika", "TIKA_TIMEOUT"),
    )


def _create_mineru_parser(container: ServiceContainer) -> Any:
    raise ValueError("Parser backend 'mineru' not yet implemented")


# --- Archive factories ---

def _create_paperless_archive(container: ServiceContainer) -> Any:
    from app.backends.archives.paperless_adapter import PaperlessArchiveBackend
    return PaperlessArchiveBackend()


def _create_s3_archive(container: ServiceContainer) -> Any:
    raise ValueError("Archive backend 's3' not yet implemented")


def _create_local_archive(container: ServiceContainer) -> Any:
    raise ValueError("Archive backend 'local' not yet implemented")


# --- Vector store factories ---

def _create_pgvector_vector_store(container: "ServiceContainer") -> Any:
    from app.backends.vectorstores.pgvector_store import PgVectorVectorStore
    from app.config import Config

    db_url = container._get_effective_url("pgvector", "DATABASE_URL")
    if not db_url:
        raise ValueError("PgVector configuration missing: DATABASE_URL is required")
    dims = container._safe_int(container._get_config_attr("EMBEDDING_DIMENSIONS", "768"), 768)
    view_name = container._get_config_attr("ANYTHINGLLM_VIEW_NAME", "anythingllm_document_view")
    drop_on_mismatch = getattr(Config, "PGVECTOR_DROP_ON_MISMATCH", False)
    return PgVectorVectorStore(
        database_url=db_url,
        dimensions=dims,
        view_name=view_name,
        drop_on_dimension_mismatch=bool(drop_on_mismatch),
    )


# --- RAG factories ---

def _create_ragflow_rag(container: ServiceContainer) -> Any:
    ragflow_url = container._get_effective_url("ragflow", "RAGFLOW_API_URL")
    ragflow_key = container._get_config_attr("RAGFLOW_API_KEY")
    if not ragflow_url or not ragflow_key:
        raise ValueError(
            "RAGFlow configuration missing: "
            "RAGFLOW_API_URL and RAGFLOW_API_KEY are required"
        )
    from app.backends.rag.ragflow_adapter import RAGFlowBackend
    return RAGFlowBackend()


def _create_anythingllm_rag(container: ServiceContainer) -> Any:
    anythingllm_url = container._get_effective_url("anythingllm", "ANYTHINGLLM_API_URL")
    anythingllm_key = container._get_config_attr("ANYTHINGLLM_API_KEY")
    if not anythingllm_url or not anythingllm_key:
        raise ValueError(
            "AnythingLLM configuration missing: "
            "ANYTHINGLLM_API_URL and ANYTHINGLLM_API_KEY are required"
        )
    from app.backends.rag.anythingllm_adapter import AnythingLLMBackend
    return AnythingLLMBackend(
        api_url=anythingllm_url,
        api_key=anythingllm_key,
        workspace_id=container._get_config_attr("ANYTHINGLLM_WORKSPACE_ID"),
    )


def _create_vector_rag(container: "ServiceContainer") -> Any:
    vector_store = container.vector_store
    embedding_client = container.embedding_client
    if not vector_store or not embedding_client:
        raise ValueError(
            "Vector RAG requires both vector_store and embedding_client"
        )
    try:
        chunk_max_tokens = int(container._get_config_attr("CHUNK_MAX_TOKENS", "512"))
        chunk_overlap_tokens = int(container._get_config_attr("CHUNK_OVERLAP_TOKENS", "64"))
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid chunking configuration: {e}") from e
    from app.backends.rag.vector_adapter import VectorRAGBackend
    return VectorRAGBackend(
        vector_store=vector_store,
        embedding_client=embedding_client,
        chunking_strategy=container._get_config_attr("CHUNKING_STRATEGY", "hybrid"),
        chunk_max_tokens=chunk_max_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        docling_serve_url=container._get_effective_url("docling_serve", "DOCLING_SERVE_URL"),
        docling_serve_timeout=container._get_effective_timeout("docling_serve", "DOCLING_SERVE_TIMEOUT"),
    )


# --- Default registry ---

_default_registry = BackendRegistry()

# Parsers
_default_registry.register("parser", "docling", _create_docling_parser)
_default_registry.register("parser", "docling_serve", _create_docling_serve_parser)
_default_registry.register("parser", "tika", _create_tika_parser)
_default_registry.register("parser", "mineru", _create_mineru_parser)

# Archives
_default_registry.register("archive", "paperless", _create_paperless_archive)
_default_registry.register("archive", "s3", _create_s3_archive)
_default_registry.register("archive", "local", _create_local_archive)

# Vector stores
_default_registry.register("vectorstore", "pgvector", _create_pgvector_vector_store)

# RAG — "vector" and "pgvector" both point to the generic vector adapter
_default_registry.register("rag", "ragflow", _create_ragflow_rag)
_default_registry.register("rag", "anythingllm", _create_anythingllm_rag)
_default_registry.register("rag", "pgvector", _create_vector_rag)
_default_registry.register("rag", "vector", _create_vector_rag)


def get_backend_registry() -> BackendRegistry:
    """Get the default backend registry."""
    return _default_registry
