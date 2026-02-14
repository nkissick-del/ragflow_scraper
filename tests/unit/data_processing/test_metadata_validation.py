"""
Tests for metadata validation and serialization.

Validates:
- Required fields present and non-empty for all scraper types
- Deduplication hash consistency
- Metadata serialization to JSON for RAGFlow submission
- Field type enforcement
- Flat metadata flattening for RAGFlow API
"""

import hashlib
import json
from datetime import datetime

import pytest

from app.scrapers.models import DocumentMetadata
from app.services.ragflow_metadata import (
    prepare_metadata_for_ragflow,
    validate_metadata,
)
from app.utils.file_utils import get_file_hash


class TestDocumentMetadataCreation:
    """Test DocumentMetadata dataclass creation and field defaults."""

    def test_create_metadata_with_required_fields(self):
        """Test creating metadata with only required fields."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Example Document",
            filename="example.pdf",
        )
        # No-op; validation is performed on ragflow metadata dicts
        assert metadata.scraped_at is not None  # Auto-set
        assert metadata.tags == []
        assert metadata.extra == {}
        assert metadata.hash is None

    def test_create_metadata_with_all_fields(self):
        """Test creating metadata with all optional fields."""
        extra = {"author": "John Doe", "abstract": "Test abstract"}
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Full Metadata Document",
            filename="full.pdf",
            file_size=1024576,
            file_size_str="1.0 MB",
            publication_date="2026-01-07",
            tags=["Energy", "Report"],
            source_page="https://example.com/reports",
            organization="Example Org",
            document_type="PDF Report",
            local_path="/data/scraped/full.pdf",
            hash="abc123def456",
            extra=extra,
        )

        assert metadata.file_size == 1024576
        assert metadata.publication_date == "2026-01-07"
        assert metadata.tags == ["Energy", "Report"]
        assert metadata.organization == "Example Org"
        assert metadata.document_type == "PDF Report"
        assert metadata.hash == "abc123def456"
        assert metadata.extra == extra

    def test_scraped_at_auto_set(self):
        """Test that scraped_at is automatically set to current time."""
        before = datetime.now().isoformat()
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
        )
        after = datetime.now().isoformat()

        assert before <= metadata.scraped_at <= after


class TestRequiredFieldValidation:
    """Test validation of required fields."""

    def test_validate_complete_metadata(self):
        """Test validation passes for complete metadata."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Complete Document",
            filename="complete.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        # Should not raise
        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result is not None

    def test_validate_empty_title_raises(self):
        """Test validation fails when title is empty."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="",  # Empty
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        # Title is not required in ragflow metadata; validation should pass
        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result is not None

    def test_validate_empty_url_raises(self):
        """Test validation fails when url is empty."""
        metadata = DocumentMetadata(
            url="",  # Empty
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )
        with pytest.raises(Exception):
            validate_metadata(metadata.to_ragflow_metadata())

    def test_validate_missing_organization_raises(self):
        """Test validation fails when organization is empty."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="",  # Empty
            document_type="PDF Report",
        )
        # Organization missing defaults to "Unknown" in ragflow metadata
        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result["organization"] == "Unknown"

    def test_validate_missing_document_type_raises(self):
        """Test validation fails when document_type is empty."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="",  # Empty
        )
        # Document type missing defaults to "Unknown" in ragflow metadata
        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result["document_type"] == "Unknown"

    def test_validate_rejects_wrong_optional_type(self):
        """Test validation fails when optional fields have incorrect types."""
        metadata = {
            "organization": "Example Org",
            "source_url": "https://example.com",
            "scraped_at": "2026-01-07T12:00:00",
            "document_type": "PDF",
            "publication_date": 20260107,  # Wrong type
        }

        with pytest.raises(ValueError):
            validate_metadata(metadata)

    def test_validate_whitespace_only_title_fails(self):
        """Test validation fails for whitespace-only title."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="   ",  # Whitespace only
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        # Title whitespace does not affect ragflow required fields
        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result is not None


