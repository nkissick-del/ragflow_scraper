from app.scrapers import ScraperRegistry


def test_registry_discovers_scrapers():
    scrapers = ScraperRegistry.list_scrapers()
    assert isinstance(scrapers, list)
    # Expect non-empty discovery with known scraper names present
    assert scrapers, "Registry should discover at least one scraper"
    names = {s["name"] for s in scrapers}
    # Common core scrapers expected in repo
    expected = {"aemo", "aemc", "aer", "eca", "ena"}
    assert expected.issubset(names)
