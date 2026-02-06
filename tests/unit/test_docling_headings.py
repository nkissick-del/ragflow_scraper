from app.backends.parsers.docling_parser import DoclingParser


def test_docling_parser_heading_extraction():
    parser = DoclingParser()

    # Test case 1: Standard heading
    markdown = "# Standard Title\nSome content"
    meta = parser._extract_metadata({}, 1, markdown)
    assert meta["title"] == "Standard Title"

    # Test case 2: Nested heading (the case lstrip would fail on)
    markdown = "# ## Nested Header\nSome content"
    meta = parser._extract_metadata({}, 1, markdown)
    assert meta["title"] == "## Nested Header"

    # Test case 3: Secondary heading
    markdown = "## Secondary Title\nSome content"
    meta = parser._extract_metadata({}, 1, markdown)
    assert meta["title"] == "Secondary Title"

    # Test case 4: Leading whitespace
    markdown = "   # Spaced Title\nSome content"
    meta = parser._extract_metadata({}, 1, markdown)
    assert meta["title"] == "Spaced Title"
