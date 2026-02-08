"""Docling parser backend implementation."""

from pathlib import Path
from typing import Optional


import multiprocessing
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
            import docling  # type: ignore # noqa: F401

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
        self, file_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """
        Parse document to Markdown using Docling.

        Args:
            file_path: Path to file
            context_metadata: Scraper-provided metadata (URL, date, org)

        Returns:
            ParserResult with markdown_path and extracted metadata
        """
        if not self.is_available():
            error_msg = "Docling not available - cannot parse document"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            self.logger.error(error_msg)
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

        # Standard imports
        from queue import Empty

        try:
            self.logger.info(f"Parsing document with Docling: {file_path.name}")

            # Use an explicit multiprocessing.Process to ensure we can kill it on timeout
            queue = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=_run_conversion_to_queue, args=(str(file_path), queue)
            )

            process.start()

            try:
                # Wait for result with timeout (300s = 5m)
                raw_result = queue.get(timeout=300)
                process.join(timeout=5)  # Give it a moment to finish gracefully
            except Empty:
                error_msg = f"Docling conversion timed out for {file_path.name}"
                self.logger.error(error_msg)

                if process.is_alive():
                    self.logger.warning(
                        f"Terminating hanging Docling process for {file_path.name}"
                    )
                    process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        self.logger.warning(
                            f"Killing hanging Docling process for {file_path.name}"
                        )
                        process.kill()
                        process.join()

                # Cleanup queue resources
                queue.close()
                queue.join_thread()

                return ParserResult(
                    success=False, error=error_msg, parser_name=self.name
                )
            finally:
                # Cleanup if still alive for any reason
                if process.is_alive():
                    process.terminate()
                    process.join()
                # Cleanup queue resources
                queue.close()
                queue.join_thread()

            if not raw_result or not raw_result.get("success"):
                error_msg = (
                    raw_result.get("error")
                    if raw_result
                    else f"Docling conversion failed for {file_path.name}"
                )
                self.logger.error(f"Docling conversion failed: {error_msg}")
                if raw_result and raw_result.get("traceback"):
                    self.logger.debug(f"Docling traceback: {raw_result['traceback']}")

                return ParserResult(
                    success=False, error=error_msg, parser_name=self.name
                )

            # Export to Markdown
            result = raw_result["result"]
            markdown_content = result["markdown"]
            docling_meta = result["metadata"]
            page_count = result["page_count"]

            # Write Markdown file next to artifact
            markdown_path = file_path.with_suffix(".md")
            try:
                markdown_path.write_text(markdown_content, encoding="utf-8")
            except (OSError, IOError) as e:
                self.logger.error(f"Failed to write markdown to {markdown_path}: {e}")
                # Re-raise to let the outer handler handle the failure
                raise

            # Extract metadata from parsed document
            extracted_metadata = self._extract_metadata(
                docling_meta, page_count, markdown_content
            )

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
            import traceback

            error_msg = f"Docling parsing failed: {e}"
            self.logger.error(error_msg)
            self.logger.debug(traceback.format_exc())
            return ParserResult(success=False, error=error_msg, parser_name=self.name)

    def _extract_metadata(
        self, docling_meta: dict, page_count: Optional[int], markdown: str
    ) -> dict:
        """
        Extract metadata from Docling parse result.

        Args:
            docling_meta: Metadata dict from Docling
            page_count: Number of pages
            markdown: Pre-computed markdown content

        Returns:
            Metadata dict with title, author, etc.
        """
        metadata = {}

        # Use metadata from Docling if available
        if docling_meta:
            if docling_meta.get("title"):
                metadata["title"] = docling_meta["title"]
            if docling_meta.get("author"):
                metadata["author"] = docling_meta["author"]
            if docling_meta.get("creation_date"):
                metadata["creation_date"] = str(docling_meta["creation_date"])

        # If no title found in metadata, try to extract from first heading
        if "title" not in metadata:
            # Check first 20 lines of the already computed markdown
            for line in markdown.split("\n")[:20]:
                line = line.strip()
                if line.startswith("# "):
                    metadata["title"] = line[len("# ") :].strip()
                    break
                elif line.startswith("## "):
                    metadata["title"] = line[len("## ") :].strip()
                    break

        # Add parser info
        metadata["parsed_by"] = self.name
        metadata["page_count"] = page_count

        return metadata


def _run_conversion_to_queue(file_path: str, queue: multiprocessing.Queue):
    """Helper function to run Docling conversion and put result in a queue."""
    try:
        result = _run_conversion(file_path)
        queue.put(result)
    except Exception as e:
        # Build error payload to send to parent
        import traceback
        import sys
        import os

        error_payload = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }

        # Attempt to send error payload to queue
        try:
            queue.put(error_payload)
        except Exception as queue_error:
            # If blocking put fails, try non-blocking fallback
            try:
                queue.put_nowait(error_payload)
            except Exception as nowait_error:
                # Both queue operations failed - print to stderr and exit
                print(
                    f"FATAL: Failed to send error to queue: {queue_error}, {nowait_error}",
                    file=sys.stderr,
                )
                print(f"Original error: {error_payload}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                # Exit worker process with non-zero code so parent can detect failure
                os._exit(1)


def _run_conversion(file_path: str) -> dict:
    """Helper function to run Docling conversion in a separate process."""
    import traceback

    try:
        from docling.document_converter import DocumentConverter  # type: ignore

        converter = DocumentConverter()
        result = converter.convert(file_path)

        # Extract what we need and return it (must be picklable)
        doc = result.document
        markdown_content = doc.export_to_markdown()

        doc_meta = {}
        if hasattr(doc, "metadata") and doc.metadata:
            if hasattr(doc.metadata, "title"):
                doc_meta["title"] = doc.metadata.title
            if hasattr(doc.metadata, "author"):
                doc_meta["author"] = doc.metadata.author
            if hasattr(doc.metadata, "creation_date"):
                doc_meta["creation_date"] = doc.metadata.creation_date

        return {
            "success": True,
            "result": {
                "markdown": markdown_content,
                "metadata": doc_meta,
                "page_count": len(doc.pages) if hasattr(doc, "pages") else None,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