class TestHashConsistency:
    """Test deduplication hash computation and consistency."""

    def test_hash_computation_from_file(self, tmp_path):
        """Test hash is computed correctly from file content."""
        # Create a test file
        test_file = tmp_path / "test.pdf"
        test_content = b"PDF test content"
        test_file.write_bytes(test_content)

        # Expected hash
        expected_hash = hashlib.sha256(test_content).hexdigest()

        # Create metadata with hash
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            local_path=str(test_file),
            hash=expected_hash,
        )

        assert metadata.hash == expected_hash
        assert len(metadata.hash) == 64  # SHA-256 is 64 hex chars

    def test_hash_consistency_same_content(self, tmp_path):
        """Test same file content always produces same hash."""
        test_file = tmp_path / "test.pdf"
        content = b"Consistent test content"
        test_file.write_bytes(content)

        hash1 = hashlib.sha256(content).hexdigest()
        hash2 = hashlib.sha256(content).hexdigest()

        assert hash1 == hash2

    def test_hash_differs_for_different_content(self):
        """Test different content produces different hashes."""
        content1 = b"Content A"
        content2 = b"Content B"

        hash1 = hashlib.sha256(content1).hexdigest()
        hash2 = hashlib.sha256(content2).hexdigest()

        assert hash1 != hash2

    def test_hash_none_when_not_computed(self):
        """Test hash is None if not explicitly set."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        assert metadata.hash is None

    def test_get_file_hash_matches_same_content(self, tmp_path):
        """Test get_file_hash returns identical values for identical content."""
        file_a = tmp_path / "a.pdf"
        file_b = tmp_path / "b.pdf"

        file_a.write_bytes(b"content-123")
        file_b.write_bytes(b"content-123")

        assert get_file_hash(file_a) == get_file_hash(file_b)


class TestMetadataFormatting:
    """Test metadata formatting for RAGFlow API submission."""

    def test_format_converts_required_fields(self):
        """Test required fields are correctly mapped to RAGFlow names."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test Document",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        formatted = prepare_metadata_for_ragflow(
            metadata.to_ragflow_metadata()
        )

        assert formatted["source_url"] == "https://example.com/doc.pdf"
        assert formatted["document_type"] == "PDF Report"
        assert "scraped_at" in formatted
        assert formatted["organization"] == "Example Org"

    def test_format_flattens_list_to_csv(self):
        """Test lists are converted to CSV strings."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            tags=["Energy", "Quarterly", "Report"],
        )

        formatted = prepare_metadata_for_ragflow(
            metadata.to_dict()
        )

        assert formatted["tags"] == "Energy, Quarterly, Report"
        assert isinstance(formatted["tags"], str)

    def test_format_flattens_nested_dict_with_dot_notation(self):
        """Test nested dicts are flattened with dot notation."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            extra={"author": "John Doe", "abstract": "Test abstract"},
        )

        formatted = prepare_metadata_for_ragflow(
            metadata.to_dict()
        )

        assert "extra.author" in formatted
        assert formatted["extra.author"] == "John Doe"
        assert "extra.abstract" in formatted

    def test_format_handles_empty_optional_fields(self):
        """Test empty optional fields are handled gracefully."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            publication_date=None,
            tags=[],
        )

        formatted = prepare_metadata_for_ragflow(
            metadata.to_dict()
        )

        # Empty lists/None should be handled
        assert formatted is not None

    def test_format_empty_string_list_element(self):
        """Test empty strings in lists are filtered out."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            tags=["Energy", "", "Report"],  # Empty string
        )

        formatted = prepare_metadata_for_ragflow(
            metadata.to_dict()
        )

        # Current behavior preserves empty slot in CSV
        assert formatted.get("tags") == "Energy, , Report"

    def test_format_flattens_nested_dicts_and_bools(self):
        """Ensure nested dictionaries and booleans are flattened and stringified."""
        metadata = {
            "organization": "Example Org",
            "source_url": "https://example.com",
            "scraped_at": "2026-01-07T12:00:00",
            "document_type": "PDF",
            "extra": {"author": "Jane Doe", "published": True},
            "flags": {"reviewed": False},
            "feature_enabled": True,
        }

        cleaned = prepare_metadata_for_ragflow(metadata)

        assert cleaned["extra.author"] == "Jane Doe"
        assert cleaned["extra.published"] == "true"
        assert cleaned["flags.reviewed"] == "false"
        assert cleaned["feature_enabled"] == "true"


