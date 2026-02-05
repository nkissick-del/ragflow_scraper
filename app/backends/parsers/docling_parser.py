"""Docling parser backend implementation."""

from pathlib import Path
from typing import Optional

from app.backends.parsers.base import ParserBackend, ParserResult
from app.scrapers.models import DocumentMetadata
from app.utils import get_logger


class DoclingParser(ParserBackend):
    """Parser backend using IBM Docling."""

    def __init__(self):
        """Initialize Docling parser."""
        self.logger = get_logger("backends.parser.docling")
        self._docling_available = None

    @property
    def name(self) -> str:
        """Get parser name."""
        return "docling"

    def is_available(self) -> bool:
        """Check if Docling is available (lazy import)."""
        if self._docling_available is not None:
            return self._docling_available

        try:
            import docling  # noqa: F401

            self._docling_available = True
            self.logger.info("Docling parser available")
        except ImportError:
            self._docling_available = False
            self.logger.warning("Docling not installed - parser unavailable")

        return self._docling_available

    def get_supported_formats(self) -> list[str]:
        """Get supported file formats."""
        return [".pdf", ".docx", ".pptx", ".html"]

    def parse_document(
        self, pdf_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """
        Parse PDF to Markdown using Docling.

        Args:
            pdf_path: Path to PDF file
            context_metadata: Scraper-provided metadata (URL, date, org)

        Returns:
            ParserResult with markdown_path and extracted metadata
        """
        if not self.is_available():
            error_msg = "Docling not available - cannot parse document"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        if not pdf_path.exists():
            error_msg = f"File not found: {pdf_path}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        # Lazy import
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as e:
            error_msg = f"Failed to import Docling: {e}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        try:
            self.logger.info(f"Parsing document with Docling: {pdf_path.name}")

            # Initialize converter
            converter = DocumentConverter()

            # Convert document
            result = converter.convert(str(pdf_path))

            # Export to Markdown
            markdown_content = result.document.export_to_markdown()

            # Write Markdown file next to PDF
            markdown_path = pdf_path.with_suffix(".md")
            markdown_path.write_text(markdown_content, encoding="utf-8")

            # Extract metadata from parsed document
            extracted_metadata = self._extract_metadata(result, context_metadata)

            self.logger.info(
                f"Docling parse successful: {markdown_path.name} "
                f"({len(markdown_content)} chars)"
            )

            return ParserResult(
                success=True,
                markdown_path=markdown_path,
                metadata=extracted_metadata,
                parser_name=self.name,
            )

        except Exception as e:
            error_msg = f"Docling parsing failed: {e}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

    def _extract_metadata(
        self, docling_result, context_metadata: DocumentMetadata
    ) -> dict:
        """
        Extract metadata from Docling parse result.

        Args:
            docling_result: Docling ConversionResult object
            context_metadata: Original scraper metadata

        Returns:
            Metadata dict with title, author, etc.
        """
        metadata = {}

        # Try to extract title from document metadata
        doc = docling_result.document
        if hasattr(doc, "metadata") and doc.metadata:
            doc_meta = doc.metadata
            if hasattr(doc_meta, "title") and doc_meta.title:
                metadata["title"] = doc_meta.title
            if hasattr(doc_meta, "author") and doc_meta.author:
                metadata["author"] = doc_meta.author
            if hasattr(doc_meta, "creation_date") and doc_meta.creation_date:
                metadata["creation_date"] = str(doc_meta.creation_date)

        # If no title found in metadata, try to extract from first heading
        if "title" not in metadata:
            # Try to find first H1/H2 heading in markdown
            markdown = doc.export_to_markdown()
            for line in markdown.split("\n")[:20]:  # Check first 20 lines
                line = line.strip()
                if line.startswith("# "):
                    metadata["title"] = line.lstrip("# ").strip()
                    break
                elif line.startswith("## "):
                    metadata["title"] = line.lstrip("## ").strip()
                    break

        # Add parser info
        metadata["parsed_by"] = self.name
        metadata["page_count"] = len(doc.pages) if hasattr(doc, "pages") else None

        return metadata
