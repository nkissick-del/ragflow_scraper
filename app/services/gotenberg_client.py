"""
Gotenberg client for document-to-PDF conversion.

Provides HTTP client for interacting with Gotenberg API:
- HTML to PDF conversion
- Markdown to PDF conversion (via HTML intermediate)
- Office document to PDF conversion
"""

from __future__ import annotations

from html import escape as _html_escape
from pathlib import Path
from typing import Optional

import requests
from lxml.html.clean import Cleaner

from app.config import Config
from app.utils import get_logger
from app.utils.file_utils import format_file_size


# Markdown → HTML conversion (lightweight, no heavy deps)
try:
    import markdown as _md

    def _md_to_html(text: str) -> str:
        return _md.markdown(text, extensions=["tables", "fenced_code"])

except ImportError:  # pragma: no cover – fallback for envs without markdown lib

    def _md_to_html(text: str) -> str:  # type: ignore[misc]
        """Minimal MD→HTML fallback (headings + paragraphs)."""
        lines = text.split("\n")
        html_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("### "):
                html_lines.append(f"<h3>{_html_escape(stripped[4:])}</h3>")
            elif stripped.startswith("## "):
                html_lines.append(f"<h2>{_html_escape(stripped[3:])}</h2>")
            elif stripped.startswith("# "):
                html_lines.append(f"<h1>{_html_escape(stripped[2:])}</h1>")
            elif stripped:
                html_lines.append(f"<p>{_html_escape(stripped)}</p>")
        return "\n".join(html_lines)


