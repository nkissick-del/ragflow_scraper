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


# -- Additional HTML fixtures for new tests ---------------------------------

PAGINATION_NO_LINKS_HTML = """
<html><body>
<div class="wp-block-query-pagination-numbers">
</div>
</body></html>
"""

PAGINATION_DOTS_HTML = """
<html><body>
<div class="wp-block-query-pagination-numbers">
  <a class="page-numbers" href="/page/2/">2</a>
  <a class="page-numbers" href="/page/3/">...</a>
</div>
</body></html>
"""

POST_MISSING_TITLE_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/article-without-heading/">
    <span>Not a heading element</span>
  </a>
</div>
</body></html>
"""

POST_MISSING_URL_HTML = """
<html><body>
<div class="post">
  <h2>Orphan Title No Link</h2>
</div>
</body></html>
"""

POST_MISSING_CATEGORY_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/no-category-article/">
    <h3>No Category Article</h3>
  </a>
</div>
</body></html>
"""

POST_WITH_AUTHOR_TAG_LINK_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/author/john-doe/">John Doe</a>
  <a href="https://reneweconomy.com.au/tag/solar/">Solar</a>
  <a href="https://reneweconomy.com.au/real-article-link/">
    <h2>Real Article</h2>
  </a>
</div>
</body></html>
"""

POST_WITH_RELATIVE_URL_HTML = """
<html><body>
<div class="post">
  <a href="/some-relative-article/">
    <h2>Relative URL Article</h2>
  </a>
</div>
</body></html>
"""

POST_WITH_HASH_LINK_HTML = """
<html><body>
<div class="post">
  <a href="#">Skip</a>
  <a href="https://reneweconomy.com.au/actual-article/">
    <h2>Actual Article</h2>
  </a>
</div>
</body></html>
"""

ARTICLE_HTML_CONTENT = """
<html><body>
<article>
  <h1>Test Article Title</h1>
  <p>This is the first paragraph of the article content.</p>
  <p>This is the second paragraph with more details.</p>
