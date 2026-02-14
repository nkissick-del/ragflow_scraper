"""Tests for TheEnergy scraper tag extraction."""

from unittest.mock import patch, MagicMock

from app.scrapers.models import DocumentMetadata


class TestTheEnergyTagExtraction:
    """Test tag extraction from TheEnergy article pages."""

    def _make_scraper(self):
        """Create a TheEnergyScraper with mocked container."""
        mock_container = MagicMock()
        mock_container.state_tracker.return_value = MagicMock()

        with patch("app.container.get_container", return_value=mock_container):
            from app.scrapers.theenergy_scraper import TheEnergyScraper
            scraper = TheEnergyScraper(dry_run=True)
        return scraper

    def test_extract_tags_from_article(self):
        """Tags should be extracted from /tags/ links and added to metadata."""
        scraper = self._make_scraper()

        html = """
        <html><body>
        <article>
            <h1>Test Article</h1>
            <div class="flex flex-wrap gap-1">
                <a href="https://theenergy.co/tags/decommissioning">Decommissioning</a>
                <a href="https://theenergy.co/tags/gas">Gas</a>
                <a href="https://theenergy.co/tags/regulation">Regulation</a>
            </div>
            <p>Article content here.</p>
        </article>
        </body></html>
        """

        metadata = DocumentMetadata(
            url="https://theenergy.co/article/test",
            title="Test Article",
            filename="test.html",
            tags=["TheEnergy"],
        )

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        scraper._extract_and_remove_tags(soup, metadata)

        assert "Decommissioning" in metadata.tags
        assert "Gas" in metadata.tags
        assert "Regulation" in metadata.tags
        assert "TheEnergy" in metadata.tags
        assert len(metadata.tags) == 4

    def test_extract_tags_deduped(self):
        """Tags already in metadata should not be duplicated."""
        scraper = self._make_scraper()

        html = """
        <html><body>
        <div>
            <a href="/tags/gas">Gas</a>
            <a href="/tags/energy">Energy</a>
        </div>
        </body></html>
        """

        metadata = DocumentMetadata(
            url="https://theenergy.co/article/test",
            title="Test",
            filename="test.html",
            tags=["TheEnergy", "Gas"],  # Gas already present
        )

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        scraper._extract_and_remove_tags(soup, metadata)

        # Gas should not be duplicated
        gas_count = sum(1 for t in metadata.tags if t.lower() == "gas")
        assert gas_count == 1
        assert "Energy" in metadata.tags

    def test_tag_container_removed_from_html(self):
        """The parent container of tag links should be removed from HTML."""
        scraper = self._make_scraper()

        html = """
        <html><body>
        <article>
            <h1>Title</h1>
            <div class="flex flex-wrap gap-1">
                <a href="/tags/decommissioning">Decommissioning</a>
            </div>
            <p>Keep this content.</p>
        </article>
        </body></html>
        """

        metadata = DocumentMetadata(
            url="https://theenergy.co/article/test",
            title="Title",
            filename="test.html",
            tags=["TheEnergy"],
        )

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        scraper._extract_and_remove_tags(soup, metadata)

        result = str(soup)
        # Tag link container should be gone
        assert "/tags/decommissioning" not in result
        # Article content should remain
        assert "Keep this content." in result

    def test_extract_article_html_with_metadata(self):
        """_extract_article_html with metadata should extract tags."""
        scraper = self._make_scraper()

        html = """
        <html><body>
        <article>
            <h1>Title</h1>
            <div>
                <a href="/tags/solar">Solar</a>
            </div>
            <p>Body text.</p>
        </article>
        </body></html>
        """

        metadata = DocumentMetadata(
            url="https://theenergy.co/article/test",
            title="Title",
            filename="test.html",
            tags=["TheEnergy"],
        )

        content = scraper._extract_article_html(html, metadata)
        assert "Solar" in metadata.tags
        assert "Body text." in content

    def test_extract_article_html_without_metadata(self):
        """_extract_article_html without metadata should work as before."""
        scraper = self._make_scraper()

        html = """
        <html><body>
        <article>
            <h1>Title</h1>
            <p>Body text.</p>
        </article>
        </body></html>
        """

        content = scraper._extract_article_html(html)
        assert "Body text." in content
