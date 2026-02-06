import pytest
from app.backends.parsers.docling_parser import DoclingParser

# Page number to extract metadata from
PAGE_NUMBER = 1


@pytest.mark.parametrize(
    "markdown,expected_title,test_id",
    [
        ("# Standard Title\nSome content", "Standard Title", "standard"),
        ("# ## Nested Header\nSome content", "## Nested Header", "nested"),
        ("## Secondary Title\nSome content", "Secondary Title", "secondary"),
        ("   # Spaced Title\nSome content", "Spaced Title", "leading_whitespace"),
    ],
)
def test_docling_heading_extraction(markdown, expected_title, test_id):
    """Test that DoclingParser correctly extracts headings from various markdown formats."""
    parser = DoclingParser()
    meta = parser._extract_metadata({}, PAGE_NUMBER, markdown)
    assert meta["title"] == expected_title


@pytest.mark.parametrize(
    "markdown,expected_title,test_id",
    [
        ("Plain text with no heading\nJust content", "", "no_heading"),
        ("", "", "empty_markdown"),
        ("# \nContent after empty heading", "", "heading_no_text"),
        ("# First\n## Second\nContent", "First", "multiple_headings"),
    ],
)
def test_docling_heading_edge_cases(markdown, expected_title, test_id):
    """Test edge cases for heading extraction: no heading, empty markdown, empty heading text, and multiple headings."""
    parser = DoclingParser()
    meta = parser._extract_metadata({}, PAGE_NUMBER, markdown)
    # Verify title is either empty or not present
    assert meta.get("title", "") == expected_title
