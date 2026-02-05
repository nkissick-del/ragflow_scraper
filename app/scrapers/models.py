"""Shared scraper data models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


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

        # Create copy of current metadata as dict
        merged = self.to_dict()

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
            # Parser overwrites all matching fields
            for key, value in parser_metadata.items():
                if key in merged and value is not None:
                    merged[key] = value
                elif value is not None:
                    # Add to extra if not a standard field
                    merged["extra"][key] = value

        elif strategy == "scraper_wins":
            # Only add new fields from parser, don't overwrite existing
            for key, value in parser_metadata.items():
                if key not in merged or merged[key] is None:
                    if key in ["title", "organization", "document_type"]:
                        merged[key] = value
                    else:
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
