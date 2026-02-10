"""Unit tests for ENAScraper _parse_articles, _parse_date, _detect_total_pages."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from app.scrapers.ena_scraper import ENAScraper


@pytest.fixture
def scraper():
    with patch("app.container.get_container") as mock_gc:
        mock_container = Mock()
        mock_container.state_tracker.return_value = Mock()
        mock_gc.return_value = mock_container
        s = ENAScraper(max_pages=1, dry_run=True)
        s.state_tracker = Mock()
        s.state_tracker.is_processed.return_value = False
        yield s


# -- Minimal HTML fixtures --------------------------------------------------

ARTICLES_HTML = """
<html><body>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/reports/energy-charter-report/">
    <span class="post-title">Energy Charter Report 2024</span>
  </a>
  <span class="post-date">31 Jul 2025</span>
  <span class="post-categories">Reports</span>
</article>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/submissions/aer-submission/">
    <span class="post-title">AER Submission on Distribution</span>
  </a>
  <span class="post-date">15 Jan 2024</span>
  <span class="post-categories">Submissions</span>
</article>
</body></html>
"""

SINGLE_ARTICLE_HTML = """
<html><body>
<article class="tease tease-post">
  <a class="tease-link" href="https://www.energynetworks.com.au/resources/reports/network-report/">
    <span class="post-title">Network Vision Report</span>
  </a>
  <span class="post-date">10 December 2023</span>
  <span class="post-categories">Reports</span>
</article>
</body></html>
"""

NO_ARTICLES_HTML = """<html><body><div class="content-area"></div></body></html>"""

MISSING_LINK_HTML = """
<html><body>
<article class="tease tease-post">
  <span class="post-title">No Link Article</span>
  <span class="post-date">01 Jan 2024</span>
</article>
</body></html>
"""

PAGINATION_HTML = """
<html><body>
<div class="chr-pagination">
  <span class="page-number"><a href="/resources/reports/">1</a></span>
  <span class="page-number"><a href="/resources/reports/page/2/">2</a></span>
  <span class="page-number"><a href="/resources/reports/page/3/">3</a></span>
  <span class="page-number"><a href="/resources/reports/page/12/">12</a></span>
</div>
</body></html>
"""


# -- Tests -------------------------------------------------------------------


class TestParseArticles:
    """_parse_articles extracts article metadata from article.tease.tease-post."""

    def test_extracts_two_articles(self, scraper):
        articles = scraper._parse_articles(ARTICLES_HTML)
        assert len(articles) == 2

    def test_article_fields(self, scraper):
        articles = scraper._parse_articles(ARTICLES_HTML)
        a = articles[0]
        assert a["title"] == "Energy Charter Report 2024"
        assert "energy-charter-report" in a["url"]
        assert a["date"] == "31 Jul 2025"
        assert a["category"] == "Reports"

    def test_single_article(self, scraper):
        articles = scraper._parse_articles(SINGLE_ARTICLE_HTML)
        assert len(articles) == 1
        assert articles[0]["title"] == "Network Vision Report"

    def test_no_articles(self, scraper):
        articles = scraper._parse_articles(NO_ARTICLES_HTML)
        assert articles == []

    def test_missing_link_skipped(self, scraper):
        articles = scraper._parse_articles(MISSING_LINK_HTML)
        assert articles == []


class TestParseDateENA:
    """_parse_date handles DD Mon YYYY and DD Month YYYY formats."""

    def test_short_month(self, scraper):
        assert scraper._parse_date("31 Jul 2025") == "2025-07-31"

    def test_full_month(self, scraper):
        assert scraper._parse_date("10 December 2023") == "2023-12-10"

    def test_slash_format(self, scraper):
        assert scraper._parse_date("15/06/2024") == "2024-06-15"

    def test_empty_returns_none(self, scraper):
        assert scraper._parse_date("") is None

    def test_none_returns_none(self, scraper):
        assert scraper._parse_date(None) is None

    def test_invalid_returns_none(self, scraper):
        assert scraper._parse_date("not a date") is None


class TestDetectTotalPagesENA:
    """_detect_total_pages extracts max page from .chr-pagination."""

    def test_finds_max_page(self, scraper):
        total = scraper._detect_total_pages(PAGINATION_HTML)
        assert total == 12

    def test_no_pagination_returns_1(self, scraper):
        total = scraper._detect_total_pages(NO_ARTICLES_HTML)
        assert total == 1


class TestBuildPageURL:
    """_build_page_url constructs correct URLs."""

    def test_page_1(self, scraper):
        url = scraper._build_page_url("https://example.com/reports/", 1)
        assert url == "https://example.com/reports/"

    def test_page_2(self, scraper):
        url = scraper._build_page_url("https://example.com/reports/", 2)
        assert url == "https://example.com/reports/page/2/"
