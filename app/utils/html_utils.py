"""Utilities for building self-contained HTML article documents.

Provides:
- clean_article_html(): removes non-article noise (share buttons, CTAs, scripts)
  from HTML before PDF generation.
- build_article_html(): wraps a bare HTML fragment in a full document with
  title, date, CSS, and <base> tag for URL resolution.
- inline_images(): downloads external <img> sources and converts them to
  base64 data URIs so the HTML is fully self-contained.
"""

from __future__ import annotations

import base64
import logging
import re as _re
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


# Social share URL patterns
_SOCIAL_SHARE_PATTERNS = [
    "linkedin.com/sharing",
    "twitter.com/intent",
    "x.com/intent",
    "facebook.com/sharer",
]

# Class substrings that indicate non-article content
_NOISE_CLASS_PATTERNS = ["newsletter", "signup"]

# Subscribe CTA text patterns (case-insensitive)
_SUBSCRIBE_CTA_RE = _re.compile(
    r"(subscribe|sign\s*up|get .* in your inbox)", _re.IGNORECASE
)


def clean_article_html(
    html: str,
    extra_removals: Optional[list[dict[str, str]]] = None,
) -> str:
    """Remove non-article noise from HTML before PDF generation.

    Universal removals (all sites):
    - <script>, <style>, <iframe>, <noscript> tags
    - Social share links (LinkedIn, Twitter/X, Facebook)
    - Elements with newsletter/signup classes
    - Subscribe CTA links

    Per-scraper removals via extra_removals list of dicts with keys:
    - selector: CSS selector to match
    - class_contains: match elements whose class contains this string
    - text: only remove if element text matches
    - remove_parent_levels: int, remove N parent levels up (default 0)

    Non-fatal: returns original HTML on any error.
    """
    if not html or not html.strip():
        return html

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    try:
        # Remove script, style, iframe, noscript tags
        for tag_name in ("script", "style", "iframe", "noscript"):
            for el in soup.find_all(tag_name):
                el.decompose()

        # Remove social share links
        for pattern in _SOCIAL_SHARE_PATTERNS:
            for a_tag in soup.find_all("a", href=_re.compile(_re.escape(pattern))):
                # Check if parent is a tooltip/share wrapper and remove it too
                parent = a_tag.parent
                if parent and parent.name != "body":
                    parent_classes = " ".join(parent.get("class", []))
                    parent_classes_lower = parent_classes.lower()
                    if "tooltip" in parent_classes_lower or "share" in parent_classes_lower:
                        parent.decompose()
                        continue
                a_tag.decompose()

        # Remove elements with share/social classes
        for el in soup.find_all(class_=_re.compile(r"\b(share|social)\b", _re.IGNORECASE)):
            # Don't remove if it contains substantial article text (>200 chars)
            if len(el.get_text(strip=True)) > 200:
                continue
            el.decompose()

        # Remove elements with newsletter/signup classes
        for pattern in _NOISE_CLASS_PATTERNS:
            for el in soup.find_all(class_=_re.compile(pattern, _re.IGNORECASE)):
                el.decompose()

        # Remove subscribe CTA links
        for a_tag in soup.find_all("a", href=_re.compile(r"/subscribe")):
            text = a_tag.get_text(strip=True)
            if _SUBSCRIBE_CTA_RE.search(text):
                a_tag.decompose()

        # Apply per-scraper extra removals
        if extra_removals:
            for removal in extra_removals:
                _apply_extra_removal(soup, removal)

        return str(soup)
    except Exception:
        logger.warning("HTML cleaning failed, returning original", exc_info=True)
        return html


def _apply_extra_removal(soup: BeautifulSoup, removal: dict[str, str]) -> None:
    """Apply a single extra removal rule to the soup."""
    selector = removal.get("selector", "")
    class_contains = removal.get("class_contains", "")
    text_match = removal.get("text", "")
    try:
        remove_parent_levels = int(removal.get("remove_parent_levels", "0"))
    except (ValueError, TypeError):
        remove_parent_levels = 0

    if class_contains:
        elements = soup.find_all(
            selector or True,
            class_=_re.compile(_re.escape(class_contains)),
        )
    elif selector:
        elements = soup.select(selector)
    else:
        return

    for el in elements:
        if text_match and text_match not in el.get_text(strip=True):
            continue

        target = el
        for _ in range(remove_parent_levels):
            if target.parent and target.parent.name != "[document]":
                target = target.parent
        target.decompose()


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
