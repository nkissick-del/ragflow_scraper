import hashlib
import tempfile
import pytest
from pathlib import Path
from app.utils.file_utils import get_file_hash, get_content_hash

def test_get_file_hash():
    content = b"test content"
    expected_hash = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        path = Path(f.name)

    try:
        assert get_file_hash(path) == expected_hash
    finally:
        if path.exists():
            path.unlink()

def test_get_content_hash_bytes():
    content = b"test content"
    expected_hash = hashlib.sha256(content).hexdigest()
    assert get_content_hash(content) == expected_hash

def test_get_content_hash_string():
    content = "test content"
    # String "test content" encoded to utf-8 is b"test content"
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert get_content_hash(content) == expected_hash

def test_consistency():
    content_str = "consistency check"
    content_bytes = content_str.encode("utf-8")

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content_bytes)
        path = Path(f.name)

    try:
        file_hash = get_file_hash(path)
        content_hash_bytes = get_content_hash(content_bytes)
        content_hash_str = get_content_hash(content_str)

        assert file_hash == content_hash_bytes
        assert file_hash == content_hash_str
    finally:
        if path.exists():
            path.unlink()
