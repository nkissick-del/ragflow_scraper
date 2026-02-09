"""
Backend registry for dynamic backend instantiation.

Replaces if/elif chains in ServiceContainer with a lookup table of factory functions.
Adding a new backend requires only a single register() call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Union

if TYPE_CHECKING:
    from app.backends import ParserBackend, ArchiveBackend, RAGBackend
    from app.services.container import ServiceContainer

BackendInstance = Union["ParserBackend", "ArchiveBackend", "RAGBackend"]
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


def _create_pgvector_rag(container: "ServiceContainer") -> Any:
    pgvector_client = container.pgvector_client
    embedding_client = container.embedding_client
    if not pgvector_client or not embedding_client:
        raise ValueError(
            "PgVector RAG requires both pgvector_client and embedding_client"
        )
    try:
        chunk_max_tokens = int(container._get_config_attr("CHUNK_MAX_TOKENS", "512"))
        chunk_overlap_tokens = int(container._get_config_attr("CHUNK_OVERLAP_TOKENS", "64"))
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid chunking configuration: {e}") from e
    from app.backends.rag.pgvector_adapter import PgVectorRAGBackend
    return PgVectorRAGBackend(
        pgvector_client=pgvector_client,
        embedding_client=embedding_client,
        chunking_strategy=container._get_config_attr("CHUNKING_STRATEGY", "fixed"),
        chunk_max_tokens=chunk_max_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
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

# RAG
_default_registry.register("rag", "ragflow", _create_ragflow_rag)
_default_registry.register("rag", "anythingllm", _create_anythingllm_rag)
_default_registry.register("rag", "pgvector", _create_pgvector_rag)


def get_backend_registry() -> BackendRegistry:
    """Get the default backend registry."""
    return _default_registry
