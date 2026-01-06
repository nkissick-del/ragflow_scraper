"""
RAGFlow metadata preparation utilities.

Handles conversion of document metadata to RAGFlow-compatible format.
"""

from __future__ import annotations

from typing import Any, Iterable

REQUIRED_FIELDS = {
    "organization": str,
    "source_url": str,
    "scraped_at": str,
    "document_type": str,
}

OPTIONAL_FIELDS = {
    "publication_date": str,
    "author": str,
    "abstract": str,
}


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate required and optional fields and ensure types are simple."""
    for field, expected_type in REQUIRED_FIELDS.items():
        value = metadata.get(field)
        if value is None or not isinstance(value, expected_type) or not str(value).strip():
            raise ValueError(f"Metadata missing or invalid required field: {field}")

    cleaned: dict[str, Any] = {}
    # Copy required
    for field in REQUIRED_FIELDS:
        cleaned[field] = metadata[field]

    # Optional if present and correct type
    for field, expected_type in OPTIONAL_FIELDS.items():
        value = metadata.get(field)
        if value is not None:
            if not isinstance(value, expected_type):
                raise ValueError(f"Metadata field {field} must be {expected_type.__name__}")
            if str(value).strip():
                cleaned[field] = value

    # Include any additional flat extras (simple scalars or iterables)
    for key, value in metadata.items():
        if key in cleaned:
            continue
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        elif isinstance(value, Iterable) and not isinstance(value, (dict, str)):
            cleaned[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                cleaned[f"{key}.{nested_key}"] = str(nested_value)
        else:
            cleaned[key] = str(value)

    return cleaned


def prepare_metadata_for_ragflow(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Convert metadata to RAGFlow-compatible format.

    RAGFlow requirements:
    - Flat JSON (no nested objects)
    - String or number values only
    - No None values

    Args:
        metadata: Raw metadata dictionary

    Returns:
        Cleaned metadata ready for RAGFlow API
    """
    cleaned = {}

    for key, value in metadata.items():
        if value is None:
            continue
        elif isinstance(value, (list, tuple)):
            # Convert lists to comma-separated strings
            cleaned[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            # Convert booleans to strings
            cleaned[key] = str(value).lower()
        elif isinstance(value, (str, int, float)):
            # Keep as-is
            cleaned[key] = value
        elif isinstance(value, dict):
            # Flatten nested dicts with dot notation
            for nested_key, nested_value in value.items():
                cleaned[f"{key}.{nested_key}"] = str(nested_value)
        else:
            # Convert everything else to string
            cleaned[key] = str(value)

    return cleaned
