from datetime import datetime
from unittest.mock import patch
from app.utils.file_utils import generate_filename_from_template, slugify, shorten


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("Major Report (2024)") == "major-report-2024"
    assert slugify("  Extra   Spaces  ") == "extra-spaces"
    assert slugify("Unicode: ñ á é") == "unicode-n-a-e"
    assert slugify("") == ""
    assert slugify(None) == ""


def test_shorten():
    assert shorten("This is a long title that should be shortened", 10) == "This is a"
    assert shorten("Short", 10) == "Short"
    assert shorten("", 10) == ""
    assert shorten(None, 10) == ""

    # Edge cases for shorten
    # Exact length
    assert shorten("0123456789", 10) == "0123456789"
    # Long numeric string (no word boundaries)
    assert shorten("123456789012345", 10) == "1234567890"
    # Multi-word string truncating inside a word (it actually truncates exactly and then strips)
    # The current implementation is value[:length].strip()
    # "A multiword string" (length 18)
    # shorten("A multiword string", 10) -> "A multiwor"
    assert shorten("A multiword string", 10) == "A multiwor"
    # shorten("A multiword string", 11) -> "A multiword"
    assert shorten("A multiword string", 11) == "A multiword"


def test_generate_filename_default():
    metadata = {
        "publication_date": "2024-07-15",
        "organization": "AEMO",
        "title": "Annual Report",
        "filename": "report.pdf",
    }
    # Default: {{ date_prefix }}_{{ org }}_{{ title | slugify }}{{ extension }}
    # 202407_AEMO_annual-report.pdf
    filename = generate_filename_from_template(metadata)
    assert filename == "202407_AEMO_annual-report.pdf"


def test_generate_filename_custom_template():
    metadata = {
        "publication_date": "2024-07-15",
        "organization": "AEMO",
        "title": "Annual Report",
        "filename": "report.pdf",
    }
    template = "{{ year }}/{{ org }}/{{ title | slugify }}{{ extension }}"
    filename = generate_filename_from_template(metadata, template=template)
    # Note: sanitize_filename will replace / with _
    assert filename == "2024_AEMO_annual-report.pdf"


def test_generate_filename_with_filters():
    metadata = {
        "publication_date": "2024-07-15",
        "organization": "AEMO",
        "title": "A Very Long Title That Needs Shortening",
        "filename": "document.pdf",
    }
    template = "{{ org }}_{{ title | shorten(10) | slugify }}{{ extension }}"
    filename = generate_filename_from_template(metadata, template=template)
    # shorten(10) -> "A Very Lon"
    # slugify -> "a-very-lon"
    assert filename == "AEMO_a-very-lon.pdf"


def test_generate_filename_missing_date():
    metadata = {"organization": "NASA", "title": "Mars Mission", "filename": "mars.pdf"}
    fixed_date = datetime(2025, 1, 1)

    with patch("app.utils.file_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_date
        # We also need to mock fromisoformat if it's called, but here it's not
        # since publication_date is missing.

        # Should use fixed_date
        filename = generate_filename_from_template(metadata)

        expected_prefix = fixed_date.strftime("%Y%m")
        assert filename.startswith(expected_prefix)
        assert "NASA" in filename
        assert "mars-mission" in filename


def test_generate_filename_invalid_template():
    metadata = {
        "publication_date": "2024-07-15",
        "organization": "AEMO",
        "title": "Annual Report",
        "filename": "report.pdf",
    }
    # Invalid syntax: missing closing brace
    invalid_template = "{{ title "
    filename = generate_filename_from_template(metadata, template=invalid_template)
    # Should fallback to default: 202407_AEMO_Annual Report.pdf (sanitized)
    assert filename == "202407_AEMO_Annual_Report.pdf"


def test_generate_filename_metadata_object():
    class MockMetadata:
        def to_dict(self):
            return {
                "publication_date": "2024-07-15",
                "organization": "AEMO",
                "title": "Class Report",
                "filename": "class.pdf",
            }

    filename = generate_filename_from_template(MockMetadata())
    assert filename == "202407_AEMO_class-report.pdf"


def test_secure_filename_filter():
    metadata = {"title": "Dangerous/Path..Traversal", "filename": "test.pdf"}
    template = "{{ title | secure_filename }}{{ extension }}"
    filename = generate_filename_from_template(metadata, template=template)
    assert "/" not in filename
    assert ".." not in filename
    # Assert exact sanitized filename
    # "Dangerous/Path..Traversal" -> "Dangerous_Path_Traversal" (from sanitize_filename)
    assert filename == "Dangerous_Path_Traversal.pdf"


def test_generate_filename_edge_cases():
    # Missing/None organization and title
    metadata = {"filename": "doc.pdf"}
    filename = generate_filename_from_template(metadata)
    assert "UNKNOWN" in filename
    assert "doc" in filename  # title defaults to original_name

    metadata = {"organization": None, "title": None, "filename": "doc.pdf"}
    filename = generate_filename_from_template(metadata)
    assert "UNKNOWN" in filename
    assert "doc" in filename

    # Filenames without extensions
    metadata = {"organization": "NASA", "title": "Mission", "filename": "mars"}
    filename = generate_filename_from_template(metadata)
    assert filename.endswith("NASA_mission")

    # Empty metadata dict
    filename = generate_filename_from_template({})
    assert "UNKNOWN" in filename
    assert "unnamed" in filename

    # Very long title/organization
    long_str = "A" * 300
    metadata = {"organization": long_str, "title": long_str, "filename": "test.pdf"}
    filename = generate_filename_from_template(metadata)
    assert len(filename) <= 200

    # Organization names with special characters
    metadata = {"organization": "NASA/JPL", "title": "Mars", "filename": "test.pdf"}
    filename = generate_filename_from_template(metadata)
    assert "NASA_JPL" in filename
    assert "/" not in filename
