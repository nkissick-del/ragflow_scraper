"""Abstract base class for parser backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.scrapers.models import DocumentMetadata


@dataclass
class ParserResult:
    """Result from parsing a document."""

    success: bool
    markdown_path: Optional[Path] = None
    metadata: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    parser_name: str = ""

    def __post_init__(self):
        """Validate result consistency."""
        if self.success and not self.markdown_path:
            raise ValueError("Successful parse must include markdown_path")
        if not self.success and not self.error:
            raise ValueError("Failed parse must include error message")


class ParserBackend(ABC):
    """Abstract base class for document parsers."""

    @abstractmethod
    def parse_document(
        self, file_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """
        Parse a document to Markdown.

        Args:
            file_path: Path to file
            context_metadata: Scraper-provided metadata (URL, date, org)

        Returns:
            ParserResult with markdown_path and extracted metadata
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if parser dependencies are available.

        Returns:
            True if parser can be used
        """
        raise NotImplementedError

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported file extensions.

        Returns:
            List of extensions (e.g., ['.pdf', '.docx'])
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Get parser name for logging/identification."""
        raise NotImplementedError
