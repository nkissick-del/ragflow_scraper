# Scraper Template (minimal)

Use this as a starting point for new scrapers. Keep it small; inherit `BaseScraper`, reuse shared retry/error utilities, and add only scraper-specific logic.

```python
from __future__ import annotations

from typing import Any

from app.scrapers.base_scraper import BaseScraper, DocumentMetadata, ScraperResult
from app.utils.errors import NetworkError, ParsingError
from app.utils.retry import retry_on_error


class MyScraper(BaseScraper):
    name = "my-scraper"
    display_name = "My Scraper"
    description = "Scrapes documents from example.com"
    base_url = "https://example.com/documents"

    # Override defaults if needed
    request_delay = 1.0
    required_tags: list[str] = []
    excluded_tags: list[str] = []
    excluded_keywords: list[str] = []

    def scrape(self) -> ScraperResult:
        result = ScraperResult(status="in_progress", scraper=self.name)

        try:
            page_html = self._fetch_listing()
            documents = self.parse_page(page_html)
            result.scraped_count = len(documents)

            for doc in documents:
                if self._is_processed(doc.url):
                    result.skipped_count += 1
                    continue

                if self.dry_run:
                    result.downloaded_count += 1
                    result.documents.append(doc.to_dict())
                else:
                    downloaded = self._download_file(doc.url, doc.filename, doc)
                    if downloaded:
                        result.downloaded_count += 1
                        result.documents.append(doc.to_dict())
                        self._mark_processed(doc.url, {"title": doc.title})
                    else:
                        result.failed_count += 1

                self._polite_delay()

        except NetworkError as exc:
            result.errors.append(str(exc))
            result.status = "failed"
        except Exception as exc:
            result.errors.append(str(exc))
            result.status = "failed"

        return result

    @retry_on_error(exceptions=(NetworkError,))
    def _fetch_listing(self) -> str:
        response = self._request_with_retry(self._get_session(), "get", self.base_url, timeout=30)
        return response.text

    def _get_session(self):
        # Optional shared session creator; delete if unused
        import requests
        session = requests.Session()
        session.headers.update({"User-Agent": "MyScraper/1.0"})
        return session

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        # TODO: parse HTML and return metadata
        return []
```

Key reminders:
- Prefer `_request_with_retry` for HTTP and `_download_file` for downloads.
- Raise `NetworkError`/`ParsingError` for clearer logging; they integrate with `run()` handling.
- Honour `dry_run`, `max_pages`, and exclusion helpers from `BaseScraper`.
