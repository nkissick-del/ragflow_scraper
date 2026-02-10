"""Mixin for extracting dates from JSON-LD schema.org Article structured data."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from bs4 import BeautifulSoup  # type: ignore[import-untyped]


class JSONLDDateExtractionMixin:
    """Extract publication/modification/creation dates from JSON-LD Article data.

    Handles:
    - Direct objects (``{"@type": "Article", ...}``)
    - ``@graph`` arrays
    - Multiple ``<script type="application/ld+json">`` tags
    - ``datePublished``, ``dateModified``, ``dateCreated`` fields
    """

    logger: Any = None

    def _extract_jsonld_dates(self, html: str) -> dict[str, Optional[str]]:
        """Parse JSON-LD scripts and return date fields from the first Article found.

        Args:
            html: HTML content of the article page.

        Returns:
            Dict with keys ``date_published``, ``date_created``, ``date_modified``.
            Values are ``YYYY-MM-DD`` strings or ``None``.
        """
        result: dict[str, Optional[str]] = {
            "date_published": None,
            "date_created": None,
            "date_modified": None,
        }

        soup = BeautifulSoup(html, "lxml")
        jsonld_scripts = soup.find_all("script", type="application/ld+json")

        for script in jsonld_scripts:
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
                    if item.get("@type") == "Article":
                        for key, field in [
                            ("date_published", "datePublished"),
                            ("date_created", "dateCreated"),
                            ("date_modified", "dateModified"),
                        ]:
                            if field in item and item[field]:
                                result[key] = self._parse_iso_date(item[field])

                        if any(result.values()):
                            return result

            except (json.JSONDecodeError, TypeError, KeyError) as e:
                if self.logger:
                    self.logger.debug(f"Failed to parse JSON-LD: {e}")
                continue

        return result

    def _parse_iso_date(self, date_str: str) -> Optional[str]:
        """Parse an ISO 8601 datetime string to ``YYYY-MM-DD``.

        Args:
            date_str: e.g. ``"2025-12-23T01:59:09+00:00"``

        Returns:
            Date in ``YYYY-MM-DD`` format, or ``None`` on parse failure.
        """
        if not date_str:
            return None
        try:
            clean = date_str.split("+")[0].split("Z")[0]
            if "T" in clean:
                clean = clean.split("T")[0]
            dt = datetime.strptime(clean, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            if self.logger:
                self.logger.debug(f"Could not parse ISO date: {date_str}")
            return None
