"""Unit tests for RenewEconomyScraper parse_page and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.reneweconomy_scraper import RenewEconomyScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = RenewEconomyScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

SINGLE_POST_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/big-battery-milestone/">
    <h2>Big Battery Milestone Reached</h2>
  </a>
  <span class="post-primary-category">Storage</span>
</div>
</body></html>
"""

TWO_POSTS_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/solar-record/">
    <h3>Solar Record Set</h3>
  </a>
  <span class="post-primary-category">Solar</span>
</div>
<div class="post">
  <a href="https://reneweconomy.com.au/wind-farm-approved/">
    <h3>Wind Farm Approved</h3>
  </a>
  <span class="post-primary-category">Renewables</span>
</div>
</body></html>
"""

EMPTY_PAGE_HTML = """<html><body><div class="content"></div></body></html>"""

POST_WITH_CATEGORY_LINK_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/category/solar/">Solar</a>
  <a href="https://reneweconomy.com.au/article-about-solar-panels/">
    <h2>Solar Panels Article</h2>
  </a>
</div>
</body></html>
"""

JSONLD_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@graph": [
    {
      "@type": "Article",
      "datePublished": "2025-12-23T01:59:09+00:00",
      "dateModified": "2025-12-23T02:30:00+00:00"
    }
  ]
}
</script>
</body></html>
"""

JSONLD_SINGLE_OBJECT_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@type": "Article",
  "datePublished": "2024-06-15T10:00:00Z",
  "dateModified": "2024-06-16T08:00:00Z"
}
</script>
</body></html>
"""

JSONLD_NO_ARTICLE_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@type": "WebPage",
  "name": "RenewEconomy"
}
</script>
</body></html>
"""

PAGINATION_HTML = """
<html><body>
<div class="wp-block-query-pagination-numbers">
  <a class="page-numbers" href="/category/solar/page/2/">2</a>
  <a class="page-numbers" href="/category/solar/page/3/">3</a>
  <a class="page-numbers" href="/category/solar/page/214/">214</a>
</div>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParsePageRE:
    """parse_page extracts articles from .post elements."""

    def test_single_post(self, scraper):
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Big Battery Milestone Reached"
        assert "reneweconomy.com.au" in doc.url
        assert doc.organization == "RenewEconomy"

    def test_multiple_posts(self, scraper):
        docs = scraper.parse_page(TWO_POSTS_HTML)
        assert len(docs) == 2
        assert docs[0].title == "Solar Record Set"
        assert docs[1].title == "Wind Farm Approved"

    def test_empty_page(self, scraper):
        docs = scraper.parse_page(EMPTY_PAGE_HTML)
        assert len(docs) == 0

    def test_category_tag_extracted(self, scraper):
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert "Storage" in docs[0].tags
        assert "RenewEconomy" in docs[0].tags

    def test_filename_is_md(self, scraper):
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert docs[0].filename.endswith(".md")


class TestExtractArticleURL:
    """_extract_article_url filters out category/author/tag links."""

    def test_skips_category_link(self, scraper):
        docs = scraper.parse_page(POST_WITH_CATEGORY_LINK_HTML)
        assert len(docs) == 1
        # Should pick the article link, not the category link
        assert "/category/" not in docs[0].url
        assert "article-about-solar-panels" in docs[0].url


class TestExtractJsonLDDates:
    """_extract_jsonld_dates extracts dates from JSON-LD structured data."""

    def test_graph_array(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_HTML)
        assert dates["date_published"] == "2025-12-23"
        assert dates["date_modified"] == "2025-12-23"

    def test_single_object(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_SINGLE_OBJECT_HTML)
        assert dates["date_published"] == "2024-06-15"
        assert dates["date_modified"] == "2024-06-16"

    def test_no_article_type(self, scraper):
        dates = scraper._extract_jsonld_dates(JSONLD_NO_ARTICLE_HTML)
        assert dates["date_published"] is None
        assert dates["date_modified"] is None

    def test_no_jsonld(self, scraper):
        dates = scraper._extract_jsonld_dates(EMPTY_PAGE_HTML)
        assert dates["date_published"] is None


class TestGetMaxPagesFromHTML:
    """_get_max_pages_from_html extracts max page from pagination."""

    def test_extracts_max_page(self, scraper):
        max_pages = scraper._get_max_pages_from_html(PAGINATION_HTML)
        assert max_pages == 214

    def test_no_pagination_returns_none(self, scraper):
        max_pages = scraper._get_max_pages_from_html(EMPTY_PAGE_HTML)
        assert max_pages is None


class TestParseIsoDateRE:
    """_parse_iso_date handles ISO 8601 date strings."""

    def test_full_datetime(self, scraper):
        assert scraper._parse_iso_date("2025-12-23T01:59:09+00:00") == "2025-12-23"

    def test_with_z(self, scraper):
        assert scraper._parse_iso_date("2024-06-15T10:00:00Z") == "2024-06-15"

    def test_date_only(self, scraper):
        assert scraper._parse_iso_date("2024-01-01") == "2024-01-01"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_iso_date("") is None
