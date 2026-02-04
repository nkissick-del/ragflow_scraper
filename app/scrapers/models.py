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
    paperless_id: Optional[int] = None
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
