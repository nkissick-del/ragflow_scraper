
import pytest
from pathlib import Path
from app.utils.file_utils import get_file_hash, get_content_hash

def test_get_content_hash_matches_get_file_hash(tmp_path):
    """Test that get_content_hash produces the same hash as get_file_hash."""
    content = "Hello, World! This is a test content."
    file_path = tmp_path / "test_file.txt"
    file_path.write_text(content, encoding="utf-8")

    file_hash = get_file_hash(file_path)
    content_hash = get_content_hash(content)

    assert file_hash == content_hash

def test_get_content_hash_bytes():
    """Test get_content_hash with bytes input."""
    content_str = "Hello, World!"
    content_bytes = content_str.encode("utf-8")

    hash_str = get_content_hash(content_str)
    hash_bytes = get_content_hash(content_bytes)

    assert hash_str == hash_bytes

def test_get_content_hash_algorithm():
    """Test with different algorithm."""
    content = "Test content"
    # sha1
    hash_sha1 = get_content_hash(content, algorithm="sha1")
    assert len(hash_sha1) == 40  # SHA-1 is 20 bytes = 40 hex chars
    assert hash_sha1 != get_content_hash(content, algorithm="sha256")
