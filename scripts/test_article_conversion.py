"""
Test article conversion with trafilatura.

This script tests the new ArticleConverter implementation with:
1. Basic unit test with sample HTML
2. Integration tests with all 4 article scrapers
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.article_converter import ArticleConverter
from app.scrapers.guardian_scraper import GuardianScraper
from app.scrapers.reneweconomy_scraper import RenewEconomyScraper
from app.scrapers.theenergy_scraper import TheEnergyScraper
from app.scrapers.the_conversation_scraper import TheConversationScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_converter_basic():
    """Test basic conversion functionality with sample HTML."""
    logger.info("\n" + "=" * 60)
    logger.info("Running basic conversion test")
    logger.info("=" * 60)

    converter = ArticleConverter()

    # Test HTML with common boilerplate elements
    html = """
    <html>
        <head><title>Test Article</title></head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
            <aside class="sidebar">
                <div class="widget">Sidebar Widget</div>
                <div class="advertisement">Ad Content</div>
            </aside>
            <article>
                <h1>Main Article Title</h1>
                <p>This is the main content that should be extracted.</p>
                <p>Second paragraph with <a href="/link">a link</a>.</p>
                <table>
                    <tr><th>Column 1</th><th>Column 2</th></tr>
                    <tr><td>Data 1</td><td>Data 2</td></tr>
                </table>
            </article>
            <div class="social-share">
                <button>Share this article!</button>
                <button>Copy URL</button>
            </div>
            <div class="author-bio">
                <p>John Smith is a journalist...</p>
            </div>
            <footer>
                <p>Footer content &copy; 2025</p>
            </footer>
        </body>
    </html>
    """

    result = converter.convert(html)

    # Validate clean extraction
    checks = {
        "Main content present": "Main Article Title" in result,
        "Paragraph content present": "main content" in result,
        "Links preserved": "link" in result,
        "Table preserved": "|" in result or "Column" in result,
        "Navigation removed": "Home" not in result and "About" not in result,
        "Sidebar removed": "Sidebar Widget" not in result,
        "Ads removed": "Ad Content" not in result,
        "Social buttons removed": "Share this article" not in result and "Copy URL" not in result,
        "Author bio removed": "journalist" not in result,
        "Footer removed": "Footer content" not in result,
    }

    passed = 0
    failed = 0
    for check_name, check_result in checks.items():
        if check_result:
            logger.info(f"  ✓ {check_name}")
            passed += 1
        else:
            logger.warning(f"  ✗ {check_name}")
            failed += 1

    logger.info(f"\nBasic conversion test: {passed}/{len(checks)} checks passed")

    if failed > 0:
        logger.warning(f"\nExtracted content preview:\n{result[:500]}...")
        return False

    logger.info("✓ Basic conversion test PASSED\n")
    return True


def test_scraper_dry_run(scraper_class, name):
    """Test scraper with dry run (1 page)."""
    logger.info("\n" + "=" * 60)
    logger.info(f"Testing {name} scraper")
    logger.info("=" * 60)

    try:
        scraper = scraper_class(
            max_pages=1,
            dry_run=True,
        )

        result = scraper.scrape()

        logger.info(f"Status: {result.status}")
        logger.info(f"Scraped: {result.scraped_count}")
        logger.info(f"Downloaded: {result.downloaded_count}")
        logger.info(f"Skipped: {result.skipped_count}")
        logger.info(f"Errors: {len(result.errors)}")

        if result.errors:
            logger.warning(f"Errors encountered:")
            for error in result.errors[:3]:  # Show first 3 errors
                logger.warning(f"  - {error}")

        # Sample first document
        if result.documents:
            doc = result.documents[0]
            logger.info(f"\nSample document:")
            logger.info(f"  Title: {doc['title'][:60]}...")
            logger.info(f"  URL: {doc['url']}")
            logger.info(f"  Date: {doc.get('publication_date', 'N/A')}")

        # Success criteria
        if result.scraped_count == 0:
            logger.error(f"✗ {name} scraper test FAILED: No articles found")
            return False

        if result.status == "failed":
            logger.error(f"✗ {name} scraper test FAILED: Status is 'failed'")
            return False

        logger.info(f"✓ {name} scraper test PASSED")
        return True

    except Exception as e:
        logger.error(f"✗ {name} scraper test FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    results = {}

    # Basic unit test
    logger.info("\n" + "=" * 80)
    logger.info("ARTICLE CONVERTER MIGRATION TEST SUITE")
    logger.info("=" * 80)

    results["Basic Conversion"] = test_converter_basic()

    # Integration tests with real scrapers
    scrapers = [
        (GuardianScraper, "Guardian"),
        (RenewEconomyScraper, "RenewEconomy"),
        (TheEnergyScraper, "TheEnergy"),
        (TheConversationScraper, "TheConversation"),
    ]

    for scraper_class, name in scrapers:
        results[name] = test_scraper_dry_run(scraper_class, name)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for test_name, test_result in results.items():
        status = "✓ PASSED" if test_result else "✗ FAILED"
        logger.info(f"{test_name:25} {status}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests PASSED! Migration successful.")
        logger.info("\nNext steps:")
        logger.info("1. Install trafilatura: docker compose exec scraper pip install trafilatura>=1.12.0")
        logger.info("2. Rebuild container: docker compose build scraper")
        logger.info("3. Run full scraper tests with --max-pages 3")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) FAILED. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
