from app.orchestrator.scheduler import Scheduler
from app.scrapers import ScraperRegistry


class DummyScraperResult:
    def __init__(self):
        self.scraped_count = 1
        self.downloaded_count = 1
        self.errors = []
        self.status = "completed"


class DummyScraper:
    def __init__(self, counter):
        self.counter = counter

    def run(self):
        self.counter["runs"] += 1
        return DummyScraperResult()


def test_scheduler_run_now_triggers_scraper(monkeypatch):
    counter = {"runs": 0}

    monkeypatch.setattr(
        ScraperRegistry,
        "get_scraper",
        lambda name: DummyScraper(counter),
    )

    scheduler = Scheduler()
    thread = scheduler.run_now("dummy")
    thread.join(timeout=2)

    assert counter["runs"] == 1
