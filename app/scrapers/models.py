"""Shared scraper data models."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime
from typing import Optional, Literal, get_type_hints, Any, get_origin, get_args, Union

logger = logging.getLogger(__name__)

INT_FIELDS = {"file_size", "page_count"}


@dataclass
class DocumentMetadata:
    url: str
    title: str
    filename: str
    file_size: Optional[int] = None
    file_size_str: Optional[str] = None
    page_count: Optional[int] = None
    publication_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source_page: Optional[str] = None
    organization: Optional[str] = None
    document_type: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    image_url: Optional[str] = None
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
        if self.author:
            metadata["author"] = self.author
        if self.description:
            metadata["abstract"] = self.description
        return metadata

    def merge_parser_metadata(
        self,
        parser_metadata: dict,
        strategy: Literal["smart", "parser_wins", "scraper_wins"] = "smart",
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

            # Parser wins for author (first-class field)
            if parser_metadata.get("author"):
                merged["author"] = parser_metadata["author"]

            # Scraper wins for context fields (URL, date, org) - already in merged
            # Add other parser fields to extra, but protect top-level page_count
            for key in ["page_count", "parsed_by", "creation_date"]:
                if key in parser_metadata:
                    if key == "page_count":
                        merged["page_count"] = parser_metadata["page_count"]
                    else:
                        merged["extra"][key] = parser_metadata[key]

        elif strategy == "parser_wins":
            # Parser overwrites all matching fields with type validation
            # Cache type hints outside loop for performance
            type_hints = get_type_hints(DocumentMetadata)
            for key, value in parser_metadata.items():
                if value is None:
                    continue

                if key == "extra" and isinstance(value, dict):
                    merged["extra"].update(value)
                    continue

                if key in merged:
                    # Type validation and safe coercion
                    current_val = merged[key]
                    if current_val is not None:
                        current_type = type(current_val)
                        if isinstance(value, current_type):
                            merged[key] = value
                        else:
                            # Attempt safe coercion
                            if current_type is int and isinstance(
                                value, (str, float, int)
                            ):
                                try:
                                    value_float = float(value)
                                    if not value_float.is_integer():
                                        logger.debug(
                                            "Truncating decimal value for field '%s': %s -> %s",
                                            key,
                                            value,
                                            int(value_float),
                                        )
                                    merged[key] = int(value_float)
                                    continue
                                except (ValueError, TypeError):
                                    pass
                            elif current_type is str:
                                merged[key] = str(value)
                                continue

                            logger.warning(
                                f"Type mismatch for field '{key}': expected {current_type}, "
                                f"got {type(value)}. Moving to extra."
                            )
                            merged["extra"][key] = value
                    else:
                        # Field is None, check DocumentMetadata types for safety
                        expected_type = type_hints.get(key)

                        # Handle Optional[T] / Union[T, None]
                        origin = get_origin(expected_type)
                        if origin is Union:
                            args = get_args(expected_type)
                            # Extract the non-None type
                            expected_type = next(
                                (a for a in args if a is not type(None)), Any
                            )

                        if expected_type and expected_type is not Any:
                            # Handle generic types (e.g., list[str] -> list)
                            check_type = get_origin(expected_type) or expected_type
                            if isinstance(value, check_type):  # type: ignore[arg-type]
                                merged[key] = value
                            else:
                                # Safe coercion attempt
                                if expected_type is int and isinstance(
                                    value, (str, float)
                                ):
                                    try:
                                        merged[key] = int(float(value))
                                        continue
                                    except (ValueError, TypeError):
                                        logger.warning(
                                            f"Coercion failed for {key}: {value}. Moving to extra."
                                        )
                                elif expected_type is str:
                                    merged[key] = str(value)
                                    continue
                                else:
                                    logger.warning(
                                        f"Type mismatch for {key}: expected {expected_type}. Moving to extra."
                                    )
                                merged["extra"][key] = value
                        else:
                            merged[key] = value
                else:
                    # Add to extra if not a standard field
                    if key not in merged["extra"] and not isinstance(value, dict):
                        merged["extra"][key] = value
                    elif isinstance(value, dict):
                        merged["extra"].update(value)
                    else:
                        merged["extra"][f"parser_{key}"] = value

        elif strategy == "scraper_wins":
            # Only add new fields from parser, don't overwrite existing
            for key, value in parser_metadata.items():
                if value is None:
                    continue

                if key == "extra" and isinstance(value, dict):
                    merged["extra"].update(value)
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
                        merged["extra"][f"parser_{key}"] = value

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
