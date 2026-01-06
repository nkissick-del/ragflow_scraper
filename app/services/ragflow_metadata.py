"""
RAGFlow metadata preparation utilities.

Handles conversion of document metadata to RAGFlow-compatible format.
"""

from __future__ import annotations

from typing import Any


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
