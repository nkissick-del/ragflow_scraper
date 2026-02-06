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
    # Should use current date
    filename = generate_filename_from_template(metadata)
    from datetime import datetime

    expected_prefix = datetime.now().strftime("%Y%m")
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