</article>
</body></html>
"""

ARTICLE_HTML_EMPTY_BODY = """
<html><body>
<article></article>
</body></html>
"""

ARTICLE_HTML_NO_ARTICLE = """
<html><body>
<div class="sidebar">Navigation content only</div>
</body></html>
"""


# -- New Test Classes -------------------------------------------------------


class TestGetMaxPagesFromHtmlExtended:
    """Extended tests for _get_max_pages_from_html."""

    def test_no_pagination_container_returns_none(self, scraper):
        """Page with no .wp-block-query-pagination-numbers returns None."""
        result = scraper._get_max_pages_from_html(EMPTY_PAGE_HTML)
        assert result is None

    def test_pagination_container_no_links_returns_none(self, scraper):
        """Pagination container exists but has no page-numbers links."""
        result = scraper._get_max_pages_from_html(PAGINATION_NO_LINKS_HTML)
        assert result is None

    def test_pagination_with_number(self, scraper):
        """Standard pagination with numeric page links."""
        result = scraper._get_max_pages_from_html(PAGINATION_HTML)
        assert result == 214

    def test_pagination_with_dots_returns_none(self, scraper):
        """Last link is '...' which cannot be parsed as int."""
        result = scraper._get_max_pages_from_html(PAGINATION_DOTS_HTML)
        assert result is None


class TestExtractArticleUrlExtended:
    """Extended tests for _extract_article_url."""

    def test_valid_url_extracted(self, scraper):
        """Extracts the article URL from a post with valid link."""
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert len(docs) == 1
        assert "big-battery-milestone" in docs[0].url

    def test_skips_category_urls(self, scraper):
        """Category URLs are filtered out."""
        docs = scraper.parse_page(POST_WITH_CATEGORY_LINK_HTML)
        assert len(docs) == 1
        assert "/category/" not in docs[0].url

    def test_skips_author_urls(self, scraper):
        """Author URLs are filtered out, article URL is found."""
        docs = scraper.parse_page(POST_WITH_AUTHOR_TAG_LINK_HTML)
        assert len(docs) == 1
        assert "/author/" not in docs[0].url
        assert "real-article-link" in docs[0].url

    def test_skips_tag_urls(self, scraper):
        """Tag URLs are filtered out."""
        docs = scraper.parse_page(POST_WITH_AUTHOR_TAG_LINK_HTML)
        assert "/tag/" not in docs[0].url

    def test_relative_url_resolved(self, scraper):
        """Relative URLs are resolved to absolute using base_url."""
        docs = scraper.parse_page(POST_WITH_RELATIVE_URL_HTML)
        assert len(docs) == 1
        assert docs[0].url.startswith("https://reneweconomy.com.au")
        assert "some-relative-article" in docs[0].url

    def test_none_when_no_valid_href(self, scraper):
        """Returns no docs when no valid article URL is found."""
        docs = scraper.parse_page(POST_MISSING_URL_HTML)
        assert len(docs) == 0

    def test_skips_hash_link(self, scraper):
        """Hash-only links are skipped."""
        docs = scraper.parse_page(POST_WITH_HASH_LINK_HTML)
        assert len(docs) == 1
        assert docs[0].url != "#"
        assert "actual-article" in docs[0].url


class TestParsePostItemExtended:
    """Extended tests for _parse_post_item via parse_page."""

    def test_full_item(self, scraper):
        """Full post with title, URL, and category."""
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Big Battery Milestone Reached"
        assert doc.organization == "RenewEconomy"
        assert doc.document_type == "Article"
        assert "Storage" in doc.tags

    def test_missing_title_skipped(self, scraper):
        """Post without a heading element is skipped."""
        docs = scraper.parse_page(POST_MISSING_TITLE_HTML)
        assert len(docs) == 0

    def test_missing_url_skipped(self, scraper):
        """Post without a valid URL is skipped."""
        docs = scraper.parse_page(POST_MISSING_URL_HTML)
        assert len(docs) == 0

    def test_missing_category(self, scraper):
        """Post without category still creates doc with RenewEconomy tag."""
        docs = scraper.parse_page(POST_MISSING_CATEGORY_HTML)
        assert len(docs) == 1
        assert "RenewEconomy" in docs[0].tags


class TestExtractArticleContentRE:
    """Tests for _extract_article_content."""

    def test_normal_html_extraction(self, scraper):
        """Extracts content from a standard article HTML page."""
        content = scraper._extract_article_content(ARTICLE_HTML_CONTENT)
        assert isinstance(content, str)

    def test_empty_body_returns_string(self, scraper):
        """Empty article body returns an empty or minimal string."""
        content = scraper._extract_article_content(ARTICLE_HTML_EMPTY_BODY)
        assert isinstance(content, str)

    def test_no_article_element(self, scraper):
        """Page without article element still returns a string."""
        content = scraper._extract_article_content(ARTICLE_HTML_NO_ARTICLE)
        assert isinstance(content, str)


class TestScrapeHomepageFallback:
    """Tests for _scrape_homepage_fallback method existence and basic invocation."""

    def test_method_exists(self, scraper):
        """Scraper has _scrape_homepage_fallback method."""
        assert hasattr(scraper, "_scrape_homepage_fallback")
        assert callable(scraper._scrape_homepage_fallback)

    def test_build_homepage_url_page_1(self, scraper):
        """Homepage URL for page 1 is base URL."""
        url = scraper._build_homepage_url(1)
        assert url == "https://reneweconomy.com.au/"

    def test_build_homepage_url_page_2(self, scraper):
        """Homepage URL for page 2 includes /page/2/."""
        url = scraper._build_homepage_url(2)
        assert url == "https://reneweconomy.com.au/page/2/"

    def test_build_category_url_page_1(self, scraper):
        """Category URL for page 1 has no /page/ suffix."""
        url = scraper._build_category_url("solar", 1)
        assert url == "https://reneweconomy.com.au/category/solar/"

    def test_build_category_url_page_3(self, scraper):
        """Category URL for page 3 includes /page/3/."""
        url = scraper._build_category_url("storage/battery", 3)
        assert url == "https://reneweconomy.com.au/category/storage/battery/page/3/"


# -- Additional HTML fixtures for scrape_category tests ---------------------

PAGINATION_SINGLE_NUMBER_HTML = """
<html><body>
<div class="wp-block-query-pagination-numbers">
  <a class="page-numbers" href="/category/solar/page/2/">2</a>
  <a class="page-numbers" href="/category/solar/page/5/">5</a>
