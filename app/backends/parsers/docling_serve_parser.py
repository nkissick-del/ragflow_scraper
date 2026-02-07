"""Docling-serve parser backend implementation (HTTP REST API)."""

from pathlib import Path
from typing import Optional

import requests

from app.backends.parsers.base import ParserBackend, ParserResult
from app.config import Config
from app.scrapers.models import DocumentMetadata
from app.utils import get_logger


class DoclingServeParser(ParserBackend):
    """Parser backend using docling-serve REST API."""

    def __init__(
        self,
        url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize docling-serve parser.

        Args:
            url: Base URL of docling-serve (e.g. http://localhost:4949)
            timeout: Request timeout in seconds
        """
        self.url = (url or Config.DOCLING_SERVE_URL or "").rstrip("/")
        self.timeout = timeout or Config.DOCLING_SERVE_TIMEOUT
        self.logger = get_logger("backends.parser.docling_serve")

    @property
    def name(self) -> str:
        """Get parser name."""
        return "docling_serve"

    def is_available(self) -> bool:
        """Check if docling-serve is reachable via /health endpoint."""
        if not self.url:
            return False
        try:
            resp = requests.get(f"{self.url}/health", timeout=10)
            return resp.ok
        except Exception:
            return False

    def get_supported_formats(self) -> list[str]:
        """Get supported file formats."""
        return [".pdf", ".docx", ".pptx", ".html"]

    def parse_document(
        self, file_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """
        Parse document to Markdown using docling-serve REST API.

        Args:
            file_path: Path to file
            context_metadata: Scraper-provided metadata (URL, date, org)

        Returns:
            ParserResult with markdown_path and extracted metadata
        """
        if not self.url:
            error_msg = "DOCLING_SERVE_URL not configured"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        try:
            self.logger.info(
                f"Parsing document with docling-serve: {file_path.name}"
            )

            # POST to docling-serve convert endpoint
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{self.url}/v1/convert/file",
                    files={"files": (file_path.name, f)},
                    params={"to_formats": "md"},
                    timeout=self.timeout,
                )

            resp.raise_for_status()
            data = resp.json()

            # Extract markdown content from response
            document = data.get("document", {})
            markdown_content = document.get("md_content", "")

            if not markdown_content:
                error_msg = (
                    f"docling-serve returned empty markdown for {file_path.name}"
                )
                self.logger.error(error_msg)
                return ParserResult(
                    success=False, error=error_msg, parser_name=self.name
                )

            # Write Markdown file next to original
            markdown_path = file_path.with_suffix(".md")
            markdown_path.write_text(markdown_content, encoding="utf-8")

            # Extract metadata
            extracted_metadata = self._extract_metadata(document, markdown_content)

            self.logger.info(
                f"docling-serve parse successful: {markdown_path.name} "
                f"({len(markdown_content)} chars)"
            )

            return ParserResult(
                success=True,
                markdown_path=markdown_path,
                metadata=extracted_metadata,
                parser_name=self.name,
            )

        except requests.Timeout:
            error_msg = (
                f"docling-serve request timed out after {self.timeout}s "
                f"for {file_path.name}"
            )
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        except requests.HTTPError as e:
            error_msg = f"docling-serve HTTP error: {e}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        except Exception as e:
            error_msg = f"docling-serve parsing failed: {e}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

    def _extract_metadata(self, document: dict, markdown: str) -> dict:
        """
        Extract metadata from docling-serve response.

        Args:
            document: Document dict from API response
            markdown: Markdown content string

        Returns:
            Metadata dict with title, page_count, etc.
        """
        metadata: dict = {}

        # Try to get metadata from document response
        doc_meta = document.get("metadata", {})
        if isinstance(doc_meta, dict):
            if doc_meta.get("title"):
                metadata["title"] = doc_meta["title"]
            if doc_meta.get("author"):
                metadata["author"] = doc_meta["author"]
            if doc_meta.get("creation_date"):
                metadata["creation_date"] = str(doc_meta["creation_date"])

        # Extract page count if available
        page_count = document.get("page_count")
        if page_count is not None:
            metadata["page_count"] = page_count

        # If no title found in metadata, try to extract from first heading
        if "title" not in metadata:
            for line in markdown.split("\n")[:20]:
                line = line.strip()
                if line.startswith("# "):
                    metadata["title"] = line[len("# "):].strip()
                    break
                elif line.startswith("## "):
                    metadata["title"] = line[len("## "):].strip()
                    break

        metadata["parsed_by"] = self.name
        return metadata
