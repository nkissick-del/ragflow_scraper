"""
Archiver service for generating clean, archival-quality PDFs from content.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.remote.webdriver import WebDriver

from app.config import Config
from app.utils import get_logger
from app.scrapers.models import DocumentMetadata


class Archiver:
    """
    Generates 'Reader View' style PDFs from HTML content for archival.
    """

    # Minimalist, clean CSS for the archive PDF
    READER_CSS = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
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
    .metadata { margin-bottom: 40px; color: #666; font-size: 0.9em; background: #fafafa; padding: 15px; border-radius: 8px; }
    .metadata div { margin-bottom: 5px; }
    .metadata strong { color: #444; }
    .footer { margin-top: 60px; border-top: 1px solid #eee; padding-top: 20px; font-size: 0.8em; color: #999; text-align: center; }
    """

    def __init__(self, driver: Optional[WebDriver] = None):
        """
        Initialize Archiver.

        Args:
            driver: Optional Selenium WebDriver to reuse. If None, creates a new ephemeral one.
        """
        self.logger = get_logger("services.archiver")
        self._external_driver = driver is not None
        self.driver = driver

    def _get_driver(self) -> WebDriver:
        """Get or create the WebDriver."""
        if self.driver:
            return self.driver

        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--print-to-pdf-no-header")

        # Use remote grid if configured
        if Config.SELENIUM_REMOTE_URL:
            self.logger.debug(
                f"Connecting to remote Selenium at {Config.SELENIUM_REMOTE_URL}"
            )
            return webdriver.Remote(
                command_executor=Config.SELENIUM_REMOTE_URL, options=options
            )
        else:
            # Fallback to local (mostly for dev)
            self.logger.debug("Starting local Chrome driver")
            return webdriver.Chrome(options=options)

    def generate_pdf(
        self, content_html: str, metadata: DocumentMetadata, output_dir: Path
    ) -> Optional[Path]:
        """
        Generate a PDF from the provided HTML content.

        Args:
            content_html: The clean HTML content (article body)
            metadata: Document metadata for the header
            output_dir: Directory to save the PDF

        Returns:
            Path to the generated PDF or None on failure
        """
        driver = None
        temp_html_path = None

        try:
            # Prepare the full HTML document
            full_html = self._synthesize_html(content_html, metadata)

            # Save to temporary file for Selenium to load
            # We use a temp file because data: URIs can be size-limited
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False, encoding="utf-8"
            ) as f:
                f.write(full_html)
                temp_html_path = Path(f.name)

            # Start/Get driver
            driver = self._get_driver()

            # Load the file
            # Note: In Docker, we might need to mount this or use a data URI if shared volume issues arise.
            # For now, let's try file:// protocol locally, but if remote selenium is on another container,
            # it won't see our temp file!
            # FIX: If Remote Selenium, we MUST use data URI or expose the file via HTTP.
            # Let's use passed content directly via CDP or Data URI if small enough?
            # Actually, standard "print_page" in Selenium usually works on currently loaded page.
            # Safest for Remote Grid: Load via 'data:text/html;charset=utf-8,...'

            # Re-encoding to base64 to avoid URI syntax issues
            b64_content = base64.b64encode(full_html.encode("utf-8")).decode("utf-8")
            driver.get(f"data:text/html;base64,{b64_content}")

            # Print to PDF using CDP (Chrome DevTools Protocol)
            # This offers more control than standard print
            print_options = {
                "landscape": False,
                "displayHeaderFooter": False,
                "printBackground": True,
                "preferCSSPageSize": True,
            }

            # Execute CDP command
            # selenium-webdriver doesn't have a direct 'print_to_pdf' method in all versions,
            # but usually can be accessed via `execute_cdp_cmd`
            result = driver.execute_cdp_cmd("Page.printToPDF", print_options)  # type: ignore

            pdf_base64 = result.get("data")
            if not pdf_base64:
                raise ValueError("No PDF data received from CDP")

            # Decode and save
            output_filename = (
                f"{metadata.filename.replace('.md', '').replace('.html', '')}.pdf"
            )
            output_path = output_dir / output_filename

            with open(output_path, "wb") as f:
                f.write(base64.b64decode(pdf_base64))

            self.logger.info(f"Generated PDF: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Failed to generate PDF: {e}")
            return None

        finally:
            # Cleanup temp file
            if temp_html_path and temp_html_path.exists():
                try:
                    temp_html_path.unlink()
                except Exception:
                    pass

            # Quit driver if we created it (not external)
            if not self._external_driver and driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _synthesize_html(self, content: str, meta: DocumentMetadata) -> str:
        """Inject content into the Reader View template."""

        # Format metadata for display
        meta_html = f"""
        <div class="metadata">
            <div><strong>Source:</strong> <a href="{meta.url}">{meta.organization or "Unknown"}</a></div>
            <div><strong>Date:</strong> {meta.publication_date or "Unknown"}</div>
            <div><strong>Author:</strong> {meta.extra.get("author", "Unknown")}</div>
        </div>
        """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{meta.title}</title>
            <style>
                {self.READER_CSS}
            </style>
        </head>
        <body>
            <h1>{meta.title}</h1>
            {meta_html}
            <div class="content">
                {content}
            </div>
            <div class="footer">
                Archived by DeepMind Agent • {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </div>
        </body>
        </html>
        """