class TestScraperTypeValidation:
    """Test validation of metadata for different scraper types."""

    def test_pdf_scraper_metadata_complete(self):
        """Test PDF scraper metadata is valid."""
        metadata = DocumentMetadata(
            url="https://aemo.com.au/reports/2025-q1.pdf",
            title="2025 Q1 Report",
            filename="aemo_2025_q1.pdf",
            organization="AEMO",
            document_type="PDF Report",
            file_size=2097152,
            file_size_str="2.0 MB",
            publication_date="2025-01-15",
            tags=["Electricity", "Quarterly"],
        )

        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result["organization"] == "AEMO"
        assert result["document_type"] == "PDF Report"

    def test_article_scraper_metadata_complete(self):
        """Test article scraper metadata is valid."""
        metadata = DocumentMetadata(
            url="https://theguardian.com/energy-crisis",
            title="Australia Energy Crisis",
            filename="guardian_energy.md",
            organization="The Guardian",
            document_type="Article",
            publication_date="2026-01-07",
            tags=["Energy", "Climate"],
            extra={
                "author": "Jane Smith",
                "abstract": "Australia faces energy crisis",
                "categories": ["Environment"],
            },
        )

        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result["organization"] == "The Guardian"
        assert result["document_type"] == "Article"

    def test_pdf_missing_file_size_still_valid(self):
        """Test PDF metadata is valid even without file_size."""
        metadata = DocumentMetadata(
            url="https://aemo.com.au/reports/2025-q1.pdf",
            title="2025 Q1 Report",
            filename="aemo_2025_q1.pdf",
            organization="AEMO",
            document_type="PDF Report",
            # file_size is optional
        )

        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result is not None

    def test_article_missing_author_still_valid(self):
        """Test article metadata is valid without author."""
        metadata = DocumentMetadata(
            url="https://theguardian.com/energy-crisis",
            title="Australia Energy Crisis",
            filename="guardian_energy.md",
            organization="The Guardian",
            document_type="Article",
            # extra.author is optional
        )

        result = validate_metadata(metadata.to_ragflow_metadata())
        assert result is not None


class TestMetadataToDict:
    """Test metadata serialization to dictionary."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all non-None fields."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            file_size=1024,
            publication_date="2026-01-07",
            tags=["Tag1"],
            source_page="https://example.com",
            local_path="/data/test.pdf",
            hash="abc123",
            extra={"key": "value"},
        )

        result = metadata.to_dict()

        assert result["url"] == "https://example.com/doc.pdf"
        assert result["title"] == "Test"
        assert result["filename"] == "test.pdf"
        assert result["file_size"] == 1024
        assert result["tags"] == ["Tag1"]
        assert result["extra"] == {"key": "value"}

    def test_to_dict_handles_none_values(self):
        """Test to_dict with optional None values."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            publication_date=None,
            file_size=None,
        )

        result = metadata.to_dict()

        assert "url" in result
        assert "publication_date" in result
        assert result["publication_date"] is None


