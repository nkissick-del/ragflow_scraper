import pytest

from app.scrapers.scraper_registry import ScraperRegistry
from app.scrapers.base_scraper import BaseScraper


@pytest.mark.unit
@pytest.mark.usefixtures("reset_registry")
def test_discover_registers_expected_scrapers():
    scrapers = ScraperRegistry.discover()
    names = set(scrapers.keys())
    expected = {
        "aemc",
        "aemo",
        "aer",
        "eca",
        "ena",
        "guardian",
        "reneweconomy",
        "the-conversation",
        "theenergy",
    }

    assert expected.issubset(names)
    assert all(issubclass(cls, BaseScraper) for cls in scrapers.values())


@pytest.mark.unit
@pytest.mark.usefixtures("reset_registry")
def test_get_scraper_returns_instance():
    ScraperRegistry.discover()
    scraper_name = ScraperRegistry.get_scraper_names()[0]

    scraper = ScraperRegistry.get_scraper(scraper_name, dry_run=True, max_pages=1)

    assert scraper is not None
    assert isinstance(scraper, BaseScraper)


@pytest.mark.unit
@pytest.mark.usefixtures("reset_registry")
def test_get_nonexistent_scraper_returns_none():
    ScraperRegistry.discover()
    scraper = ScraperRegistry.get_scraper("nonexistent-scraper")
    assert scraper is None


@pytest.mark.unit
@pytest.mark.usefixtures("reset_registry")
def test_list_scrapers_returns_metadata():
    metadata_list = ScraperRegistry.list_scrapers()

    assert isinstance(metadata_list, list)
    assert metadata_list
    first = metadata_list[0]
    for key in ("name", "display_name", "description"):
        assert key in first


@pytest.mark.unit
@pytest.mark.parametrize("scraper_name", ScraperRegistry.get_scraper_names())
def test_scraper_instantiation(scraper_name):
    scraper = ScraperRegistry.get_scraper(scraper_name, dry_run=True, max_pages=1)
    assert scraper is not None
    assert isinstance(scraper, BaseScraper)
