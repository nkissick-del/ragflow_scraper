"""Utilities for building self-contained HTML article documents.

Provides:
- build_article_html(): wraps a bare HTML fragment in a full document with
  title, date, CSS, and <base> tag for URL resolution.
- inline_images(): downloads external <img> sources and converts them to
  base64 data URIs so the HTML is fully self-contained.
"""

from __future__ import annotations

import base64
import logging
from html import escape as html_escape
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import requests

logger = logging.getLogger(__name__)

# Maximum image size to inline (5 MB)
_MAX_IMAGE_SIZE = 5 * 1024 * 1024

# Reader-friendly CSS (matches gotenberg_client.py READER_CSS)
_ARTICLE_CSS = """
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
.article-meta { color: #666; font-size: 0.9em; margin-bottom: 2em; }
.article-meta a { color: #0066cc; }
"""


def build_article_html(
    body_html: str,
    title: str = "",
    date: str = "",
    organization: str = "",
    source_url: str = "",
    base_url: str = "",
) -> str:
    """Wrap an HTML fragment in a complete, styled HTML document.

    Args:
        body_html: The article body as an HTML fragment.
        title: Article title (rendered as <h1>).
        date: Publication date string.
        organization: Publisher/organization name.
        source_url: Original article URL (rendered as link).
        base_url: Base URL for resolving relative URLs (<base> tag).

    Returns:
        Complete HTML document string.
    """
    safe_title = html_escape(title) if title else ""
    base_tag = f'<base href="{html_escape(base_url)}">' if base_url else ""

    # Build metadata header
    meta_parts: list[str] = []
    if date:
        meta_parts.append(html_escape(date))
    if organization:
        meta_parts.append(html_escape(organization))
    if source_url:
        meta_parts.append(
            f'<a href="{html_escape(source_url)}">Original article</a>'
        )
    meta_line = " &middot; ".join(meta_parts)
    meta_html = f'<div class="article-meta">{meta_line}</div>' if meta_line else ""

    title_html = f"<h1>{safe_title}</h1>" if safe_title else ""

    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{safe_title}</title>\n"
        f"{base_tag}\n"
        f"<style>{_ARTICLE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{title_html}\n"
        f"{meta_html}\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>"
    )


def inline_images(
    html: str,
    session: Optional[requests.Session] = None,
    base_url: str = "",
    timeout: int = 15,
    max_size: int = _MAX_IMAGE_SIZE,
) -> str:
    """Download external images and replace src with base64 data URIs.

    Non-fatal: logs a warning per failed image and never raises.

    Args:
        html: HTML string containing <img> tags.
        session: HTTP session for downloads (uses cookies/headers). Falls back
            to a plain requests.get if None.
        base_url: Base URL for resolving relative src attributes.
        timeout: Per-image download timeout in seconds.
        max_size: Maximum image size in bytes to inline.

    Returns:
        HTML string with inlined images.
    """
    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")

    if not images:
        return html

    for img in images:
        src = img.get("src", "")
        if not src or src.startswith("data:"):
            continue

        # Resolve relative and protocol-relative URLs
        if src.startswith("//"):
            src = "https:" + src
        elif base_url and not src.startswith(("http://", "https://")):
            src = urljoin(base_url, src)

        try:
            if session is not None:
                resp = session.get(src, timeout=timeout)
            else:
                resp = requests.get(src, timeout=timeout)  # noqa: S113
            resp.raise_for_status()

            content = resp.content
            if len(content) > max_size:
                logger.warning(
                    "Image too large (%d bytes), skipping: %s", len(content), src
                )
                continue

            # Determine MIME type from Content-Type header, fallback to extension
            content_type = resp.headers.get("Content-Type", "")
            mime = content_type.split(";")[0].strip() if content_type else ""
            if not mime or not mime.startswith("image/"):
                # Guess from extension
                ext = src.rsplit(".", 1)[-1].lower().split("?")[0]
                mime_map = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                    "svg": "image/svg+xml",
                    "avif": "image/avif",
                }
                mime = mime_map.get(ext, "image/png")

            encoded = base64.b64encode(content).decode("ascii")
            img["src"] = f"data:{mime};base64,{encoded}"

        except Exception:
            logger.warning("Failed to inline image: %s", src, exc_info=True)
            continue

    return str(soup)
