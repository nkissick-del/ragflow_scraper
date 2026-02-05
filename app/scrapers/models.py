"""Shared scraper data models."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

INT_FIELDS = {"file_size", "page_count"}


@dataclass
class DocumentMetadata:
    url: str
    title: str
    filename: str
    file_size: Optional[int] = None
    file_size_str: Optional[str] = None
    publication_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source_page: Optional[str] = None
    organization: Optional[str] = None
    document_type: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    local_path: Optional[str] = None
    hash: Optional[str] = None
    extra: dict = field(default_factory=dict)

    # Paperless integration
    paperless_id: Optional[str] = None
    pdf_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_ragflow_metadata(self) -> dict:
        metadata = {
            "organization": self.organization or "Unknown",
            "source_url": self.url,
            "scraped_at": self.scraped_at,
            "document_type": self.document_type or "Unknown",
        }
        if self.publication_date:
            metadata["publication_date"] = self.publication_date
        if self.extra.get("author"):
            metadata["author"] = self.extra["author"]
        abstract = self.extra.get("abstract") or self.extra.get("description")
        if abstract:
            metadata["abstract"] = abstract
        return metadata

    def merge_parser_metadata(
        self, parser_metadata: dict, strategy: str = "smart"
    ) -> DocumentMetadata:
        """
        Merge parser-extracted metadata with scraper context.

        Strategy:
        - "smart": Context (URL, date, org) from scraper; Content (title, author) from parser
        - "parser_wins": Parser overwrites all fields
        - "scraper_wins": Keep scraper metadata, only add new fields from parser

        Args:
            parser_metadata: Metadata extracted by parser backend
            strategy: Merge strategy ("smart", "parser_wins", "scraper_wins")

        Returns:
            New DocumentMetadata instance with merged data
        """
        from app.utils.errors import MetadataMergeError

        # Create deep copy of current metadata as dict to avoid mutating self.extra
        merged = copy.deepcopy(self.to_dict())
        standard_fields = {f.name for f in fields(DocumentMetadata)}

        if strategy == "smart":
            # Parser wins for content fields (title, author)
            if parser_metadata.get("title"):
                merged["title"] = parser_metadata["title"]

            # Add author to extra if available
            if parser_metadata.get("author"):
                merged["extra"]["author"] = parser_metadata["author"]

            # Scraper wins for context fields (URL, date, org) - already in merged
            # Add other parser fields to extra
            for key in ["page_count", "parsed_by", "creation_date"]:
                if key in parser_metadata:
                    merged["extra"][key] = parser_metadata[key]

        elif strategy == "parser_wins":
            # Parser overwrites all matching fields with type validation
            for key, value in parser_metadata.items():
                if value is None:
                    continue

                if key in merged:
                    # Type validation and safe coercion
                    current_val = merged[key]
                    if current_val is not None:
                        current_type = type(current_val)
                        if isinstance(value, current_type):
                            merged[key] = value
                        else:
                            # Attempt safe coercion for known numeric fields
                            if key in INT_FIELDS and isinstance(
                                value, (str, float, int)
                            ):
                                try:
                                    merged[key] = int(value)
                                    continue
                                except (ValueError, TypeError):
                                    pass

                            logger.warning(
                                f"Type mismatch for field '{key}': expected {current_type}, "
                                f"got {type(value)}. Moving to extra."
                            )
                            merged["extra"][key] = value
                    else:
                        # Field is None, check DocumentMetadata types for safety if possible
                        # For simplicity, if it's in standard fields, we accept it if it's a known field
                        merged[key] = value
                else:
                    # Add to extra if not a standard field
                    merged["extra"][key] = value

        elif strategy == "scraper_wins":
            # Only add new fields from parser, don't overwrite existing
            for key, value in parser_metadata.items():
                if value is None:
                    continue

                # Treat any standard field as a top-level field
                if key in standard_fields:
                    if merged.get(key) is None:
                        merged[key] = value
                else:
                    # Truly unknown keys go to extra
                    if key not in merged["extra"]:
                        merged["extra"][key] = value

        else:
            raise MetadataMergeError(
                f"Invalid merge strategy '{strategy}'. "
                "Must be one of: smart, parser_wins, scraper_wins"
            )

        # Return new DocumentMetadata instance
        return DocumentMetadata(**merged)


@dataclass
class ExcludedDocument:
    title: str
    url: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScraperResult:
    status: str
    scraper: str
    scraped_count: int = 0
    downloaded_count: int = 0
    uploaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    excluded_count: int = 0
    duration_seconds: float = 0.0
    documents: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
