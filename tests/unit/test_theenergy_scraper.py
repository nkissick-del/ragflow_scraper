"""Unit tests for TheEnergyScraper parse_page and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.theenergy_scraper import TheEnergyScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = TheEnergyScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

LISTING_HTML = """
<html><body>
<main>
  <article>
    <a href="/article/energy-policy-update">
      <h3>Energy Policy Update</h3>
    </a>
    <div class="metadata">
      <span>Policy</span>
      <span>news</span>
      <span class="date">24 Dec 2025</span>
    </div>
    <div class="abstract">Summary of the energy policy changes.</div>
  </article>
  <article>
    <a href="https://theenergy.co/article/grid-battery-project">
      <h3>Grid Battery Project Announced</h3>
    </a>
    <div class="metadata">
      <span>Projects</span>
      <span>feature</span>
      <span class="date">20 Dec 2025</span>
    </div>
    <div class="abstract">New battery project for grid stability.</div>
  </article>
</main>
</body></html>
"""

SINGLE_ARTICLE_HTML = """
<html><body>
<main>
  <article>
    <a href="/article/hydrogen-hub">
      <h3>Hydrogen Hub Launch</h3>
    </a>
    <div class="metadata">
      <span>Technology</span>
      <span>explainer</span>
    </div>
  </article>
</main>
</body></html>
"""

NO_MAIN_HTML = """<html><body><div class="content">No main element.</div></body></html>"""

EMPTY_MAIN_HTML = """<html><body><main></main></body></html>"""

ARTICLE_NO_TITLE_HTML = """
<html><body>
<main>
  <article>
    <a href="/article/no-title"></a>
    <div class="metadata"><span>Policy</span></div>
  </article>
</main>
</body></html>
"""

JSONLD_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@type": "Article",
  "datePublished": "2025-12-24T07:30:00+11:00",
  "dateCreated": "2025-12-24T12:04:37+11:00",
  "dateModified": "2025-12-24T12:39:08+11:00"
}
</script>
</body></html>
"""

JSONLD_GRAPH_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@graph": [
    {
      "@type": "WebPage",
      "name": "TheEnergy"
    },
    {
      "@type": "Article",
      "datePublished": "2024-01-15T09:00:00+00:00"
    }
  ]
}
</script>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParsePage:
    """parse_page extracts articles from <article> within <main>."""

    def test_extracts_two_articles(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        assert len(docs) == 2

    def test_first_article_fields(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        doc = docs[0]
        assert doc.title == "Energy Policy Update"
        assert doc.url == "https://theenergy.co/article/energy-policy-update"
        assert doc.organization == "The Energy"
        assert doc.document_type == "Article"

    def test_second_article_absolute_url(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        assert docs[1].url == "https://theenergy.co/article/grid-battery-project"

    def test_no_main_returns_empty(self, scraper):
        docs = scraper.parse_page(NO_MAIN_HTML)
        assert docs == []

    def test_empty_main_returns_empty(self, scraper):
        docs = scraper.parse_page(EMPTY_MAIN_HTML)
        assert docs == []


class TestParseArticleItem:
    """_parse_article_item extracts metadata from an article element."""

    def test_extracts_category(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        assert docs[0].extra["category"] == "Policy"

    def test_extracts_article_type(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        assert docs[0].extra["article_type"] == "news"

    def test_extracts_abstract(self, scraper):
        docs = scraper.parse_page(LISTING_HTML)
        assert docs[0].extra["abstract"] == "Summary of the energy policy changes."

    def test_tags_include_category_and_type(self, scraper):
        docs = scraper.parse_page(SINGLE_ARTICLE_HTML)
        assert "TheEnergy" in docs[0].tags
        assert "Technology" in docs[0].tags
        assert "explainer" in docs[0].tags

    def test_article_without_title_skipped(self, scraper):
        docs = scraper.parse_page(ARTICLE_NO_TITLE_HTML)
        assert docs == []


class TestExtractJsonLDDatesTE:
    """_extract_jsonld_dates extracts dates from JSON-LD."""

    def test_single_object(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_HTML)
        assert dates["date_published"] == "2025-12-24"
        assert dates["date_created"] == "2025-12-24"
        assert dates["date_modified"] == "2025-12-24"

    def test_graph_array(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_GRAPH_HTML)
        assert dates["date_published"] == "2024-01-15"

    def test_no_jsonld(self, scraper):
        dates = scraper._extract_jsonld_dates(NO_MAIN_HTML)
        assert dates["date_published"] is None
        assert dates["date_created"] is None
        assert dates["date_modified"] is None


class TestParseIsoDateTE:
    """_parse_iso_date handles various ISO 8601 formats."""

    def test_with_timezone_offset(self, scraper):
        assert scraper._parse_iso_date("2025-12-24T07:30:00+11:00") == "2025-12-24"

    def test_with_utc_z(self, scraper):
        assert scraper._parse_iso_date("2024-06-15T10:00:00Z") == "2024-06-15"

    def test_date_only(self, scraper):
        assert scraper._parse_iso_date("2024-01-01") == "2024-01-01"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_iso_date("") is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_iso_date("not-a-date") is None


class TestBuildPageURL:
    """_build_page_url constructs correct URLs."""

    def test_page_1(self, scraper):
        url = scraper._build_page_url(1)
        assert url == "https://theenergy.co/articles"

    def test_page_2(self, scraper):
        url = scraper._build_page_url(2)
        assert url == "https://theenergy.co/articles/p2"

    def test_page_34(self, scraper):
        url = scraper._build_page_url(34)
        assert url == "https://theenergy.co/articles/p34"