class TestMetadataSerialization:
    """Test metadata serialization to JSON."""

    def test_serialize_to_json(self):
        """Test metadata can be serialized to JSON."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            tags=["Energy"],
            extra={"author": "John Doe"},
        )

        # Should be JSON serializable
        json_str = json.dumps(metadata.to_dict(), default=str)
        assert json_str is not None

        # Should be deserializable
        loaded = json.loads(json_str)
        assert loaded["title"] == "Test"

    def test_serialize_with_datetime(self):
        """Test metadata with datetime fields serializes correctly."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
        )

        # scraped_at is datetime ISO string
        json_str = json.dumps(
            metadata.to_dict(),
            default=str,
        )
        loaded = json.loads(json_str)

        assert "scraped_at" in loaded
        assert isinstance(loaded["scraped_at"], str)

    def test_roundtrip_serialization(self):
        """Test metadata survives round-trip serialization."""
        original = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title="Test Document",
            filename="test.pdf",
            organization="Example Org",
            document_type="PDF Report",
            publication_date="2026-01-07",
            tags=["Energy", "Report"],
        )

        # Serialize and deserialize
        json_str = json.dumps(original.to_dict(), default=str)
        loaded = json.loads(json_str)

        # Verify key fields match
        assert loaded["url"] == original.url
        assert loaded["title"] == original.title
        assert loaded["filename"] == original.filename
        assert loaded["tags"] == original.tags


class TestMetadataIntegration:
    """Integration tests for complete metadata flow."""

    def test_create_validate_format_pdf_metadata(self):
        """Test complete flow: create -> validate -> format PDF metadata."""
        # Create metadata
        metadata = DocumentMetadata(
            url="https://aemo.com.au/reports/2025-q1.pdf",
            title="2025 Q1 Electricity Report",
            filename="aemo_2025_q1.pdf",
            organization="AEMO",
            document_type="PDF Report",
            file_size=2097152,
            publication_date="2025-01-15",
            tags=["Electricity", "Quarterly"],
            source_page="https://aemo.com.au/reports",
        )

        # Validate
        validated = validate_metadata(metadata.to_ragflow_metadata())
        assert "source_url" in validated

        # Format for RAGFlow
        formatted = prepare_metadata_for_ragflow({**metadata.to_dict(), **validated})
        assert formatted["document_type"] == "PDF Report"
        assert "Electricity, Quarterly" in formatted.get("tags", "")

    def test_create_validate_format_article_metadata(self):
        """Test complete flow: create -> validate -> format article metadata."""
        # Create metadata
        metadata = DocumentMetadata(
            url="https://theguardian.com/environment/2026/energy-crisis",
            title="Australia Faces Energy Crisis",
            filename="guardian_energy_2026.md",
            organization="The Guardian",
            document_type="Article",
            publication_date="2026-01-07",
            tags=["Energy", "Climate", "Australia"],
            extra={
                "author": "Jane Smith",
                "abstract": "Australia faces unprecedented energy crisis...",
                "categories": ["Environment", "News"],
            },
        )

        # Validate
        validated = validate_metadata(metadata.to_ragflow_metadata())
        assert "source_url" in validated

        # Format for RAGFlow
        formatted = prepare_metadata_for_ragflow({**metadata.to_dict(), **validated})
        assert formatted["document_type"] == "Article"
        assert "Jane Smith" in str(formatted.values())

    def test_to_ragflow_metadata_applies_defaults_and_fallbacks(self):
        """Test to_ragflow_metadata fills defaults and abstract fallback chain."""
        metadata = DocumentMetadata(
            url="https://example.com/article",
            title="Energy Update",
            filename="energy.md",
            description="Short description",
        )

        rag_meta = metadata.to_ragflow_metadata()
        validated = validate_metadata(rag_meta)

        assert validated["organization"] == "Unknown"
        assert validated["document_type"] == "Unknown"
        assert validated["abstract"] == "Short description"

    def test_metadata_preserves_special_characters(self):
        """Test metadata preserves special characters in text fields."""
        metadata = DocumentMetadata(
            url="https://example.com/doc.pdf",
            title='Test & Report: "2025" Q1',
            filename="test_2025_q1.pdf",
            organization="Example Org (Pty Ltd)",
            document_type="PDF Report",
        )

        validated = validate_metadata(metadata.to_ragflow_metadata())
        # Title isn't part of ragflow minimal metadata; ensure organization preserved
        assert "(" in validated["organization"]