# Clean CSS for PDF rendering
READER_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px;
    color: #333;
}
h1 { font-size: 2.5em; margin-bottom: 0.5em; color: #111; border-bottom: 1px solid #eee; padding-bottom: 15px; }
h2 { font-size: 1.8em; margin-top: 2em; margin-bottom: 0.5em; color: #111; }
h3 { font-size: 1.4em; margin-top: 1.5em; margin-bottom: 0.5em; }
a { color: #0066cc; text-decoration: none; }
img { max-width: 100%; height: auto; border-radius: 4px; margin: 20px 0; }
blockquote { border-left: 4px solid #eee; padding-left: 15px; color: #666; margin: 20px 0; font-style: italic; }
pre { background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; }
code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; background: #f5f5f5; padding: 2px 5px; border-radius: 2px; }
"""


# Global cleaner instance (reused for performance)
# We start with the default safe attributes and add 'style' (needed for PDF rendering)
# This allows us to use safe_attrs_only=True for stricter security.
_SAFE_ATTRS = set(Cleaner().safe_attrs) | {"style"}

_HTML_CLEANER = Cleaner(
    scripts=True,
    javascript=True,
    comments=True,
    style=False,  # Allow <style> tags
    links=False,  # Allow <link> tags (CSS)
    meta=False,   # Allow <meta> tags
    page_structure=False,
    processing_instructions=True,
    embedded=True,  # Removes object, embed, applet
    frames=True,    # Removes frame, iframe
    forms=True,     # Removes form
    annoying_tags=False,
    remove_unknown_tags=False,
    safe_attrs_only=True,  # Strict attribute allowlist
    safe_attrs=_SAFE_ATTRS,
)


class GotenbergClient:
    """Client for Gotenberg document conversion API."""

    def __init__(
        self,
        url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.url = (url or Config.GOTENBERG_URL or "").rstrip("/")
        self.timeout = timeout or getattr(Config, "GOTENBERG_TIMEOUT", 60)
        self.logger = get_logger("gotenberg.client")

    def _check_file_size(self, file_path: Path) -> None:
        """Raise ValueError if file exceeds MAX_UPLOAD_FILE_SIZE (0 disables)."""
        limit = getattr(Config, "MAX_UPLOAD_FILE_SIZE", 0)
        if limit <= 0:
            return
        size = file_path.stat().st_size
        if size > limit:
            raise ValueError(
                f"File {file_path.name} ({format_file_size(size)}) exceeds "
                f"MAX_UPLOAD_FILE_SIZE ({format_file_size(limit)})"
            )

    @property
    def is_configured(self) -> bool:
        """Check if Gotenberg URL is set."""
        return bool(self.url)

    def health_check(self) -> bool:
        """Check Gotenberg health (GET /health)."""
        if not self.url:
            return False
        try:
            resp = requests.get(f"{self.url}/health", timeout=10)
            return resp.ok
        except Exception:
            return False

    def _sanitize_html(self, html_content: str) -> str:
        """
        Sanitize HTML to remove dangerous tags and attributes.

        Removes:
        - Scripts, iframes, objects, embeds, forms
        - Event handlers (onclick, etc.)
        - javascript: URIs
        """
        if not html_content:
            return ""

        try:
            return _HTML_CLEANER.clean_html(html_content)
        except Exception as e:
            self.logger.error(f"HTML sanitization failed: {e}")
            raise ValueError(f"Failed to sanitize HTML: {e}") from e

    def convert_html_to_pdf(
        self, html_content: str, title: str = ""
    ) -> bytes:
        """
        Convert HTML string to PDF via Gotenberg chromium endpoint.

        Args:
            html_content: Full or partial HTML content
            title: Optional title for the HTML document

        Returns:
            PDF file bytes

        Raises:
            requests.HTTPError: On non-2xx response
            requests.RequestException: On connection failure
        """
        # Sanitize HTML before processing
        html_content = self._sanitize_html(html_content)

        # Wrap in full HTML document if not already
        if "<html" not in html_content.lower():
            safe_title = _html_escape(title) if title else ""
            html_content = (
                "<!DOCTYPE html>\n<html>\n<head>\n"
                f"<meta charset=\"utf-8\">\n<title>{safe_title}</title>\n"
                f"<style>{READER_CSS}</style>\n"
                "</head>\n<body>\n"
                f"{html_content}\n"
                "</body>\n</html>"
            )

        files = {
            "files": ("index.html", html_content.encode("utf-8"), "text/html"),
        }

        resp = requests.post(
            f"{self.url}/forms/chromium/convert/html",
            files=files,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.content

    def convert_markdown_to_pdf(
        self, md_content: str, title: str = "", css: str = ""
    ) -> bytes:
        """
        Convert Markdown to PDF.

        Converts MD → HTML locally, wraps in styled template, then sends to
        Gotenberg HTML endpoint.

        Args:
            md_content: Markdown text
            title: Document title
            css: Optional CSS override (defaults to READER_CSS)

        Returns:
            PDF file bytes
        """
        style = css or READER_CSS
        body_html = _md_to_html(md_content)
        safe_title = _html_escape(title) if title else ""
        title_heading = f"<h1>{safe_title}</h1>\n" if title else ""

        full_html = (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            f"<meta charset=\"utf-8\">\n<title>{safe_title}</title>\n"
            f"<style>{style}</style>\n"
            "</head>\n<body>\n"
            f"{title_heading}{body_html}\n"
            "</body>\n</html>"
        )

        return self.convert_html_to_pdf(full_html, title=title)

    def convert_office_to_pdf(self, file_path: Path) -> bytes:
        """
        Convert office document (DOCX, XLSX, PPTX, etc.) to PDF
        via Gotenberg LibreOffice endpoint.

        Args:
            file_path: Path to office document

        Returns:
            PDF file bytes
        """
        self._check_file_size(file_path)
        with open(file_path, "rb") as f:
            files = {
                "files": (file_path.name, f, "application/octet-stream"),
            }
            resp = requests.post(
                f"{self.url}/forms/libreoffice/convert",
                files=files,
                timeout=self.timeout,
            )
        resp.raise_for_status()
        return resp.content

    def convert_to_pdf(self, file_path: Path) -> bytes:
        """
        Auto-route file to the appropriate conversion endpoint.

        Args:
            file_path: Path to file

        Returns:
            PDF file bytes
        """
        self._check_file_size(file_path)
        suffix = file_path.suffix.lower()

        if suffix in (".html", ".htm"):
            content = file_path.read_text(encoding="utf-8")
            return self.convert_html_to_pdf(content, title=file_path.stem)

        if suffix in (".md", ".markdown"):
            content = file_path.read_text(encoding="utf-8")
            return self.convert_markdown_to_pdf(content, title=file_path.stem)

        # Everything else → LibreOffice
        return self.convert_office_to_pdf(file_path)


__all__ = ["GotenbergClient"]
