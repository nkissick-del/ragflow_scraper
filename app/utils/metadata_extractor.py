"""Generic structured metadata extraction from HTML pages.

Priority cascade: JSON-LD > Open Graph > meta tags.
Non-fatal: malformed HTML returns empty dict.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Schema.org Article types to look for in JSON-LD
_ARTICLE_TYPES = {
    "Article",
    "NewsArticle",
    "BlogPosting",
    "TechArticle",
    "ScholarlyArticle",
    "ReportageNewsArticle",
    "AnalysisNewsArticle",
    "OpinionNewsArticle",
    "ReviewNewsArticle",
}


def extract_structured_metadata(html: str) -> dict[str, Any]:
    """Extract structured metadata from an HTML page.

    Priority cascade: JSON-LD > Open Graph > meta tags.
    Returns a flat dict with keys:
        author, description, language, keywords, image_url,
        publication_date, title

    All values are optional — missing data is omitted from the dict.
    Non-fatal: malformed HTML returns empty dict.
    """
    if not html:
        return {}

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {}

    result: dict[str, Any] = {}

    # Layer 1: JSON-LD (highest priority)
    _extract_jsonld(soup, result)

    # Layer 2: Open Graph meta tags
    _extract_opengraph(soup, result)

    # Layer 3: Standard meta tags
    _extract_meta_tags(soup, result)

    # Layer 4: Byline links (lowest priority, for sites without structured author data)
    _extract_byline_link(soup, result)

    return result


def _extract_jsonld(soup: Any, result: dict[str, Any]) -> None:
    """Extract metadata from JSON-LD <script> tags."""
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)

            items: list[Any] = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                if "@graph" in data:
                    items = data["@graph"]
                else:
                    items = [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                # Handle list types (e.g., ["NewsArticle", "Article"])
                if isinstance(item_type, list):
                    if not any(t in _ARTICLE_TYPES for t in item_type):
                        continue
                elif item_type not in _ARTICLE_TYPES:
                    continue

                # Author
                if "author" not in result:
                    author = _extract_jsonld_author(item)
                    if author:
                        result["author"] = author

                # Description
                if "description" not in result:
                    desc = item.get("description") or item.get("abstract")
                    if desc and isinstance(desc, str):
                        result["description"] = desc.strip()

                # Publication date
                if "publication_date" not in result:
                    date_str = item.get("datePublished")
                    if date_str:
                        parsed = _normalize_date(date_str)
                        if parsed:
                            result["publication_date"] = parsed

                # Image
                if "image_url" not in result:
                    img = item.get("image")
                    if isinstance(img, str):
                        result["image_url"] = img
                    elif isinstance(img, dict):
                        img_url = img.get("url")
                        if img_url:
                            result["image_url"] = img_url
                    elif isinstance(img, list) and img:
                        first = img[0]
                        if isinstance(first, str):
                            result["image_url"] = first
                        elif isinstance(first, dict):
                            img_url = first.get("url")
                            if img_url:
                                result["image_url"] = img_url

                # Keywords
                if "keywords" not in result:
                    kw = item.get("keywords")
                    if isinstance(kw, str):
                        result["keywords"] = [
                            k.strip() for k in kw.split(",") if k.strip()
                        ]
                    elif isinstance(kw, list):
                        result["keywords"] = [
                            str(k).strip() for k in kw if k
                        ]

                # Language
                if "language" not in result:
                    lang = item.get("inLanguage")
                    if isinstance(lang, str):
                        result["language"] = lang
                    elif isinstance(lang, dict):
                        lang_name = lang.get("name")
                        if lang_name:
                            result["language"] = lang_name

                # Title
                if "title" not in result:
                    headline = item.get("headline")
                    if headline and isinstance(headline, str):
                        result["title"] = headline.strip()

                # Found an article — stop searching
                return

        except (json.JSONDecodeError, TypeError, KeyError):
            continue


def _extract_jsonld_author(item: dict) -> Optional[str]:
    """Extract author name from a JSON-LD item.

    Skips Organization-type authors (e.g. site name) — only accepts
    Person types or plain strings.
    """
    author = item.get("author")
    if not author:
        return None

    if isinstance(author, str):
        return author.strip()

    if isinstance(author, dict):
        # Skip Organization-type authors (site name, not a person)
        author_type = author.get("@type", "")
        if isinstance(author_type, str) and author_type.lower() == "organization":
            return None
        return (author.get("name") or "").strip() or None

    if isinstance(author, list):
        names = []
        for a in author:
            if isinstance(a, str):
                names.append(a.strip())
            elif isinstance(a, dict):
                # Skip Organization-type entries
                a_type = a.get("@type", "")
                if isinstance(a_type, str) and a_type.lower() == "organization":
                    continue
                name = (a.get("name") or "").strip()
                if name:
                    names.append(name)
        return ", ".join(names) if names else None

    return None


def _extract_opengraph(soup: Any, result: dict[str, Any]) -> None:
    """Extract metadata from Open Graph meta tags."""
    def _og(prop: str) -> Optional[str]:
        tag = soup.find("meta", property=prop)
        if tag:
            return (tag.get("content") or "").strip() or None
        return None

    if "description" not in result:
        desc = _og("og:description")
        if desc:
            result["description"] = desc

    if "image_url" not in result:
        img = _og("og:image")
        if img:
            result["image_url"] = img

    if "title" not in result:
        title = _og("og:title")
        if title:
            result["title"] = title

    if "language" not in result:
        lang = _og("og:locale")
        if lang:
            result["language"] = lang

    # article:author
    if "author" not in result:
        author = _og("article:author")
        if author:
            result["author"] = author

    # article:tag (may appear multiple times)
    if "keywords" not in result:
        tag_metas = soup.find_all("meta", property="article:tag")
        if tag_metas:
            keywords = [
                (m.get("content") or "").strip()
                for m in tag_metas
                if (m.get("content") or "").strip()
            ]
            if keywords:
                result["keywords"] = keywords

    # article:published_time
    if "publication_date" not in result:
        pub_time = _og("article:published_time")
        if pub_time:
            parsed = _normalize_date(pub_time)
            if parsed:
                result["publication_date"] = parsed


def _extract_meta_tags(soup: Any, result: dict[str, Any]) -> None:
    """Extract metadata from standard HTML meta tags."""
    def _meta(name: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": name})
        if tag:
            return (tag.get("content") or "").strip() or None
        return None

    if "author" not in result:
        author = _meta("author")
        if author:
            result["author"] = author

    if "description" not in result:
        desc = _meta("description")
        if desc:
            result["description"] = desc

    if "keywords" not in result:
        kw = _meta("keywords")
        if kw:
            result["keywords"] = [k.strip() for k in kw.split(",") if k.strip()]

    if "language" not in result:
        lang = _meta("language")
        if lang:
            result["language"] = lang

    # Also check html lang attribute
    if "language" not in result:
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            result["language"] = html_tag["lang"]


def _extract_byline_link(soup: Any, result: dict[str, Any]) -> None:
    """Extract author from byline links (e.g. /person/name, /author/name).

    Lowest-priority fallback for sites that don't put author in structured
    data but do link to author profile pages.
    """
    if "author" in result:
        return

    import re

    _BYLINE_PATH_RE = re.compile(r"/(person|author|people|writers?|staff)/")
    link = soup.find("a", href=_BYLINE_PATH_RE)
    if link:
        name = link.get_text(strip=True)
        if name and len(name) < 100:
            result["author"] = name


def _normalize_date(date_str: str) -> Optional[str]:
    """Normalize a date string to YYYY-MM-DD format.

    Handles ISO 8601 datetime strings with or without timezone info.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    date_str = date_str.strip()

    # Strip timezone suffix and time portion
    try:
        clean = date_str.split("+")[0].split("Z")[0]
        if "T" in clean:
            clean = clean.split("T")[0]
        dt = datetime.strptime(clean, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None
