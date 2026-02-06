from datetime import datetime
from unittest.mock import patch
import pytest
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
        # Expose fromisoformat and other methods from real datetime
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime

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


@pytest.mark.parametrize(
    "metadata,expected_in_filename",
    [
        ({"filename": "doc.pdf"}, ["UNKNOWN", "doc"]),
        (
            {"organization": None, "title": None, "filename": "doc.pdf"},
            ["UNKNOWN", "doc"],
        ),
        ({}, ["UNKNOWN", "unnamed"]),
    ],
)
def test_generate_filename_missing_fields(metadata, expected_in_filename):
    """Test filename generation when organization or title is missing."""
    fixed_date = datetime(2025, 2, 6)
    with patch("app.utils.file_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_date
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime

        filename = generate_filename_from_template(metadata)
        for expected in expected_in_filename:
            assert expected in filename


def test_generate_filename_without_extension():
    """Test filename generation when the original filename has no extension."""
    fixed_date = datetime(2025, 2, 6)
    metadata = {"organization": "NASA", "title": "Mission", "filename": "mars"}

    with patch("app.utils.file_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_date
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime

        filename = generate_filename_from_template(metadata)
        assert filename.endswith("NASA_mission")


def test_generate_filename_long_inputs():
    """Test filename generation with very long title and organization."""
    fixed_date = datetime(2025, 2, 6)
    long_str = "A" * 300
    metadata = {"organization": long_str, "title": long_str, "filename": "test.pdf"}

    with patch("app.utils.file_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_date
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime

        filename = generate_filename_from_template(metadata)
        assert len(filename) <= 200


def test_generate_filename_special_characters_in_org():
    """Test filename generation when organization contains special characters."""
    fixed_date = datetime(2025, 2, 6)
    metadata = {"organization": "NASA/JPL", "title": "Mars", "filename": "test.pdf"}

    with patch("app.utils.file_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_date
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime

        filename = generate_filename_from_template(metadata)
        assert "NASA_JPL" in filename
        assert "/" not in filename
