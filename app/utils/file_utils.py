"""
File utility functions for the PDF Scraper application.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Protocol, runtime_checkable

from jinja2 import Environment, BaseLoader

logger = logging.getLogger(__name__)


@runtime_checkable
class MetadataProtocol(Protocol):
    """Protocol for metadata objects."""

    def to_dict(self) -> dict[str, Any]: ...


# Shared Jinja2 Environment for filename generation
JINJA_ENV = Environment(loader=BaseLoader())


def _set_context_date_from_dt(context: dict[str, str], dt: datetime) -> None:
    """Helper to set date fields in context from a datetime object."""
    context["date_prefix"] = dt.strftime("%Y%m")
    context["year"] = dt.strftime("%Y")
    context["month"] = dt.strftime("%m")
    context["day"] = dt.strftime("%d")


# Standard chunk size for file I/O operations (64KB)
CHUNK_SIZE = 65536


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize a filename by removing/replacing invalid characters.

    Args:
        filename: Original filename
        max_length: Maximum length for the filename

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Normalize unicode characters
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    # Replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)  # Control characters

    # Prevent directory traversal
    filename = filename.replace("..", "__")

    # Replace multiple spaces/underscores with single
    filename = re.sub(r"[\s_]+", "_", filename)

    # Remove leading/trailing dots, spaces, underscores
    filename = filename.strip(". _")

    # Truncate if too long (preserve extension)
    if len(filename) > max_length:
        name_part, ext = split_filename(filename)
        available = max_length - len(ext) - 1 if ext else max_length
        filename = f"{name_part[:available]}.{ext}" if ext else name_part[:available]

    return filename or "unnamed"


def split_filename(filename: str) -> tuple[str, str]:
    """
    Split a filename into name and extension.

    Args:
        filename: Filename to split

    Returns:
        Tuple of (name, extension) without the dot
    """
    path = Path(filename)
    ext = path.suffix.lstrip(".")
    name = path.stem
    return name, ext


def ensure_dir(path: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The path that was ensured to exist
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate the hash of a file.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hex digest of the file hash
    """
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def get_content_hash(content: str | bytes, algorithm: str = "sha256") -> str:
    """
    Calculate the hash of content (string or bytes).

    Args:
        content: Content to hash (string or bytes)
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hex digest of the content hash
    """
    hash_obj = hashlib.new(algorithm)
    if isinstance(content, str):
        content = content.encode("utf-8")
    hash_obj.update(content)
    return hash_obj.hexdigest()


def get_unique_filepath(base_path: Path, filename: str) -> Path:
    """
    Get a unique filepath by appending a number if file already exists.

    Args:
        base_path: Directory path
        filename: Desired filename

    Returns:
        Path that doesn't exist yet
    """
    filepath = base_path / filename
    if not filepath.exists():
        return filepath

    name, ext = split_filename(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}.{ext}" if ext else f"{name}_{counter}"
        filepath = base_path / new_filename
        if not filepath.exists():
            return filepath
        counter += 1


def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    value = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def parse_file_size(size_str: str) -> Optional[int]:
    """
    Parse a human-readable file size string to bytes.

    Args:
        size_str: Size string (e.g., "1.5 MB", "500KB")

    Returns:
        Size in bytes, or None if parsing fails
    """
    size_str = size_str.strip().upper()
    match = re.match(r"^([\d.]+)\s*(B|KB|MB|GB|TB|PB)?$", size_str)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2) or "B"

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "PB": 1024**5,
    }

    return int(value * multipliers.get(unit, 1))


def slugify(value: str) -> str:
    """
    Convert a string to a filesystem-safe slug.
    Example: "Hello World!" -> "hello-world"
    """
    if not value:
        return ""
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def shorten(value: str, length: int = 50) -> str:
    """Truncate string to maximum length."""
    if not isinstance(length, int):
        raise ValueError(
            f"shorten() length must be an integer, got {type(length).__name__}"
        )

    length = max(1, length)

    if not value or len(value) <= length:
        return value or ""
    return value[:length].strip()


