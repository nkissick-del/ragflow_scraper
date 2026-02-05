"""AnythingLLM RAG backend adapter (stub implementation)."""

from pathlib import Path
from typing import Optional

from app.backends.rag.base import RAGBackend, RAGResult
from app.utils import get_logger


class AnythingLLMBackend(RAGBackend):
    """RAG backend using AnythingLLM (not yet implemented)."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ):
        """
        Initialize AnythingLLM backend.

        Args:
            api_url: AnythingLLM API URL
            api_key: API key for authentication
            workspace_id: Default workspace ID
        """
        self.api_url = api_url
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.logger = get_logger("backends.rag.anythingllm")

    @property
    def name(self) -> str:
        """Get RAG backend name."""
        return "anythingllm"

    def is_configured(self) -> bool:
        """Check if AnythingLLM is properly configured."""
        return bool(self.api_url and self.api_key)

    def test_connection(self) -> bool:
        """Test connection to AnythingLLM service."""
        self.logger.warning("AnythingLLM backend not implemented")
        return False

    def ingest_document(
        self,
        markdown_path: Path,
        metadata: dict,
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        """
        Ingest Markdown document into AnythingLLM.

        Args:
            markdown_path: Path to Markdown file
            metadata: Document metadata dict
            collection_id: Optional workspace ID

        Returns:
            RAGResult with error (not implemented)
        """
        error_msg = (
            "AnythingLLM backend not yet implemented. "
            "Please use RAGFlow backend or contribute implementation."
        )
        self.logger.error(error_msg)
        return RAGResult(success=False, error=error_msg, rag_name=self.name)
