"""
Article-to-Markdown converter using trafilatura.

Replaces the custom GFMConverter with a production-grade extraction library.
Trafilatura is used by CommonCrawl, Internet Archive, and major NLP projects.
"""

from __future__ import annotations

import logging
from typing import Optional

import trafilatura  # type: ignore[import-untyped]
from trafilatura.settings import use_config  # type: ignore[import-untyped]


class ArticleConverter:
    """
    Convert HTML articles to clean Markdown using trafilatura.

    Replaces GFMConverter with a simpler, more reliable implementation.
    Trafilatura automatically handles:
    - Main content extraction (no manual selectors needed)
    - Author bio removal
    - Navigation/sidebar/ad removal
    - Social sharing button removal
    - Table preservation
    - Metadata extraction (title, author, date)

    Example usage:
        converter = ArticleConverter()
        markdown = converter.convert(html_content)
    """

    def __init__(self) -> None:
        """Initialize converter with optimized settings."""
        self.logger = logging.getLogger(__name__)

        # Configure trafilatura for extensive extraction
        self.config = use_config()
        self.config.set("DEFAULT", "EXTENSIVE_EXTRACTION", "on")

    def convert(
        self,
        html: str,
        content_selector: Optional[str] = None,  # Ignored but kept for API compat
        fallback_selectors: Optional[list[str]] = None,  # Ignored but kept for API compat
    ) -> str:
        """
        Convert HTML to GFM-compliant Markdown.

        Args:
            html: Raw HTML content
            content_selector: (Ignored) Kept for backwards compatibility
            fallback_selectors: (Ignored) Kept for backwards compatibility

        Returns:
            Clean markdown string or empty string if extraction fails
        """
        # Log if selectors are provided (for migration tracking)
        if content_selector or fallback_selectors:
            self.logger.debug(
                "Content selectors provided but ignored (trafilatura handles extraction)"
            )

        # Extract main content as Markdown
        markdown = trafilatura.extract(
            html,
            output_format='markdown',
            include_links=True,
            include_tables=True,
            include_images=False,  # Images don't help RAG
            include_comments=False,  # Skip comment sections
            config=self.config,
        )

        if not markdown:
            # Try fallback mode (less strict filtering)
            self.logger.warning("Standard extraction failed, trying fallback mode")
            markdown = trafilatura.extract(
                html,
                output_format='markdown',
                include_links=True,
                include_tables=True,
                include_images=False,
                no_fallback=False,  # Enable fallback extraction
                config=self.config,
            )

        if not markdown:
            self.logger.error("Failed to extract content from HTML")
            return ""

        return markdown.strip()

    def extract_metadata(self, html: str) -> dict[str, Optional[str]]:
        """
        Extract article metadata using trafilatura.

        Args:
            html: Raw HTML content

        Returns:
            Dict with keys: title, author, date, sitename, description, categories, tags, url
            Returns empty dict if extraction fails
        """
        meta = trafilatura.extract_metadata(html)

        if not meta:
            return {}

        return {
            'title': meta.title,
            'author': meta.author,
            'date': meta.date,
            'sitename': meta.sitename,
            'description': meta.description,
            'categories': meta.categories if meta.categories else [],
            'tags': meta.tags if meta.tags else [],
            'url': meta.url,
        }
