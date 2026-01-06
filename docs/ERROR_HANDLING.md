# Error Handling Guide

## Exception Hierarchy
- `ScraperError` – base type; carries `scraper`, `recoverable`, `context`.
- `NetworkError` – network/HTTP issues (recoverable by default).
- `DownloadError` – download/write failures (recoverable unless flagged).
- `ParsingError` – HTML/JSON/feed parsing issues (non-recoverable by default).
- `ConfigurationError` – invalid/missing config.
- `StateError` – persistence/state problems.

## Retry Pattern
Use `retry_on_error` for transient failures. By default it reads `self.retry_attempts` on bound methods and uses exponential backoff.

```python
from app.utils.errors import NetworkError
from app.utils.retry import retry_on_error

@retry_on_error(exceptions=(NetworkError,))
def fetch_page(url: str) -> str:
    ...
```

Backoff: `backoff_factor ** (attempt-1)` with max attempts from `self.retry_attempts` or the explicit argument.

## BaseScraper Hooks
- `_request_with_retry(session, method, url, **kwargs)` – standard HTTP with retries, raises `NetworkError` on failure.
- `_download_file(...)` – shared download + metadata writer, retries via `retry_on_error` and returns `None` on final failure while logging.
- `run()` now captures `ScraperError` explicitly for clearer logging and status.

## Future Work
- Extend retry coverage to uploads and Selenium navigation paths.
- Add jitter to backoff for high-concurrency runs.
- Emit structured error metrics once telemetry target is chosen.
- When deployed behind a proxy, ensure forwarded headers (X-Forwarded-Proto/Host) are set and configure `TRUST_PROXY_COUNT` so Flask/ProxyFix logs accurate scheme/host for error context.
