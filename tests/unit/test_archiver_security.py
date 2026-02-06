
import pytest
from app.services.archiver import Archiver
from app.scrapers.models import DocumentMetadata

class TestArchiverWrapper(Archiver):
    """Wrapper to expose private method for testing without full PDF generation."""
    def get_html(self, content, meta):
        return self._synthesize_html(content, meta)

    def sanitize(self, content):
        return self._sanitize_content(content)

@pytest.fixture
def archiver():
    return TestArchiverWrapper()

def test_metadata_escaping(archiver):
    """Test that metadata fields are properly escaped."""
    payload = "<script>alert(1)</script>"
    meta = DocumentMetadata(
        filename="test",
        title=f"Title {payload}",
        url=f"http://example.com/{payload}",
        organization=f"Org {payload}",
        publication_date="2024-01-01",
        source_page="http://example.com",
        extra={"author": f"Author {payload}"}
    )

    html_output = archiver.get_html("content", meta)

    # Check that payload is NOT present in raw form
    assert payload not in html_output

    # Check that it IS present in escaped form
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_output

    # Check title specifically
    assert f"Title &lt;script&gt;alert(1)&lt;/script&gt;" in html_output

def test_content_sanitization_scripts(archiver):
    """Test that scripts are removed from content."""
    content = """
    <h1>Title</h1>
    <script>alert('xss')</script>
    <p>Text</p>
    """

    sanitized = archiver.sanitize(content)

    assert "alert('xss')" not in sanitized
    assert "<script>" not in sanitized
    assert "<h1>Title</h1>" in sanitized
    assert "<p>Text</p>" in sanitized

def test_content_sanitization_iframes(archiver):
    """Test that iframes are removed from content."""
    content = """
    <p>Before</p>
    <iframe src="javascript:alert(1)"></iframe>
    <p>After</p>
    """

    sanitized = archiver.sanitize(content)

    assert "<iframe" not in sanitized
    assert "javascript:alert(1)" not in sanitized
    assert "<p>Before</p>" in sanitized

def test_content_sanitization_attributes(archiver):
    """Test that dangerous attributes like onclick are removed."""
    content = '<a href="#" onclick="alert(1)">Click me</a>'

    sanitized = archiver.sanitize(content)

    assert "onclick" not in sanitized
    assert "alert(1)" not in sanitized
    assert '<a href="#">Click me</a>' in sanitized or '<a>Click me</a>' in sanitized

def test_content_sanitization_javascript_urls(archiver):
    """Test that javascript: URLs are removed."""
    content = '<a href="javascript:alert(1)">Click me</a>'

    sanitized = archiver.sanitize(content)

    # Depending on BeautifulSoup implementation, it might remove the attribute or the tag
    # Our implementation removes the attribute
    assert "javascript:" not in sanitized
    assert "alert(1)" not in sanitized
    # assert '<a' in sanitized # The tag should remain

def test_formatting_preservation(archiver):
    """Test that safe formatting tags are preserved."""
    content = """
    <div class="article">
        <h1>Heading</h1>
        <p>Paragraph with <b>bold</b> and <i>italic</i>.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </div>
    """

    sanitized = archiver.sanitize(content)

    assert "<h1>Heading</h1>" in sanitized
    assert "<b>bold</b>" in sanitized
    assert "<i>italic</i>" in sanitized
    assert "<li>Item 1</li>" in sanitized
