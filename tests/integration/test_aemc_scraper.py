import pytest

from app.scrapers.scraper_registry import ScraperRegistry
from tests.conftest import RUN_INTEGRATION_TESTS


@pytest.mark.integration
@pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests")
def test_aemc_scraper_dry_run_instantiation():
    scraper = ScraperRegistry.get_scraper("aemc", dry_run=True, max_pages=1)
    if scraper is None:
        pytest.skip("AEMC scraper not available")

    result = scraper.scrape()

    assert result is not None
    assert result.scraper == "aemc"
    assert isinstance(result.documents, list)