def generate_filename_from_template(
    metadata: MetadataProtocol | dict[str, Any],
    template: Optional[str] = None,
) -> str:
    """
    Generate filename from Jinja2 template using metadata.

    Args:
        metadata: DocumentMetadata instance or dict
        template: Jinja2 template string (defaults to Config.FILENAME_TEMPLATE)

    Returns:
        Sanitized filename generated from template

    Available template variables:
        - date_prefix: YYYYMM from publication_date
        - year: YYYY from publication_date
        - month: MM from publication_date
        - day: DD from publication_date
        - org: Uppercase organization name
        - title: Document title
        - original_name: Original filename without extension
        - extension: File extension (with dot)

    Available filters:
        - slugify: Convert to filesystem-safe slug
        - shorten(n): Truncate to length n
        - secure_filename: Sanitize filename

    Examples:
        >>> meta = DocumentMetadata(title="Annual Report", organization="AEMO", ...)
        >>> generate_filename_from_template(meta)
        '202407_AEMO_annual-report.pdf'

        >>> generate_filename_from_template(
        ...     meta,
        ...     template="{{ year }}/{{ org }}/{{ title | slugify }}{{ extension }}"
        ... )
        '2024/AEMO/annual-report.pdf'
    """
    if template is None:
        from app.config import Config

        template = Config.FILENAME_TEMPLATE

    # Convert metadata to dict if needed
    if isinstance(metadata, MetadataProtocol):
        meta_dict = metadata.to_dict()
    elif isinstance(metadata, dict):
        meta_dict = metadata
    else:
        meta_dict = metadata  # Fallback for unexpected types

    # Build template context
    context = {}

    # Parse publication date
    pub_date = meta_dict.get("publication_date")
    if pub_date:
        try:
            dt = datetime.fromisoformat(pub_date.split("T")[0])
            _set_context_date_from_dt(context, dt)
        except (ValueError, AttributeError):
            _set_context_date_from_dt(context, datetime.now(timezone.utc))
            logger.warning(f"Could not parse date '{pub_date}', using current date")
    else:
        _set_context_date_from_dt(context, datetime.now(timezone.utc))

    # Organization
    context["org"] = (meta_dict.get("organization") or "Unknown").upper()

    # Original filename info
    filename = meta_dict.get("filename") or "unnamed"
    original_path = Path(filename)
    context["original_name"] = original_path.stem
    context["extension"] = original_path.suffix

    # Title
    context["title"] = meta_dict.get("title") or context["original_name"]

    # Configure filters on the cached environment
    JINJA_ENV.filters["slugify"] = slugify
    JINJA_ENV.filters["shorten"] = shorten
    JINJA_ENV.filters["secure_filename"] = sanitize_filename

    try:
        tmpl = JINJA_ENV.from_string(template)
        rendered = tmpl.render(**context)
    except Exception as e:
        logger.error(
            f"Jinja2 template rendering failed ({e.__class__.__name__}): {e}",
            exc_info=True,
        )
        # Default fallback format
        rendered = f"{context['date_prefix']}_{context['org']}_{context['title']}{context['extension']}"

    # Sanitize the final result
    return sanitize_filename(rendered)


def generate_standardized_filename(
    original_path: Path,
    publication_date: Optional[str],
    organization: str,
    extension: Optional[str] = None,
) -> str:
    """
    Generate standardized filename: YYYYMM_Org_OriginalName.ext

    DEPRECATED: Use generate_filename_from_template() for more flexibility.

    Args:
        original_path: Path to original file
        publication_date: ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        organization: Organization name/abbreviation
        extension: File extension (if None, use original extension from path)

    Returns:
        Formatted filename like "202407_AEMO_original-document-name.pdf"

    Examples:
        >>> from pathlib import Path
        >>> generate_standardized_filename(
        ...     Path("report.pdf"),
        ...     "2024-07-15",
        ...     "AEMO"
        ... )
        '202407_AEMO_report.pdf'
    """
    warnings.warn(
        "generate_standardized_filename is deprecated; use generate_filename_from_template()",
        DeprecationWarning,
        stacklevel=2,
    )
    original_name = original_path.stem

    # Parse publication date to YYYYMM format
    if publication_date:
        try:
            # Handle ISO format dates (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            pub_date = datetime.fromisoformat(publication_date.split("T")[0])
            date_prefix = pub_date.strftime("%Y%m")
        except (ValueError, AttributeError):
            # Fallback if date parsing fails
            date_prefix = datetime.now(timezone.utc).strftime("%Y%m")
            logger.warning(
                f"Could not parse date '{publication_date}', using current date"
            )
    else:
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m")
        logger.warning(f"No publication_date for {original_name}, using current date")

    # Get organization abbreviation (uppercase)
    org = organization.upper()

    # Sanitize original filename (remove problematic characters but preserve hyphens)
    safe_original = sanitize_filename(original_name)

    # Use original extension if not specified
    if extension is None:
        extension = original_path.suffix

    # Combine components
    new_filename = f"{date_prefix}_{org}_{safe_original}{extension}"

    return new_filename
