# Error Handling & Logging Guide

This guide covers exception handling patterns, retry strategies, and logging standards for consistent error diagnosis across the scraper system.

---

## Table of Contents

1. [Exception Hierarchy](#exception-hierarchy)
2. [Retry Patterns](#retry-patterns)
3. [Logging Standards](#logging-standards)
4. [Log Levels](#log-levels)
5. [Structured Logging](#structured-logging)
6. [Log Rotation & Retention](#log-rotation--retention)
7. [Common Errors & Troubleshooting](#common-errors--troubleshooting)

---

## Exception Hierarchy

Custom exceptions provide context and recovery hints:

- **`ScraperError`** – Base type; carries `scraper`, `recoverable`, `context`
- **`NetworkError`** – Network/HTTP issues (recoverable by default)
- **`DownloadError`** – Download/write failures (recoverable unless flagged)
- **`ParsingError`** – HTML/JSON/feed parsing issues (non-recoverable by default)
- **`ConfigurationError`** – Invalid/missing config (non-recoverable)
- **`StateError`** – Persistence/state problems (non-recoverable)
- **`ScraperAlreadyRunningError`** – Duplicate scraper execution attempt (non-recoverable)

**Usage:**

```python
from app.utils.errors import NetworkError, ParsingError

# Recoverable error with context
raise NetworkError(
    "Failed to fetch page",
    scraper="aemo",
    recoverable=True,
    context={"url": url, "attempt": 3}
)

# Non-recoverable parsing error
raise ParsingError(
    "Missing required title element",
    scraper="aemo",
    recoverable=False,
    context={"selector": ".document-title"}
)
```

---

## Retry Patterns

### Using retry_on_error Decorator

For transient failures, use the `retry_on_error` decorator with exponential backoff:

```python
from app.utils.errors import NetworkError
from app.utils.retry import retry_on_error

@retry_on_error(exceptions=(NetworkError,))
def fetch_page(url: str) -> str:
    response = requests.get(url, timeout=30)
    if response.status_code >= 500:
        raise NetworkError(f"Server error: {response.status_code}")
    return response.text
```

**Backoff formula:** `backoff_factor ** (attempt-1)`  
**Max attempts:** Read from `self.retry_attempts` or specified explicitly

### BaseScraper Retry Methods

- **`_request_with_retry(session, method, url, **kwargs)`** – HTTP requests with retries, raises `NetworkError` on final failure
- **`_download_file(...)`** – Download + metadata writer with retries, returns `None` on failure after logging
- **`run()`** – Captures `ScraperError` for clean logging and status reporting

---

## Logging Standards

### Quick Reference

| Level | When to Use | Frequency | Example |
| ------ | ----------- | --------- | ------- |
| **DEBUG** | Diagnostic details | Rare in prod | Function parameters, iteration counts |
| **INFO** | Normal milestones | 5-20/run | Downloads, processing complete |
| **WARNING** | Recoverable issues | 1-5/run | Missing optional data, timeouts with fallback |
| **ERROR** | Recoverable failures | 1-3/doc | Download failed, will retry |
| **CRITICAL** | Unrecoverable errors | 0-1/run | Config missing, service unreachable |

---

## Log Levels

### DEBUG

**Use when:** Detailed diagnostic information for troubleshooting specific issues  
**Audience:** Developers debugging a failing scraper  
**Frequency:** Rarely in production (disabled by default via `LOG_LEVEL=INFO`)

```python
self.logger.debug(f"Parsing HTML: {len(html)} bytes, encoding={charset}")
self.logger.debug(f"Retrying request (attempt {attempt}/{max_attempts}, backoff={delay}s)")
```

**When to use:**

- Function entry/exit with parameters
- Loop iterations over large datasets
- Conditional branch selection logic
- Raw HTTP request/response data
- Regex matches and parsing steps

### INFO

**Use when:** Normal operation milestones that operators should see  
**Audience:** Operators monitoring scraper runs in production  
**Frequency:** 5–20 log lines per scraper run

```python
self.logger.info(f"Downloaded: {filename} ({file_size_str})")
self.logger.info(f"Processed 25 documents from {source_url}")
self.logger.info(f"RAGFlow metadata push completed: 25 docs")
```

**When to use:**

- Scraper start/stop
- Documents downloaded, skipped, or failed
- Major milestone completions
- External service connections
- Run statistics

### WARNING

**Use when:** Unexpected condition that scraper can recover from  
**Audience:** Operators scanning logs for issues  
**Frequency:** 1–5 per run (should be rare)

```python
self.logger.warning(f"Document missing author metadata: {title}")
self.logger.warning(f"FlareSolverr timed out (60s), falling back to direct request")
```

**When to use:**

- Missing optional metadata (recovered with default)
- Retries triggered (will continue)
- Service timeouts with fallback
- Data validation warnings
- Rate limiting (will backoff and retry)

### ERROR

**Use when:** Recoverable error; operation failed but scraper continues  
**Audience:** Operators assessing scraper health  
**Frequency:** 1–3 per failed document

```python
self.logger.error(f"Failed to download {url}: HTTP 403", exc_info=True)
self.logger.error(f"Document validation failed: missing required field 'title'")
```

**When to use:**

- Document download failed (will retry or skip)
- Required metadata missing (document skipped)
- API call failed (will retry)
- Parsing error on single document
- State corruption (will reset and continue)

### CRITICAL

**Use when:** Unrecoverable error; scraper must stop  
**Audience:** Operators; triggers alerts  
**Frequency:** 0–1 per run (should be exceptional)

```python
self.logger.critical(f"Configuration file corrupted: {config_path}")
self.logger.critical(f"RAGFlow server unreachable: {ragflow_url}")
```

**When to use:**

- Configuration or secrets missing
- External service permanently unreachable
- Filesystem errors
- Database corruption
- Unrecoverable exception in main loop

---

## Structured Logging

### Message Structure

Format: `<action>: <resource> | <context> | <result>`

**Examples:**

✅ **Good:**

```python
self.logger.info(f"Downloaded: aemo_2025_q1.pdf (2.0 MB, 1.2s)")
self.logger.warning(f"FlareSolverr timeout: {url} (60s), retrying with direct request")
self.logger.error(f"Parse failed: {filename} (missing title, skipping)")
```

❌ **Poor:**

```python
self.logger.info("Done")  # No context
self.logger.error("Error")  # No details
```

### Using Structured Context

Use `extra` dict for machine-parsable context:

```python
self.logger.info(
    "Document downloaded successfully",
    extra={
        "scraper": self.name,
        "document": filename,
        "size_bytes": file_size,
        "duration_seconds": 1.2,
        "operation": "download",
        "status": "success"
    }
)

# Exception with context
try:
    upload_to_ragflow(metadata)
except Exception as e:
    self.logger.error(
        "RAGFlow upload failed",
        exc_info=e,
        extra={
            "scraper": self.name,
            "document": filename,
            "dataset_id": dataset_id,
            "retry_count": 2
        }
    )
```

---

## Log Rotation & Retention

### Configuration

Set via environment variables:

```bash
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_JSON_FORMAT=true          # Emit JSON logs to file handler
LOG_TO_FILE=true              # Enable file handler (console always on)
LOG_FILE_MAX_BYTES=10485760   # 10 MB per file
LOG_FILE_BACKUP_COUNT=5       # Keep 5 rotated files
LOG_DIR=/app/data/logs        # Log directory
```

### Rotation Policy

- **Max file size:** 10 MB (configurable)
- **Backup count:** 5 files retained
- **Total retention:** ~50 MB on disk
- **Behavior:** When `scraper.log` reaches 10 MB, files rotate:
  - `scraper.log` → `scraper.log.1`
  - `scraper.log.1` → `scraper.log.2`
  - Files older than `scraper.log.5` are deleted

### Directory Structure

```tree
data/logs/
├── scraper.log              # Current log
├── scraper.log.1            # Previous rotation
├── scraper.log.2
├── scraper.log.3
├── scraper.log.4
└── scraper.log.5            # Oldest retained
```

---

## Common Errors & Troubleshooting

### Troubleshooting Flowchart

```tree
SCRAPER RUN FAILED
│
├─ Check last 10 lines: tail -10 data/logs/scraper.log
│  │
│  ├─ Contains "CRITICAL" or "RAGFLOW_UNREACHABLE"?
│  │  └─ YES → External service unavailable
│  │  └─ NO  → Continue
│  │
│  └─ Contains "PARSE_ERROR" or "VALIDATION_ERROR"?
│     └─ YES → Scraper logic error
│     └─ NO  → Continue
│
└─ Enable DEBUG logging and re-run:
   LOG_LEVEL=DEBUG python scripts/run_scraper.py --scraper <name>
```

### Network & Connectivity Errors

**Error:** `NET_TIMEOUT` or `connect timed out`  
**Fix:**

1. Check network: `ping <host>`
2. Increase timeout: `SCRAPER_REQUEST_TIMEOUT=30`
3. Check firewall rules

**Error:** `HTTP 403 Forbidden` or `HTTP 401 Unauthorized`  
**Fix:**

1. Verify API keys in `.env`
2. Re-authenticate with service
3. Check if IP is blocklisted

### FlareSolverr Errors

**Error:** `FlareSolverr timeout`  
**Fix:**

1. Check status: `docker compose ps flaresolverr`
2. Restart: `docker compose restart flaresolverr`
3. Check logs: `docker compose logs flaresolverr | tail -20`
4. Fallback: Set `FLARESOLVERR_ENABLED=false`

### RAGFlow Errors

**Error:** `RAGFLOW_UNREACHABLE` or `Connection refused`  
**Fix:**

1. Start services: `docker compose --profile full up -d`
2. Verify RAGFlow: `curl http://localhost:9380/`
3. Check logs: `docker compose logs ragflow | tail -30`

**Error:** `Authentication failed`  
**Fix:**

1. Regenerate API key in RAGFlow UI
2. Update `.env`: `RAGFLOW_API_KEY=<key>`
3. Restart: `docker compose restart scraper`

**Error:** `Dataset not found` or `404`  
**Fix:**

1. List datasets: `curl -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
2. Update config with correct dataset_id
3. Or enable auto-create: `RAGFLOW_AUTO_CREATE_DATASET=true`

### Parsing & Metadata Errors

**Error:** `PARSE_ERROR: failed to extract title`  
**Fix:**

1. Inspect page: `curl -s <url> | head -50`
2. Update scraper CSS selectors in `config/scrapers/{scraper}.json`
3. Test with single page: `python scripts/run_scraper.py --scraper <name> --max-pages 1`

**Error:** `VALIDATION_ERROR: missing required field 'title'`  
**Fix:**

1. Enable DEBUG logs: `LOG_LEVEL=DEBUG`
2. Add fallback logic (e.g., use URL as title)

### State & Deduplication Errors

**Error:** `STATE_ERROR: state file corrupted`  
**Fix:**

1. Inspect: `cat data/state/{scraper}_state.json | jq .`
2. If invalid JSON, delete: `rm data/state/{scraper}_state.json`
3. Restart scraper (will recreate from scratch)

**Error:** `Duplicate detected` but document is new  
**Fix:**

1. Use `--force` to re-process: `python scripts/run_scraper.py --scraper {name} --force`
2. Or delete state: `rm data/state/{scraper}_state.json`

### Resource Errors

**Error:** `Disk full` or `No space left on device`  
**Fix:**

1. Check disk: `df -h`
2. Clean old files: `rm -rf data/scraped/*/older_than_30_days`
3. Compress logs: `gzip data/logs/scraper.log.*`

**Error:** `Out of memory` or `OOMKilled`  
**Fix:**

1. Reduce concurrency: `MAX_CONCURRENT_DOWNLOADS=1`
2. Restart Chrome: `docker compose restart chrome`
3. Increase container memory in `docker-compose.yml`

---

## Logging Checklist for Contributors

When adding a new scraper or feature:

- [ ] Log scraper start: `self.logger.info(f"Starting {self.name} scraper")`
- [ ] Log each document download: `self.logger.info(f"Downloaded: {filename}")`
- [ ] Log skipped documents: `self.logger.warning(f"Skipped {url}: {reason}")`
- [ ] Log errors with context: `self.logger.error(f"Failed {action}: {url}", exc_info=True)`
- [ ] Use structured context via `extra` dict
- [ ] Test with DEBUG level: `LOG_LEVEL=DEBUG`
- [ ] Verify logs are human-readable and actionable

---

## References

- [logging_config.py](../../app/utils/logging_config.py) – Logging setup
- [errors.py](../../app/utils/errors.py) – Exception hierarchy
- [retry.py](../../app/utils/retry.py) – Retry decorator
- [BaseScraper](../../app/scrapers/base_scraper.py) – Example patterns
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) – Development setup
