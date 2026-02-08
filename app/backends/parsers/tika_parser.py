"""Tika parser backend implementation (HTTP REST API)."""

from pathlib import Path
from typing import Optional

from app.backends.parsers.base import ParserBackend, ParserResult
from app.scrapers.models import DocumentMetadata
from app.services.tika_client import TikaClient
from app.utils import get_logger


class TikaParser(ParserBackend):
    """Parser backend using Apache Tika server REST API."""

    SUPPORTED_FORMATS = [
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
        ".odt", ".ods", ".odp", ".rtf", ".html", ".htm", ".txt",
        ".epub", ".msg", ".eml", ".csv",
    ]

    def __init__(
        self,
        url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.client = TikaClient(url=url, timeout=timeout)
        self.logger = get_logger("backends.parser.tika")

    @property
    def name(self) -> str:
        return "tika"

    def is_available(self) -> bool:
        """Check if Tika server is reachable."""
        if not self.client.is_configured:
            return False
        try:
            return self.client.health_check()
        except Exception:
            return False

    def get_supported_formats(self) -> list[str]:
        return list(self.SUPPORTED_FORMATS)

    def parse_document(
        self, file_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """
        Parse document to Markdown using Tika server.

        Args:
            file_path: Path to file
            context_metadata: Scraper-provided metadata

        Returns:
            ParserResult with markdown_path and extracted metadata
        """
        if not self.client.is_configured:
            error_msg = "TIKA_SERVER_URL not configured"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        try:
            self.logger.info(f"Parsing document with Tika: {file_path.name}")

            # Extract text
            text = self.client.extract_text(file_path)

            if not text or not text.strip():
                error_msg = f"Tika returned empty text for {file_path.name}"
                self.logger.error(error_msg)
                return ParserResult(
                    success=False, error=error_msg, parser_name=self.name
                )

            # Extract metadata
            tika_meta = self.client.extract_metadata(file_path)

            # Build metadata dict
            extracted_metadata = self._extract_metadata(tika_meta, text)

            # Convert text to markdown
            title = (
                extracted_metadata.get("title")
                or context_metadata.title
                or file_path.stem
            )
            markdown_content = self._text_to_markdown(text, title=title)

            # Write markdown file next to original
            markdown_path = file_path.with_suffix(".md")
            markdown_path.write_text(markdown_content, encoding="utf-8")

            self.logger.info(
                f"Tika parse successful: {markdown_path.name} "
                f"({len(markdown_content)} chars)"
            )

            return ParserResult(
                success=True,
                markdown_path=markdown_path,
                metadata=extracted_metadata,
                parser_name=self.name,
            )

        except Exception as e:
            error_msg = f"Tika parsing failed: {e}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

    def _extract_metadata(self, tika_meta: dict, text: str) -> dict:
        """
        Build metadata dict from Tika-normalized metadata.

        Args:
            tika_meta: Normalized metadata from TikaClient
            text: Extracted text (for fallback title extraction)

        Returns:
            Metadata dict
        """
        metadata: dict = {}

        # Copy relevant normalized keys
        for key in ("title", "author", "creation_date", "page_count",
                     "content_type", "language", "word_count"):
            if key in tika_meta:
                metadata[key] = tika_meta[key]

        # Fallback: extract title from first non-empty line
        if "title" not in metadata:
            for line in text.split("\n")[:20]:
                line = line.strip()
                if line and len(line) > 3:
                    metadata["title"] = line[:200]
                    break

        metadata["parsed_by"] = self.name
        return metadata

    def _text_to_markdown(self, text: str, title: str | None = None) -> str:
        """
        Convert plain text to minimal markdown.

        Adds title heading and preserves paragraph breaks.

        Args:
            text: Plain text content
            title: Optional title for heading

        Returns:
            Markdown string
        """
        lines: list[str] = []

        if title:
            lines.append(f"# {title}")
            lines.append("")

        # Preserve paragraph structure (double newlines → paragraph breaks)
        paragraphs = text.split("\n\n")
        for para in paragraphs:
            cleaned = para.strip()
            if cleaned:
                lines.append(cleaned)
                lines.append("")

        return "\n".join(lines)