</div>
</body></html>
"""

CATEGORY_PAGE_WITH_POSTS_HTML = """
<html><body>
<div class="post">
  <a href="https://reneweconomy.com.au/already-seen-article/">
    <h3>Already Seen Article</h3>
  </a>
  <span class="post-primary-category">Solar</span>
</div>
<div class="post">
  <a href="https://reneweconomy.com.au/new-article/">
    <h3>New Article</h3>
  </a>
  <span class="post-primary-category">Solar</span>
</div>
</body></html>
"""

POST_WITH_NO_HREF_HTML = """
<html><body>
<div class="post">
  <a>
    <h2>Link Without Href</h2>
  </a>
</div>
</body></html>
"""


# -- Scrape Category Tests --------------------------------------------------


class TestGetMaxPagesFromHtmlNew:
    """Additional coverage for _get_max_pages_from_html edge cases."""

    def test_no_pagination_returns_none(self, scraper):
        """Page without pagination container returns None."""
        result = scraper._get_max_pages_from_html("<html><body><p>Hello</p></body></html>")
        assert result is None

    def test_pagination_with_numeric_last_link(self, scraper):
        """Extracts the last numeric page link value."""
        result = scraper._get_max_pages_from_html(PAGINATION_SINGLE_NUMBER_HTML)
        assert result == 5

    def test_pagination_with_ellipsis_returns_none(self, scraper):
        """Last link text '...' is not numeric, returns None."""
        html = """
        <html><body>
        <div class="wp-block-query-pagination-numbers">
          <a class="page-numbers" href="/page/2/">2</a>
          <a class="page-numbers" href="/page/3/">…</a>
        </div>
        </body></html>
        """
        result = scraper._get_max_pages_from_html(html)
        assert result is None


class TestExtractArticleUrlNew:
    """Additional coverage for _extract_article_url via parse_page."""

    def test_valid_url_found(self, scraper):
        """Extracts a valid reneweconomy.com.au URL."""
        from bs4 import BeautifulSoup

        html = '<div class="post"><a href="https://reneweconomy.com.au/test-article/">link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        post = soup.select_one(".post")
        url = scraper._extract_article_url(post)
        assert url == "https://reneweconomy.com.au/test-article/"

    def test_skip_category_url(self, scraper):
        """Category URLs are filtered out."""
        from bs4 import BeautifulSoup

        html = '<div class="post"><a href="https://reneweconomy.com.au/category/solar/">Solar</a></div>'
        soup = BeautifulSoup(html, "lxml")
        post = soup.select_one(".post")
        url = scraper._extract_article_url(post)
        assert url is None

    def test_skip_author_url(self, scraper):
        """Author URLs are filtered out."""
        from bs4 import BeautifulSoup

        html = '<div class="post"><a href="https://reneweconomy.com.au/author/jane/">Jane</a></div>'
        soup = BeautifulSoup(html, "lxml")
        post = soup.select_one(".post")
        url = scraper._extract_article_url(post)
        assert url is None

    def test_skip_tag_url(self, scraper):
        """Tag URLs are filtered out."""
        from bs4 import BeautifulSoup

        html = '<div class="post"><a href="https://reneweconomy.com.au/tag/wind/">Wind</a></div>'
        soup = BeautifulSoup(html, "lxml")
        post = soup.select_one(".post")
        url = scraper._extract_article_url(post)
        assert url is None

    def test_missing_href_returns_none(self, scraper):
        """Post element with no valid href returns None."""
        docs = scraper.parse_page(POST_WITH_NO_HREF_HTML)
        assert len(docs) == 0


class TestParsePostItemNew:
    """Additional coverage for _parse_post_item via parse_page."""

    def test_full_item_all_fields(self, scraper):
        """Full post returns DocumentMetadata with all expected fields."""
        docs = scraper.parse_page(SINGLE_POST_HTML)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "Big Battery Milestone Reached"
        assert doc.url == "https://reneweconomy.com.au/big-battery-milestone/"
        assert doc.organization == "RenewEconomy"
        assert doc.document_type == "Article"

    def test_missing_title_returns_none(self, scraper):
        """Post with no heading element is skipped."""
        docs = scraper.parse_page(POST_MISSING_TITLE_HTML)
        assert len(docs) == 0

    def test_missing_url_returns_none(self, scraper):
        """Post with no valid link is skipped."""
        docs = scraper.parse_page(POST_MISSING_URL_HTML)
        assert len(docs) == 0

    def test_missing_category_defaults_to_reneweconomy_tag(self, scraper):
        """Post without category still has RenewEconomy tag."""
        docs = scraper.parse_page(POST_MISSING_CATEGORY_HTML)
        assert len(docs) == 1
        assert "RenewEconomy" in docs[0].tags
        # No category tag added
        assert len(docs[0].tags) == 1


class TestExtractArticleContentNew:
    """Additional tests for _extract_article_content."""

    def test_normal_html_returns_string(self, scraper):
        """Standard HTML page returns a string."""
        content = scraper._extract_article_content(ARTICLE_HTML_CONTENT)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_empty_body_returns_empty_string(self, scraper):
        """Empty article body returns an empty or minimal string."""
        content = scraper._extract_article_content(ARTICLE_HTML_EMPTY_BODY)
        assert isinstance(content, str)

    def test_no_article_element_returns_string(self, scraper):
        """Page without article element returns a string (possibly empty)."""
        content = scraper._extract_article_content(ARTICLE_HTML_NO_ARTICLE)
        assert isinstance(content, str)


class TestScrapeCategoryBehavior:
    """Tests for _scrape_category behavior."""

    def test_empty_page_stops_early(self, scraper):
        """Category with no articles on the page triggers pagination guard."""
        from unittest.mock import MagicMock, PropertyMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")

        # Mock FlareSolverr to return a page with no posts
        mock_fs_result = MagicMock()
        mock_fs_result.success = True
        mock_fs_result.html = EMPTY_PAGE_HTML
        mock_fs_result.url = "https://reneweconomy.com.au/category/solar/"
        scraper.fetch_rendered_page_full = MagicMock(return_value=mock_fs_result)
        scraper._polite_delay = MagicMock()

        scraper._scrape_category("solar", result)
        # With empty pages, pagination guard should eventually stop
        assert result.downloaded_count == 0

    def test_all_articles_already_processed_skips(self, scraper):
        """Articles already in session_processed_urls are skipped."""
        from unittest.mock import MagicMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")

        # Pre-populate session URLs
        scraper._session_processed_urls.add("https://reneweconomy.com.au/already-seen-article/")
        scraper._session_processed_urls.add("https://reneweconomy.com.au/new-article/")

        # Return page with known articles, then empty to stop
        mock_fs_result_page1 = MagicMock()
        mock_fs_result_page1.success = True
        mock_fs_result_page1.html = CATEGORY_PAGE_WITH_POSTS_HTML
        mock_fs_result_page1.url = "https://reneweconomy.com.au/category/solar/"

        mock_fs_result_page2 = MagicMock()
        mock_fs_result_page2.success = True
        mock_fs_result_page2.html = EMPTY_PAGE_HTML
        mock_fs_result_page2.url = "https://reneweconomy.com.au/category/solar/page/2/"

        scraper.fetch_rendered_page_full = MagicMock(
            side_effect=[mock_fs_result_page1, mock_fs_result_page2]
        )
        scraper._polite_delay = MagicMock()
        scraper._process_article = MagicMock()

        scraper._scrape_category("solar", result)
        # _process_article should not have been called for already-seen articles
        scraper._process_article.assert_not_called()

    def test_cancellation_stops_scrape(self, scraper):
        """check_cancelled returning True breaks the loop."""
        from unittest.mock import MagicMock
        from app.scrapers.models import ScraperResult

        result = ScraperResult(status="in_progress", scraper="reneweconomy")

        # Set cancelled immediately
        scraper.check_cancelled = MagicMock(return_value=True)
        scraper.fetch_rendered_page_full = MagicMock()

        scraper._scrape_category("solar", result)
        # Should not have fetched any pages
        scraper.fetch_rendered_page_full.assert_not_called()
